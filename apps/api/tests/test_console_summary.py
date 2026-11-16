from datetime import datetime, timezone
from types import SimpleNamespace

from secmate_api import chatmate_runs, console, deepteam_runs, synthetic_chatmate_smoke


NOW = datetime(2026, 11, 15, 12, 0, tzinfo=timezone.utc)


def _run(run_id, status, timestamp, *, outcome=None, target_id="synthetic-socmate-tier1",
         target_name="stored name", secret=None, evaluated=False, critic_status=None):
    return SimpleNamespace(
        run_id=run_id,
        status=status,
        final_status=outcome,
        target_profile_id=target_id,
        target_name=target_name,
        created_at=timestamp,
        started_at=None,
        completed_at=None,
        evidence=secret,
        logs=secret,
        error_message=secret,
        manual_evidence={"saved": True} if evaluated else None,
        evaluation_attempts=1 if evaluated else 0,
        critic_status=critic_status,
    )


def _smoke(run_id, status, timestamp, *, secret=None):
    return SimpleNamespace(
        run_id=run_id,
        status=status,
        target_id="secmate.synthetic-chatmate.fresh.v1",
        target_name="untrusted smoke name",
        created_at=timestamp,
        started_at=None,
        completed_at=None,
        final_response=secret,
        error_message=secret,
    )


def _sources(monkeypatch, deepteam=(), chatmate=(), smoke=()):
    monkeypatch.setattr(console, "snapshot_deepteam_runs", lambda: list(deepteam))
    monkeypatch.setattr(console, "snapshot_chatmate_runs", lambda: list(chatmate))
    monkeypatch.setattr(console, "snapshot_smoke_runs", lambda: list(smoke))


def test_summary_endpoint_is_read_only_bounded_and_not_cached(monkeypatch):
    from fastapi.testclient import TestClient
    from secmate_api.main import app

    monkeypatch.setattr(console, "snapshot", lambda days: {"days": days, "activity": []})
    client = TestClient(app)
    response = client.get("/api/v1/console-summary?days=7")

    assert response.json() == {"days": 7, "activity": []}
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/console-summary?days=0").status_code == 422
    assert client.get("/api/v1/console-summary?days=91").status_code == 422


def test_v2_normalizes_families_targets_lifecycles_and_policy_outcomes(monkeypatch):
    secret = "private evidence prompt diagnostic"
    deepteam = [
        _run("soc-resisted", "COMPLETED", "2026-11-15T09:00:00Z", outcome="RESISTED", secret=secret),
        _run("fresh-compromised", "COMPLETED", "2026-11-15T14:00:00+02:00", outcome="COMPROMISED",
             target_id="secmate.synthetic-chatmate.fresh.v1", target_name="wrong historical name"),
        _run("unknown", "COMPLETED", "2026-11-14T10:00:00Z", outcome="INCONCLUSIVE",
             target_id="retired.target.v1", target_name="Retired Target"),
        _run("draft", "DRAFT", "2026-11-13T10:00:00Z"),
        _run("error", "FAILED", "2026-11-12T10:00:00Z", outcome="ERROR"),
        _run("cancelled", "CANCELLED", "2026-11-11T10:00:00Z"),
        _run("active-old", "RUNNING", "2026-10-01T10:00:00Z"),
    ]
    chatmate = [
        _run("legacy-resisted", "COMPLETED", "2026-11-15T08:00:00Z", outcome="RESISTED", evaluated=True),
        _run("legacy-failed", "FAILED", "2026-11-14T08:00:00Z", outcome="COMPROMISED"),
        _run("legacy-rejected", "REJECTED", "2026-11-13T08:00:00Z"),
        _run("legacy-abandoned", "ABANDONED", "2026-11-12T08:00:00Z"),
        _run("legacy-draft", "DRAFT", "2026-11-11T08:00:00Z"),
    ]
    smoke = [
        _smoke("target-smoke-111111111111", "COMPLETED", "2026-11-15T07:00:00Z", secret=secret),
        _smoke("target-smoke-222222222222", "FAILED", "2026-11-14T07:00:00Z"),
        _smoke("target-smoke-333333333333", "RUNNING", "2026-11-13T07:00:00Z"),
    ]
    _sources(monkeypatch, deepteam, chatmate, smoke)

    result = console.snapshot(7, now=NOW)

    assert result["schema_version"] == "console-summary-v2"
    assert result["range"] == {
        "days": 7,
        "start": "2026-11-09T00:00:00+00:00",
        "end_exclusive": "2026-11-16T00:00:00+00:00",
        "timezone": "UTC",
    }
    assert result["counts"] == {
        "total": 14, "assessments": 9, "drafts": 2, "smoke_tests": 3, "active": 1,
        "completed": 5, "evaluated": 4, "conclusive": 3, "resisted": 2,
        "compromised": 1, "inconclusive": 1, "failed": 3, "cancelled": 1,
        "rejected": 1, "abandoned": 1,
    }
    assert result["pass_rate"] == 66.7
    assert result["pass_rate_rounding"] == "PERCENT_HALF_UP_1_DECIMAL"
    assert result["finding_severity"] == {"available": False, "counts": None}
    assert result["has_active_runs_global"] is True
    assert result["has_active_runs_in_range"] is True

    assert set(result["targets"]) == {
        "synthetic-socmate-tier1", "secmate.synthetic-chatmate.fresh.v1",
        "retired.target.v1", "legacy-chatmate-manual",
    }
    assert result["targets"]["synthetic-socmate-tier1"]["target_name"] == "SocMate"
    assert result["targets"]["secmate.synthetic-chatmate.fresh.v1"]["target_name"] == "Synthetic ChatMate"
    assert result["targets"]["secmate.synthetic-chatmate.fresh.v1"]["target_owner"] == "AIDA"
    assert result["targets"]["retired.target.v1"]["target_name"] == "Retired Target"
    assert result["targets"]["retired.target.v1"]["target_owner"] is None
    assert result["targets"]["legacy-chatmate-manual"]["target_name"] == "ChatMate"
    assert "socmate" not in result["targets"] and "chatmate" not in result["targets"]

    activities = {item["run_id"]: item for item in result["activity"]}
    assert activities["soc-resisted"]["family"] == "DEEPTEAM"
    assert activities["soc-resisted"]["target_id"] == "synthetic-socmate-tier1"
    assert activities["legacy-resisted"]["family"] == "LEGACY_CHATMATE"
    assert activities["draft"]["kind"] == "DRAFT"
    assert activities["target-smoke-111111111111"]["kind"] == "SMOKE_TEST"
    assert activities["error"]["outcome"] is None and not activities["error"]["evaluated"]
    assert activities["legacy-failed"]["outcome"] is None and not activities["legacy-failed"]["evaluated"]
    assert all(item["activity_id"].endswith(":" + item["run_id"]) for item in result["activity"])
    assert secret not in str(result)


def test_utc_calendar_boundaries_offsets_naive_invalid_and_future_are_consistent(monkeypatch):
    records = [
        _run("at-start-naive", "COMPLETED", "2026-11-09T00:00:00", outcome="RESISTED"),
        _run("before-offset", "COMPLETED", "2026-11-09T00:30:00+01:00", outcome="COMPROMISED"),
        _run("at-end", "COMPLETED", "2026-11-16T00:00:00Z", outcome="COMPROMISED"),
        _run("later-today", "COMPLETED", "2026-11-15T12:00:01Z", outcome="COMPROMISED"),
        _run("future", "COMPLETED", "2026-11-20T00:00:00Z", outcome="COMPROMISED"),
        _run("invalid", "RUNNING", "not-a-time"),
    ]
    _sources(monkeypatch, deepteam=records)

    result = console.snapshot(7, now=NOW)

    assert [item["run_id"] for item in result["activity"]] == ["at-start-naive"]
    assert result["activity"][0]["occurred_at"] == "2026-11-09T00:00:00+00:00"
    assert len(result["trend"]) == 7
    assert [point["date"] for point in result["trend"]] == [
        "2026-11-09", "2026-11-10", "2026-11-11", "2026-11-12",
        "2026-11-13", "2026-11-14", "2026-11-15",
    ]
    assert result["trend"][0]["counts"]["total"] == 1
    assert result["trend"][0]["pass_rate"] == 100.0
    assert all(point["pass_rate"] is None for point in result["trend"][1:])
    assert result["has_active_runs_global"] is True
    assert result["has_active_runs_in_range"] is False


def test_nullable_pass_rate_and_latest_activity_limit_are_deterministic(monkeypatch):
    records = [
        _run(f"run-{index:02}", "COMPLETED", "2026-11-15T10:00:00Z", outcome="INCONCLUSIVE")
        for index in range(25)
    ]
    _sources(monkeypatch, deepteam=records)

    result = console.snapshot(7, now=NOW)

    assert result["counts"]["total"] == 25
    assert result["pass_rate"] is None
    assert len(result["activity"]) == 20
    assert [item["run_id"] for item in result["activity"]] == [f"run-{index:02}" for index in range(24, 4, -1)]


def test_legacy_awaiting_phase_is_active_but_unevaluated_completion_is_not_an_outcome(monkeypatch):
    records = [
        _run("awaiting", "AWAITING_EVALUATION", "2026-11-15T09:00:00Z"),
        _run("unevaluated", "COMPLETED", "2026-11-15T08:00:00Z", outcome="COMPROMISED"),
    ]
    _sources(monkeypatch, chatmate=records)

    result = console.snapshot(7, now=NOW)

    assert result["has_active_runs_global"] is True
    assert result["has_active_runs_in_range"] is True
    assert result["counts"]["active"] == 1
    assert result["counts"]["evaluated"] == result["counts"]["compromised"] == 0
    assert result["pass_rate"] is None


def test_completed_assessment_with_running_critic_counts_as_active_work(monkeypatch):
    _sources(monkeypatch, deepteam=[
        _run("critic", "COMPLETED", "2026-11-15T09:00:00Z", outcome="RESISTED", critic_status="RUNNING"),
    ])

    result = console.snapshot(7, now=NOW)

    assert result["has_active_runs_global"] is True
    assert result["has_active_runs_in_range"] is True
    assert result["counts"]["active"] == 1
    assert result["counts"]["resisted"] == 1


def test_snapshot_readers_copy_all_current_records_without_reconciliation(monkeypatch):
    class Record:
        def __init__(self, run_id):
            self.run_id = run_id
            self.copies = 0

        def model_copy(self, *, deep):
            assert deep is True
            self.copies += 1
            return SimpleNamespace(run_id=self.run_id)

    deep_draft = Record("deep-draft")
    legacy = Record("legacy")
    smoke = Record("smoke")
    monkeypatch.setattr(deepteam_runs, "_runs", {deep_draft.run_id: deep_draft})
    monkeypatch.setattr(chatmate_runs, "_runs", {legacy.run_id: legacy})
    monkeypatch.setattr(synthetic_chatmate_smoke, "_runs", {smoke.run_id: smoke})
    monkeypatch.setattr(chatmate_runs, "_refresh_generation_failure_locked",
                        lambda run_id: (_ for _ in ()).throw(AssertionError("must not reconcile")))
    monkeypatch.setattr(chatmate_runs, "_refresh_critic_locked",
                        lambda run_id: (_ for _ in ()).throw(AssertionError("must not reconcile")))

    assert [item.run_id for item in deepteam_runs.snapshot_deepteam_runs()] == ["deep-draft"]
    assert [item.run_id for item in chatmate_runs.snapshot_chatmate_runs()] == ["legacy"]
    assert [item.run_id for item in synthetic_chatmate_smoke.snapshot_runs()] == ["smoke"]
    assert (deep_draft.copies, legacy.copies, smoke.copies) == (1, 1, 1)
