import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

from .deepteam_runner import ExecutionMode, SecMateDeepTeamRunner
from .deepteam_catalog import (
    ATTACK_PROFILES_BY_ID,
    DEFAULT_ATTACK_PROFILE_ID,
    DEFAULT_VULNERABILITY_PROFILE_ID,
    VULNERABILITY_PROFILES_BY_ID,
)
from .model_clients import ModelClientSettings
from .target_profiles import SOCMATE_PROFILE, TARGET_PROFILES_BY_ID


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a bounded synthetic DeepTeam campaign."
    )
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts"))
    parser.add_argument("--generation-context", type=Path)
    parser.add_argument("--generation-context-sha256")
    parser.add_argument(
        "--attack-profile",
        choices=sorted(ATTACK_PROFILES_BY_ID),
        default=DEFAULT_ATTACK_PROFILE_ID,
    )
    parser.add_argument(
        "--vulnerability-profile",
        choices=sorted(VULNERABILITY_PROFILES_BY_ID),
        default=DEFAULT_VULNERABILITY_PROFILE_ID,
    )
    parser.add_argument("--token-budget", type=int, default=250_000)
    parser.add_argument(
        "--execution-mode",
        choices=[mode.value for mode in ExecutionMode],
        default=ExecutionMode.SINGLE.value,
    )
    parser.add_argument("--max-paths", type=int, choices=(1, 2), default=1)
    parser.add_argument(
        "--target-profile",
        choices=sorted(TARGET_PROFILES_BY_ID),
        default=SOCMATE_PROFILE.profile_id,
    )
    parser.add_argument(
        "--allow-openrouter-data-collection",
        action="store_true",
        help="Required only for the declared harmless synthetic free-model run.",
    )
    args = parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    settings = ModelClientSettings(
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_critic_api_key=os.getenv("GROQ_CRITIC_API_KEY", "").strip(),
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
    if not args.allow_openrouter_data_collection:
        raise SystemExit(
            "The current free OpenRouter models require explicit collection approval. "
            "Use only with harmless synthetic prompts."
        )
    if not 10_000 <= args.token_budget <= 250_000:
        raise SystemExit("Token budget must be between 10,000 and 250,000.")
    if args.execution_mode == ExecutionMode.SINGLE.value and args.max_paths != 1:
        raise SystemExit("SINGLE execution requires --max-paths 1.")
    if args.execution_mode == ExecutionMode.ADAPTIVE.value and args.max_paths != 2:
        raise SystemExit("ADAPTIVE execution requires --max-paths 2.")
    runner = SecMateDeepTeamRunner(settings)
    context = None
    if args.generation_context:
        from .job_runtime import read_frozen
        from .standard_review_contracts import LinkedAssessmentContext, digest
        context = LinkedAssessmentContext.model_validate_json(read_frozen(args.generation_context))
        if digest(context.model_dump(mode="json")) != args.generation_context_sha256:
            raise SystemExit("Frozen linked context digest mismatch")
    elif args.generation_context_sha256:
        raise SystemExit("Linked context digest requires an input file")
    run = asyncio.run(
        runner.run_single_attack(
            args.attack_profile,
            args.vulnerability_profile,
            args.token_budget,
            args.execution_mode,
            args.max_paths,
            args.target_profile,
            **({"follow_up_context": context} if context is not None else {}),
        )
    )
    directory = runner.persist(run, args.output)
    print(json.dumps({**run.summary(), "artifact_directory": str(directory)}, indent=2))
    if run.final_status == "ERROR":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
