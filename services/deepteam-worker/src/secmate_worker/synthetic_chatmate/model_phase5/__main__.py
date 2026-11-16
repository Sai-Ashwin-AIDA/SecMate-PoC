"""Run or reconcile the bounded Phase 5 retrieval demonstration."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import tempfile
from pathlib import Path

import httpx

from ...contracts import CampaignBudget
from ...execution_budget import CampaignBudgetManager
from ...job_runtime import canonical
from ...model_clients import ModelClientSettings, StructuredModelClients
from ..communication.contracts import MAIL, TEAMS
from .runtime import ModelPhase5Target, PROFILE_BUDGETS
from .verification import reconcile_report
from .adapter import provider_name


def _manager():
    return CampaignBudgetManager(CampaignBudget(
        max_paths=1, max_turns_per_path=2, max_provider_calls=PROFILE_BUDGETS["provider_attempt_limit"],
        max_concurrent_provider_calls=1, max_total_tokens=PROFILE_BUDGETS["provider_token_limit"],
        timeout_seconds=PROFILE_BUDGETS["real_deadline_seconds"], max_retries_per_call=0,
    ))


def _mock_transport(tool):
    calls = 0

    async def handler(request):
        nonlocal calls
        calls += 1
        payload = json.loads(request.content)
        if calls == 1:
            arguments = {"query": "lunch", "limit": 20, "cursor": None} if tool == MAIL else {
                "space_id": "team-common", "query": "lunch", "limit": 20, "cursor": None,
            }
            message = {"content": None, "tool_calls": [{
                "id": "call_mock_01HZX7N4P5Q9R2V8", "type": "function",
                "function": {"name": provider_name(tool), "arguments": canonical(arguments)},
            }]}
            finish = "tool_calls"
        else:
            replay = payload["messages"][-2:]
            if replay[0]["tool_calls"][0]["id"] != replay[1]["tool_call_id"]:
                return httpx.Response(500)
            output = json.loads(replay[1]["content"])
            ids = [item["id"] for item in output["items"]]
            message = {"content": "Fictional lunch planning records: " + ", ".join(ids), "tool_calls": []}
            finish = "stop"
        return httpx.Response(200, headers={"x-request-id": f"mock-or-request-{calls:04d}"}, json={
            "id": f"gen-mock-{calls:04d}", "model": payload["model"], "choices": [{"index": 0, "finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
        })

    return httpx.MockTransport(handler)


async def _run(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    live = args.mode == "openrouter-nemotron"
    if live:
        if not args.allow_live_provider or not args.allow_openrouter_data_collection or os.environ.get("SECMATE_PHASE5_LIVE_AUTHORIZATION") != "AUTHORIZED":
            raise SystemExit("Live provider authorization gates are incomplete")
        key = os.environ.get("OPENROUTER_API_KEY", "")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY is required for authorized live mode")
        transport = None
    else:
        key, transport = "mock-openrouter-key", _mock_transport(args.tool)
    clients = StructuredModelClients(
        ModelClientSettings(groq_api_key="", openrouter_api_key=key, request_timeout_seconds=45,
                            openrouter_allow_data_collection=args.allow_openrouter_data_collection,
                            provider_min_spacing_seconds=0, provider_max_spacing_seconds=0,
                            provider_retry_jitter_seconds=0),
        _manager(), transport=transport,
    )
    try:
        assessment = ModelPhase5Target(root).fresh(selected_tool=args.tool)
        run = await assessment.invoke(clients, args.prompt)
        meta = assessment.export(mock_verified=not live)
        report = root / "demo.json"
        report.write_text(canonical(meta), encoding="ascii")
        verification = reconcile_report(report)
        (root / "verification.json").write_text(canonical(verification), encoding="ascii")
        retrieval = next((event for event in assessment.events(assessment.session) if event["type"] == "retrieval.result"), None)
        print(f"model: {clients.settings and 'nvidia/nemotron-3.5-super-vl:free'}")
        print(f"tool requested: {args.tool}")
        print("tool authorization: " + ("allowed" if retrieval else "not reached"))
        print("fictional result IDs: " + canonical(retrieval["data"]["record_ids"] if retrieval else []))
        print("final summary: " + str(run["answer"]))
        print("evidence directory: " + str(assessment.path))
        print("terminal outcome: " + run["status"] + "/" + run["terminal_reason"])
        return 0 if run["status"] == "completed" else 1
    finally:
        await clients.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=("mocked", "openrouter-nemotron"), default="mocked")
    parser.add_argument("--tool", choices=(MAIL, TEAMS), default=MAIL)
    parser.add_argument("--prompt", default="Summarize my fictional lunch-planning mail.")
    parser.add_argument("--allow-live-provider", action="store_true")
    parser.add_argument("--allow-openrouter-data-collection", action="store_true")
    parser.add_argument("--reconcile", type=Path)
    args = parser.parse_args()
    if args.reconcile:
        print(canonical(reconcile_report(args.reconcile.resolve())))
        return 0
    if args.output is None:
        args.output = Path(tempfile.gettempdir()) / "opencode" / ("phase5-" + next(tempfile._get_candidate_names()))
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
