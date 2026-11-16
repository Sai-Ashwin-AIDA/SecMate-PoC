from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from .contracts import CampaignBudget
from .execution_budget import CampaignBudgetManager
from .model_clients import (
    ModelClientError,
    ModelClientSettings,
    StructuredModelClients,
)
from .model_profiles import (
    GROQ_QWEN_ATTACKER,
    OPENROUTER_NEMOTRON_EVALUATOR,
    OPENROUTER_NEMOTRON_TARGET,
    RuntimeModelProfile,
)
from .runtime_policy import (
    configure_runtime_environment,
    validate_installed_frameworks,
    validate_runtime,
)


class ReachabilityReply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["READY"]
    summary: str = Field(min_length=1, max_length=160)


async def run_model_smoke(
    settings: ModelClientSettings,
) -> tuple[list[dict[str, object]], dict[str, object]]:
    configure_runtime_environment()
    validate_runtime()
    validate_installed_frameworks()
    from .model_adapters import GroqDeepEvalModel, OpenRouterDeepEvalModel

    budget_manager = CampaignBudgetManager(
        CampaignBudget(
            max_paths=1,
            max_turns_per_path=1,
            max_provider_calls=3,
            max_concurrent_provider_calls=1,
            max_total_tokens=10_000,
            timeout_seconds=180,
            max_retries_per_call=0,
        )
    )
    clients = StructuredModelClients(
        settings,
        budget_manager=budget_manager,
    )
    structured_checks = (
        (
            GROQ_QWEN_ATTACKER,
            GroqDeepEvalModel(
                clients,
                GROQ_QWEN_ATTACKER.model,
                profile_id=GROQ_QWEN_ATTACKER.profile_id,
                role=GROQ_QWEN_ATTACKER.role,
            ),
        ),
        (
            OPENROUTER_NEMOTRON_EVALUATOR,
            OpenRouterDeepEvalModel(
                clients,
                OPENROUTER_NEMOTRON_EVALUATOR.model,
                profile_id=OPENROUTER_NEMOTRON_EVALUATOR.profile_id,
                role=OPENROUTER_NEMOTRON_EVALUATOR.role,
            ),
        ),
    )
    results: list[dict[str, object]] = []
    prompt = (
        "This is a harmless SecMate connectivity check using synthetic data only. "
        "Return status READY and a short confirmation."
    )
    for profile, adapter in structured_checks:
        metadata = []
        adapter.metadata_sink = metadata.append
        try:
            reply = await adapter.a_generate(prompt, schema=ReachabilityReply)
            call = metadata[-1]
            results.append(
                {
                    "profile_id": profile.profile_id,
                    "provider": profile.provider.value,
                    "model": profile.model,
                    "status": "PASS",
                    "latency_ms": call.latency_ms,
                    "usage": call.usage.model_dump() if call.usage else None,
                    "summary": reply.summary,
                }
            )
        except Exception as error:
            results.append(_failure_result(profile, error))
    target_metadata = []
    target_adapter = OpenRouterDeepEvalModel(
        clients,
        OPENROUTER_NEMOTRON_TARGET.model,
        metadata_sink=target_metadata.append,
        profile_id=OPENROUTER_NEMOTRON_TARGET.profile_id,
        role=OPENROUTER_NEMOTRON_TARGET.role,
    )
    try:
        target_reply = await target_adapter.a_generate(prompt)
        target_call = target_metadata[-1]
        results.append(
            {
                "profile_id": OPENROUTER_NEMOTRON_TARGET.profile_id,
                "provider": OPENROUTER_NEMOTRON_TARGET.provider.value,
                "model": OPENROUTER_NEMOTRON_TARGET.model,
                "status": "PASS",
                "latency_ms": target_call.latency_ms,
                "usage": (
                    target_call.usage.model_dump() if target_call.usage else None
                ),
                "summary": target_reply[:160],
            }
        )
    except Exception as error:
        results.append(_failure_result(OPENROUTER_NEMOTRON_TARGET, error))
    snapshot = asdict(await budget_manager.snapshot())
    await clients.close()
    return results, snapshot


def _failure_result(
    profile: RuntimeModelProfile,
    error: Exception,
) -> dict[str, object]:
    result: dict[str, object] = {
        "profile_id": profile.profile_id,
        "provider": profile.provider.value,
        "model": profile.model,
        "status": "FAIL",
        "error": str(error),
    }
    if isinstance(error, ModelClientError):
        result.update(
            {
                "error_code": error.code.value,
                "retryable": error.retryable,
                "status_code": error.status_code,
                "latency_ms": error.latency_ms,
                "provider_request_id": error.provider_request_id,
            }
        )
    else:
        result.update(
            {
                "error": "Unexpected model smoke failure.",
                "error_code": "UNEXPECTED_ERROR",
                "retryable": False,
                "status_code": None,
                "latency_ms": 0,
                "provider_request_id": None,
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run harmless model reachability checks.")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument(
        "--allow-openrouter-data-collection",
        action="store_true",
        help="Allow only for the declared harmless synthetic smoke prompts.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    configure_runtime_environment()
    validate_runtime()
    installed_deepteam_commit = validate_installed_frameworks()
    settings = ModelClientSettings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        request_timeout_seconds=float(
            os.getenv("SECMATE_REQUEST_TIMEOUT_SECONDS", "45")
        ),
        provider_min_spacing_seconds=float(
            os.getenv("SECMATE_PROVIDER_MIN_SPACING_SECONDS", "2")
        ),
        provider_tokens_per_second=float(
            os.getenv("SECMATE_PROVIDER_TOKENS_PER_SECOND", "300")
        ),
        provider_max_spacing_seconds=float(
            os.getenv("SECMATE_PROVIDER_MAX_SPACING_SECONDS", "12")
        ),
        provider_retry_base_seconds=float(
            os.getenv("SECMATE_PROVIDER_RETRY_BASE_SECONDS", "2")
        ),
        provider_max_cooldown_seconds=float(
            os.getenv("SECMATE_PROVIDER_MAX_COOLDOWN_SECONDS", "30")
        ),
        provider_retry_jitter_seconds=float(
            os.getenv("SECMATE_PROVIDER_RETRY_JITTER_SECONDS", "0.25")
        ),
        openrouter_allow_data_collection=args.allow_openrouter_data_collection,
    )
    results, budget_snapshot = asyncio.run(run_model_smoke(settings))
    report = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "python_version": platform.python_version(),
        "deepteam_version": version("deepteam"),
        "deepteam_commit": installed_deepteam_commit,
        "deepeval_version": version("deepeval"),
        "synthetic_prompts_only": True,
        "openrouter_data_collection": (
            "allow" if args.allow_openrouter_data_collection else "deny"
        ),
        "command": (
            "secmate-worker-model-smoke --env-file <redacted> "
            "--allow-openrouter-data-collection"
            if args.allow_openrouter_data_collection
            else "secmate-worker-model-smoke --env-file <redacted>"
        ),
        "budget": budget_snapshot,
        "results": results,
    }
    serialized = json.dumps(report, indent=2) + "\n"
    print(serialized, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="ascii")
    if any(result["status"] != "PASS" for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
