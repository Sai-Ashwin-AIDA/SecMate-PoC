"""Read-only normalized dashboard accounting over retained run stores."""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from .chatmate_runs import snapshot_chatmate_runs
from .deepteam_runs import snapshot_deepteam_runs
from .synthetic_chatmate_smoke import snapshot_runs as snapshot_smoke_runs
from .target_projection import get_target


ACTIVE = {
    "QUEUED", "RUNNING", "CANCEL_REQUESTED", "GENERATING",
    "AWAITING_SELECTION", "AWAITING_RESPONSE", "AWAITING_EVALUATION", "EVALUATING",
}
POLICY_OUTCOMES = {"RESISTED", "COMPROMISED", "INCONCLUSIVE"}
LEGACY_CHATMATE_TARGET_ID = "legacy-chatmate-manual"
PASS_RATE_ROUNDING = "PERCENT_HALF_UP_1_DECIMAL"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _instant(value) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        return None


def _occurred_at(run) -> datetime | None:
    value = getattr(run, "completed_at", None) or getattr(run, "started_at", None) or getattr(run, "created_at", None)
    return _instant(value)


def _target(target_id: str, stored_name: str | None) -> tuple[str | None, str | None]:
    authoritative = get_target(target_id)
    if authoritative is None:
        return stored_name, None
    return authoritative.name, authoritative.owner


def _activity(run, *, family: str, kind: str, target_id: str, target_name: str | None,
              target_owner: str | None, occurred: datetime, evaluated: bool | None = None,
              active: bool | None = None) -> dict:
    status = run.status
    outcome = getattr(run, "final_status", None)
    if evaluated is None:
        evaluated = kind == "ASSESSMENT" and status == "COMPLETED" and outcome in POLICY_OUTCOMES
    if active is None:
        active = status in ACTIVE
    return {
        "activity_id": f"{family.lower()}:{run.run_id}",
        "run_id": run.run_id,
        "kind": kind,
        "family": family,
        "target_id": target_id,
        "target_name": target_name,
        "target_owner": target_owner,
        "status": status,
        "outcome": outcome if evaluated else None,
        "evaluated": evaluated,
        "active": active,
        "occurred_at": occurred.isoformat(),
    }


def _counts(records: list[dict]) -> dict:
    return {
        "total": len(records),
        "assessments": sum(item["kind"] == "ASSESSMENT" for item in records),
        "drafts": sum(item["kind"] == "DRAFT" for item in records),
        "smoke_tests": sum(item["kind"] == "SMOKE_TEST" for item in records),
        "active": sum(item["active"] for item in records),
        "completed": sum(item["status"] == "COMPLETED" for item in records),
        "evaluated": sum(item["evaluated"] for item in records),
        "conclusive": sum(item["outcome"] in {"RESISTED", "COMPROMISED"} for item in records),
        "resisted": sum(item["outcome"] == "RESISTED" for item in records),
        "compromised": sum(item["outcome"] == "COMPROMISED" for item in records),
        "inconclusive": sum(item["outcome"] == "INCONCLUSIVE" for item in records),
        "failed": sum(item["status"] == "FAILED" for item in records),
        "cancelled": sum(item["status"] == "CANCELLED" for item in records),
        "rejected": sum(item["status"] == "REJECTED" for item in records),
        "abandoned": sum(item["status"] == "ABANDONED" for item in records),
    }


def _pass_rate(counts: dict) -> float | None:
    denominator = counts["resisted"] + counts["compromised"]
    if not denominator:
        return None
    percentage = Decimal(counts["resisted"] * 100) / Decimal(denominator)
    return float(percentage.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def snapshot(days: int, now: datetime | None = None) -> dict:
    current = _instant(now if now is not None else _now())
    if current is None:
        raise ValueError("Snapshot time must be a valid datetime")
    today = current.date()
    start = datetime.combine(today - timedelta(days=days - 1), time.min, timezone.utc)
    end = datetime.combine(today + timedelta(days=1), time.min, timezone.utc)

    normalized: list[tuple[datetime, dict]] = []
    active_states: list[bool] = []
    for run in snapshot_deepteam_runs():
        active = run.status in ACTIVE or getattr(run, "critic_status", None) == "RUNNING"
        active_states.append(active)
        occurred = _occurred_at(run)
        if occurred is None:
            continue
        target_name, target_owner = _target(run.target_profile_id, run.target_name)
        kind = "DRAFT" if run.status == "DRAFT" else "ASSESSMENT"
        normalized.append((occurred, _activity(
            run, family="DEEPTEAM", kind=kind, target_id=run.target_profile_id,
            target_name=target_name, target_owner=target_owner, occurred=occurred, active=active,
        )))
    for run in snapshot_chatmate_runs():
        active = run.status in ACTIVE or getattr(run, "critic_status", None) == "RUNNING"
        active_states.append(active)
        occurred = _occurred_at(run)
        if occurred is None:
            continue
        kind = "DRAFT" if run.status == "DRAFT" else "ASSESSMENT"
        normalized.append((occurred, _activity(
            run, family="LEGACY_CHATMATE", kind=kind, target_id=LEGACY_CHATMATE_TARGET_ID,
            target_name="ChatMate", target_owner=None, occurred=occurred,
            evaluated=(
                kind == "ASSESSMENT" and run.status == "COMPLETED"
                and run.final_status in POLICY_OUTCOMES
                and bool(getattr(run, "manual_evidence", None))
                and bool(getattr(run, "evaluation_attempts", 0))
            ),
            active=active,
        )))
    for run in snapshot_smoke_runs():
        active = run.status in ACTIVE
        active_states.append(active)
        occurred = _occurred_at(run)
        if occurred is None:
            continue
        target_name, target_owner = _target(run.target_id, run.target_name)
        normalized.append((occurred, _activity(
            run, family="SYNTHETIC_CHATMATE_SMOKE", kind="SMOKE_TEST", target_id=run.target_id,
            target_name=target_name, target_owner=target_owner, occurred=occurred, active=active,
        )))

    in_range = [(instant, item) for instant, item in normalized if start <= instant <= current and instant < end]
    in_range.sort(key=lambda value: (value[0], value[1]["activity_id"]), reverse=True)
    records = [item for _, item in in_range]
    summary_counts = _counts(records)

    targets = {}
    for target_id in sorted({item["target_id"] for item in records}):
        selected = [item for item in records if item["target_id"] == target_id]
        target_counts = _counts(selected)
        targets[target_id] = {
            "target_id": target_id,
            "target_name": selected[0]["target_name"],
            "target_owner": selected[0]["target_owner"],
            "counts": target_counts,
            "pass_rate": _pass_rate(target_counts),
            "latest_activity": selected[0],
        }

    trend = []
    for offset in range(days):
        bucket_start = start + timedelta(days=offset)
        bucket_end = bucket_start + timedelta(days=1)
        bucket_records = [item for instant, item in in_range if bucket_start <= instant < bucket_end]
        bucket_counts = _counts(bucket_records)
        trend.append({
            "date": bucket_start.date().isoformat(),
            "counts": bucket_counts,
            "pass_rate": _pass_rate(bucket_counts),
        })

    return {
        "schema_version": "console-summary-v2",
        "generated_at": current.isoformat(),
        "range": {"days": days, "start": start.isoformat(), "end_exclusive": end.isoformat(), "timezone": "UTC"},
        "has_active_runs_global": any(active_states),
        "has_active_runs_in_range": summary_counts["active"] > 0,
        "counts": summary_counts,
        "pass_rate": _pass_rate(summary_counts),
        "pass_rate_rounding": PASS_RATE_ROUNDING,
        "finding_severity": {"available": False, "counts": None},
        "targets": targets,
        "trend": trend,
        "activity": records[:20],
    }
