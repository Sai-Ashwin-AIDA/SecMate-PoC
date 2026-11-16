"""Pinned package-resource timezone rules; never consult OS timezone databases."""
import hashlib
import re
from datetime import datetime, timezone
from importlib.resources import files
from io import BytesIO
from zoneinfo import ZoneInfo

from ..contracts import SyntheticError, digest

ZONES = ("UTC", "America/New_York", "Asia/Kolkata")
RESOURCE_HASHES = {
    "UTC": "fddce1e648a1732ac29afd9a16151b2973cdf082e7ec0c690f7e42be6b598b93",
    "America/New_York": "d7f2206b3a45989fc9ad63d558922532fa7352280d5f87176bf1db79cb1d1fa9",
    "Asia/Kolkata": "3a00bdbe1bc4959e727567c730ba51b03455ecd455f7c190c5ad14386eb79b0d",
}
STAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|[+-][0-9]{2}:[0-9]{2})\Z")
MINIMUM = datetime(2000, 1, 1, tzinfo=timezone.utc)
MAXIMUM = datetime(2100, 1, 1, tzinfo=timezone.utc)


class TimeError(ValueError):
    def __init__(self, code, field):
        self.code, self.field = code, field
        super().__init__(code)


def resource_bytes():
    try:
        import tzdata
        if (tzdata.__version__, tzdata.IANA_VERSION) != ("2026.6", "2026f"):
            raise ValueError("version")
        result = {}
        for key in ZONES:
            value = files("tzdata.zoneinfo").joinpath(*key.split("/")).read_bytes()
            if hashlib.sha256(value).hexdigest() != RESOURCE_HASHES[key]:
                raise ValueError("resource")
            result[key] = value
        return result
    except (ImportError, OSError, ValueError, AttributeError):
        raise SyntheticError("timezone_binding_unavailable") from None


def materialize():
    resources = resource_bytes()
    return {
        "version": "time-rules-0.3.0", "package": "tzdata", "package_version": "2026.6",
        "iana_version": "2026f", "zones": list(ZONES),
        "resources": [{"zone_key": k, "resource_sha256": hashlib.sha256(resources[k]).hexdigest(),
                       "byte_count": len(resources[k])} for k in ZONES],
        "parser_version": "offset-time-v1", "transformation_version": "meeting-local-v1",
        "min_instant": "2000-01-01T00:00:00Z", "max_instant_exclusive": "2100-01-01T00:00:00Z",
        "os_fallback": False,
    }


def parse(value, field):
    if not isinstance(value, str):
        raise TimeError("invalid_arguments", field)
    try:
        if not STAMP.fullmatch(value) or value.endswith("-00:00"):
            raise ValueError("grammar")
        if not value.endswith("Z"):
            hours, minutes = int(value[-5:-3]), int(value[-2:])
            if hours > 14 or minutes > 59 or (hours == 14 and minutes):
                raise ValueError("offset")
        local = datetime.fromisoformat(value.replace("Z", "+00:00"))
        instant = local.astimezone(timezone.utc)
        if not MINIMUM <= instant < MAXIMUM:
            raise ValueError("domain")
        return local, instant
    except (ValueError, OverflowError):
        raise TimeError("invalid_datetime", field) from None


def utc(instant):
    return instant.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class TimeRules:
    def __init__(self, artifact=None):
        actual = materialize()
        if artifact is not None and artifact != actual:
            raise SyntheticError("timezone_binding_unavailable")
        self.artifact, self.digest = actual, digest(actual)
        self._cache = {}

    def zone(self, key):
        if not isinstance(key, str):
            raise TimeError("invalid_arguments", "/timezone")
        if key not in ZONES:
            raise TimeError("invalid_timezone", "/timezone")
        cache_key = (self.digest, key)
        if cache_key not in self._cache:
            self._cache[cache_key] = ZoneInfo.from_file(BytesIO(resource_bytes()[key]), key=key)
        return self._cache[cache_key]

    def endpoint(self, value, key, field):
        local, instant = parse(value, field)
        zone = self.zone(key)
        wall = local.replace(tzinfo=None)
        candidates = [wall.replace(tzinfo=zone, fold=f) for f in (0, 1)]
        real = [c for c in candidates if c.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == wall]
        if not real:
            raise TimeError("nonexistent_local_time", field)
        matched = instant.astimezone(zone)
        if matched.replace(tzinfo=None) != wall or matched.utcoffset() != local.utcoffset():
            raise TimeError("timezone_offset_mismatch", field)
        return matched.isoformat(timespec="seconds"), utc(instant), matched.fold

    def interval(self, start, end, key=None):
        if key is None:
            left, right = parse(start, "/start")[1], parse(end, "/end")[1]
            result = {"start_utc": utc(left), "end_utc": utc(right)}
        else:
            self.zone(key)
            a, au, af = self.endpoint(start, key, "/start")
            b, bu, bf = self.endpoint(end, key, "/end")
            left, right = parse(au, "/start")[1], parse(bu, "/end")[1]
            result = {"start": a, "end": b, "start_utc": au, "end_utc": bu,
                      "start_fold": af, "end_fold": bf}
        if right <= left:
            raise TimeError("invalid_interval", "/end")
        return result
