"""Phase 3 bound-resource grammar, domain and DST conformance checks."""
import pytest

from offline_synthetic_guard import forbid_network
from secmate_worker.synthetic_chatmate.calendar_phase3.time_rules import TimeRules, TimeError, materialize, parse
from secmate_worker.synthetic_chatmate.contracts import SyntheticError


@pytest.mark.parametrize("value", [
    "2030-01-08", "tomorrow", "2030-01-08T10:00:00", "2030-01-08t10:00:00Z",
    "2030-01-08T10:00:00z", " 2030-01-08T10:00:00Z", "2030-01-08T10:00:00.1Z",
    "2030-01-08T10:00:60Z", "2030-01-08T24:00:00Z", "2030-02-29T10:00:00Z",
    "2030-01-08T10:00:00-00:00", "2030-01-08T10:00:00+14:01",
    "2030-01-08T10:00:00+15:00", "1999-12-31T23:59:59Z", "2100-01-01T00:00:00Z",
    "0000-01-01T00:00:00Z", "9999-12-31T23:59:59-14:00",
])
def test_t01_strict_dates(value):
    with pytest.raises(TimeError) as error:
        parse(value, "/start")
    assert (error.value.code, error.value.field) == ("invalid_datetime", "/start")


@pytest.mark.parametrize("end", ["2030-01-08T10:00:00Z", "2030-01-08T09:59:59Z"])
def test_t02_nonpositive_interval(end):
    with pytest.raises(TimeError, match="invalid_interval"):
        TimeRules().interval("2030-01-08T10:00:00Z", end, "UTC")


def test_t02_t03_fold_and_reverse_wall_order():
    rules = TimeRules()
    early = rules.endpoint("2030-11-03T01:30:00-04:00", "America/New_York", "/start")
    late = rules.endpoint("2030-11-03T01:30:00-05:00", "America/New_York", "/start")
    assert early[1:] == ("2030-11-03T05:30:00Z", 0)
    assert late[1:] == ("2030-11-03T06:30:00Z", 1)
    result = rules.interval("2030-11-03T01:45:00-04:00", "2030-11-03T01:15:00-05:00", "America/New_York")
    assert result["start_utc"] == "2030-11-03T05:45:00Z"
    assert result["end_utc"] == "2030-11-03T06:15:00Z"


@pytest.mark.parametrize("value,code", [
    ("2030-03-10T02:30:00-05:00", "nonexistent_local_time"),
    ("2030-07-01T10:00:00-05:00", "timezone_offset_mismatch"),
])
def test_t03_gap_and_mismatch(value, code):
    with pytest.raises(TimeError, match=code):
        TimeRules().endpoint(value, "America/New_York", "/start")


def test_t04_equivalent_instants_and_transition():
    rules = TimeRules()
    assert rules.endpoint("2030-01-08T10:00:00Z", "UTC", "/start")[:2] == (
        "2030-01-08T10:00:00+00:00", "2030-01-08T10:00:00Z")
    assert rules.endpoint("2030-01-08T15:30:00+05:30", "Asia/Kolkata", "/start")[1] == "2030-01-08T10:00:00Z"
    result = rules.interval("2030-03-10T01:30:00-05:00", "2030-03-10T03:30:00-04:00", "America/New_York")
    assert result["start_utc"] == "2030-03-10T06:30:00Z"
    assert result["end_utc"] == "2030-03-10T07:30:00Z"


@pytest.mark.parametrize("zone", ["utc", "Etc/UTC", "US/Eastern", "../UTC", "/UTC", "Europe/London"])
def test_t05_exact_zone_allowlist(zone):
    with pytest.raises(TimeError, match="invalid_timezone"):
        TimeRules().zone(zone)


def test_t05_wrong_resource_binding_and_no_os_fallback(monkeypatch):
    import zoneinfo
    import tzdata
    artifact = materialize()
    artifact["resources"][0]["resource_sha256"] = "0" * 64
    with pytest.raises(SyntheticError, match="timezone_binding_unavailable"):
        TimeRules(artifact)
    zoneinfo.reset_tzpath([])
    try:
        assert TimeRules().endpoint("2030-01-08T15:30:00+05:30", "Asia/Kolkata", "/start")[1] == "2030-01-08T10:00:00Z"
    finally:
        zoneinfo.reset_tzpath()
    monkeypatch.setattr(tzdata, "__version__", "different")
    with pytest.raises(SyntheticError, match="timezone_binding_unavailable"):
        TimeRules()
