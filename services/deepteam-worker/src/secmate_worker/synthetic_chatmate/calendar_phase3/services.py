"""Typed calendar preparation and own-view reads, fictional and assessment-local."""
import base64
import hashlib

from ...job_runtime import canonical
from ..contracts import SyntheticError, digest, clone
from ..communication.store import CommunicationStore
from .contracts import bounded_json, validate
from .time_rules import TimeRules, TimeError


def contact(person):
    return {k: person[k] for k in ("person_id", "display_name", "address")}


def account(db, person):
    values = [bounded_json(r[0]) for r in db.execute("SELECT payload FROM calendar_accounts")]
    matches = [a for a in values if a["owner_person_id"] == person["person_id"] and
               a["tenant"] == person["tenant"] and a["connector_owner"] == person["connector_owner"]]
    if len(matches) != 1:
        raise SyntheticError("resource_unavailable")
    return matches[0]


def actor(db, identity, privilege):
    people = CommunicationStore.people(db)
    matches = [p for p in people if p["active"] and
               (p["subject"], p["connector_owner"], p["tenant"]) ==
               (identity["subject"], identity["connector_owner"], identity["tenant"])]
    if len(matches) != 1:
        raise SyntheticError("resource_unavailable")
    person = matches[0]
    calendar = account(db, person)
    if not calendar[privilege + "_enabled"]:
        raise SyntheticError("resource_unavailable")
    return person, calendar


def normalize_meeting(raw, rules):
    # String date/zone/cursor errors have explicit precedence over lexical schema
    # rejection; raw type/bound/extra-field failures still precede semantics.
    value = clone(raw)
    if type(value) is not dict or set(value) != {"title", "description", "attendee_ids", "start", "end", "timezone"}:
        raise TimeError("invalid_arguments", None)
    for field in ("start", "end", "timezone"):
        if type(value[field]) is not str:
            raise TimeError("invalid_arguments", "/" + field)
    structural = {**value, "start": "2030-01-08T10:00:00Z", "end": "2030-01-08T10:30:00Z", "timezone": "UTC"}
    try:
        validate("ProposeMeetingInput", structural)
    except ValueError:
        raise TimeError("invalid_arguments", None) from None
    value["title"] = value["title"].strip()
    if not value["title"]:
        raise TimeError("invalid_arguments", "/title")
    times = rules.interval(value["start"], value["end"], value["timezone"])
    prepared = {**value, "start": times["start"], "end": times["end"]}
    validate("PreparedMeeting", prepared)
    return prepared, times


def read_arguments(raw, rules):
    if type(raw) is not dict or set(raw) != {"start", "end", "limit", "cursor"}:
        raise TimeError("invalid_arguments", None)
    for key in ("start", "end"):
        if type(raw[key]) is not str:
            raise TimeError("invalid_arguments", "/" + key)
    if type(raw["limit"]) is not int or not 1 <= raw["limit"] <= 20:
        raise TimeError("invalid_arguments", "/limit")
    if raw["cursor"] is not None and type(raw["cursor"]) is not str:
        raise TimeError("invalid_arguments", "/cursor")
    window = rules.interval(raw["start"], raw["end"])
    if raw["cursor"] is not None:
        try:
            validate("Cursor", raw["cursor"])
        except ValueError:
            raise TimeError("invalid_cursor", "/cursor") from None
    return clone(raw), window


class CalendarServices:
    def __init__(self, binding, calendar_seed, rules):
        self.binding, self.seed, self.rules = binding, calendar_seed, rules

    def prepare(self, db, identity, prepared, times, transformation_digest):
        organizer, calendar = actor(db, identity, "create")
        if organizer["person_id"] in prepared["attendee_ids"]:
            raise TimeError("invalid_arguments", "/attendee_ids")
        people = {p["person_id"]: p for p in CommunicationStore.people(db)}
        attendees = []
        for pid in prepared["attendee_ids"]:
            person = people.get(pid)
            if person is None or not person["active"] or person["tenant"] != identity["tenant"] or not account(db, person)["invite_enabled"]:
                raise SyntheticError("resource_unavailable")
            attendees.append(contact(person))
        snapshot = {"contact": contact(organizer), "subject": organizer["subject"],
                    "connector_owner": organizer["connector_owner"], "tenant": organizer["tenant"],
                    "active": organizer["active"], "calendar_id": calendar["id"], "create_enabled": calendar["create_enabled"]}
        timing = {k: times[k] for k in ("start", "end", "start_utc", "end_utc")}
        timing.update(timezone=prepared["timezone"], time_rules_digest=self.rules.digest)
        review = {
            "action_kind": "meeting", "calendar_id": calendar["id"], "organizer": contact(organizer),
            "attendees": attendees, "prepared": prepared,
            "start_utc": times["start_utc"], "end_utc": times["end_utc"],
            "prepared_digest": digest(prepared),
            "argument_digest": digest({"tool": "secmate.propose_meeting", "arguments": prepared}),
            "organizer_snapshot_digest": digest(snapshot), "attendee_ids_digest": digest(prepared["attendee_ids"]),
            "attendee_snapshot_digest": digest(attendees),
            "content_digest": digest({k: prepared[k] for k in ("title", "description")}),
            "timing_digest": digest(timing), "transformation_version": "meeting-local-v1",
            "time_rules_digest": self.rules.digest,
        }
        validate("MeetingReview", review)
        dispatch = {"action_kind": "meeting", "calendar_id": calendar["id"], "organizer": review["organizer"],
                    "attendees": attendees, **{k: prepared[k] for k in ("title", "description", "start", "end", "timezone")},
                    "start_utc": times["start_utc"], "end_utc": times["end_utc"],
                    "time_rules_digest": self.rules.digest, "transformation_version": "meeting-local-v1"}
        validate("MeetingDispatch", dispatch)
        return snapshot, review, dispatch

    def view(self, db, identity):
        person, calendar = actor(db, identity, "read")
        records = [bounded_json(r[0]) for r in db.execute("SELECT payload FROM calendar_records ORDER BY ordinal")]
        visible = [r for r in records if r["tenant"] == identity["tenant"] and
                   (r["organizer_id"] == person["person_id"] or person["person_id"] in r["attendee_ids"])]
        policy = {"subject": identity["subject"], "person_id": person["person_id"],
                  "connector_owner": identity["connector_owner"], "tenant": identity["tenant"], "active": person["active"],
                  "calendar_id": calendar["id"], "read_enabled": calendar["read_enabled"]}
        value = {"policy": policy, "records": [{"id": r["id"], "content_digest": digest(r), "ordinal": r["ordinal"]} for r in visible]}
        validate("VisibleViewDigestInput", value)
        return calendar, visible, digest(value)

    @staticmethod
    def item(record):
        return {**{k: record[k] for k in ("id", "title", "description", "organizer_id", "attendee_ids", "start", "end", "timezone")},
                "source_ref": {"resource_id": record["id"], "source_kind": "synthetic_calendar", "content_digest": digest(record)}}

    def read(self, db, identity, arguments, window, requested=None):
        calendar, visible, view_digest = self.view(db, identity)
        if requested is not None and requested != calendar["id"]:
            raise SyntheticError("resource_unavailable")
        context = {"context_version": "calendar-cursor-context-v1", "tool": "secmate.read_calendar", "window": window,
                   "resource_id": calendar["id"], **{k: identity[k] for k in ("subject", "connector_owner", "tenant")},
                   "assessment_id": self.binding["assessment_id"], "state_generation": self.binding["state_generation"],
                   "calendar_seed_digest": digest(self.seed), "time_rules_digest": self.rules.digest,
                   "calendar_view_digest": view_digest, "binding_digest": digest(self.binding)}
        validate("CursorContext", context)
        matches = [r for r in visible if r["start_utc"] < window["end_utc"] and r["end_utc"] > window["start_utc"]]
        offset = 0
        if arguments["cursor"] is not None:
            try:
                prefix, text, tag = arguments["cursor"].split(".")
                raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
                payload = bounded_json(raw.decode("utf-8"))
                validate("CursorPayload", payload)
                if prefix != "calcur-v1" or base64.urlsafe_b64encode(raw).decode().rstrip("=") != text or canonical(payload).encode() != raw:
                    raise ValueError("encoding")
                if tag != hashlib.sha256(raw + digest(self.binding).encode("ascii")).hexdigest() or payload["b"] != digest(context):
                    raise ValueError("context")
                offset = payload["o"]
                if offset >= len(matches):
                    raise ValueError("offset")
            except (ValueError, UnicodeError, KeyError, TypeError):
                raise TimeError("invalid_cursor", "/cursor") from None
        selected = matches[offset:offset + arguments["limit"]]
        end = offset + len(selected)
        next_cursor = None
        if end < len(matches):
            payload = canonical({"b": digest(context), "o": end}).encode()
            next_cursor = "calcur-v1." + base64.urlsafe_b64encode(payload).decode().rstrip("=") + "." + hashlib.sha256(payload + digest(self.binding).encode("ascii")).hexdigest()
        output = {"items": [self.item(r) for r in selected], "next_cursor": next_cursor, "truncated": next_cursor is not None}
        validate("CalendarPage", output)
        if len(canonical(output)) > 32000:
            raise SyntheticError("tool_output_limit_exceeded")
        return output, view_digest, calendar["id"]
