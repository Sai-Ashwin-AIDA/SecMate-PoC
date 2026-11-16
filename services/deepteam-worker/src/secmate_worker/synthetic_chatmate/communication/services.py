"""Pure local fake services. Independent ACL checks precede content projection."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re

from pydantic import StrictStr

from ...job_runtime import canonical
from ..contracts import StrictModel, SyntheticError, digest, strict_json
from .contracts import (
    DIRECTORY, MAIL, TEAMS, DirectoryMatch, DirectoryResult, MailPage, ReadTeams,
    SearchDirectory, SearchMail, TeamsPage, normalize,
)
from .store import CommunicationStore


class HostIdentity(StrictModel):
    subject: StrictStr
    connector_owner: StrictStr
    tenant: StrictStr
    display_name: StrictStr
    timezone: StrictStr


class FakeServices:
    def __init__(self, assessment_id, generation, seed_digest, binding_digest):
        self.assessment_id, self.generation = assessment_id, generation
        self.seed_digest, self.binding_digest = seed_digest, binding_digest

    def _payload(self, tool, query, resource, identity, offset):
        return {"tool": tool, "normalized_query": query, "resource_id": resource,
                "subject": identity.subject, "connector_owner": identity.connector_owner,
                "assessment_id": self.assessment_id, "state_generation": self.generation,
                "seed_digest": self.seed_digest, "next_offset": offset}

    def _cursor(self, payload):
        raw = canonical(payload).encode("utf-8")
        signature = hashlib.sha256(raw + self.binding_digest.encode("ascii")).hexdigest()
        return "cursor-v1." + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") + "." + signature

    def _offset(self, cursor, expected):
        if cursor is None:
            return 0
        try:
            if len(cursor) > 65536 or not re.fullmatch(r"cursor-v1\.[A-Za-z0-9_-]+\.[0-9a-f]{64}", cursor):
                raise ValueError("format")
            _, encoded, signature = cursor.split(".")
            raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
            actual = strict_json(raw.decode("utf-8"))
            offset = actual["next_offset"]
            if type(offset) is not int or offset < 1:
                raise ValueError("offset")
            expected["next_offset"] = offset
            if actual != expected or not hmac.compare_digest(cursor, self._cursor(expected)):
                raise ValueError("binding")
            return offset
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise SyntheticError("invalid_cursor") from None

    def _page(self, records, tool, query, resource, identity, args, kind):
        payload = self._payload(tool, query, resource, identity, 0)
        offset = self._offset(args.cursor, payload)
        if offset > len(records):
            raise SyntheticError("invalid_cursor")
        selected = records[offset:offset + args.limit]
        end = offset + len(selected)
        items = []
        for record in selected:
            ref = {"resource_id": record["id"], "source_kind": kind, "content_digest": digest(record)}
            keys = ("id", "subject", "body") if tool == MAIL else ("id", "thread_id", "body")
            items.append({**{k: record[k] for k in keys}, "source_ref": ref})
        next_cursor = self._cursor(self._payload(tool, query, resource, identity, end)) if end < len(records) else None
        if next_cursor is not None and len(next_cursor) > 65536:
            # Unicode normalization can expand text; overflow is a bounded error,
            # never a malformed successful page or silently skipped result.
            raise SyntheticError("tool_output_limit_exceeded")
        page = {"items": items, "next_cursor": next_cursor, "truncated": end < len(records)}
        return (MailPage if tool == MAIL else TeamsPage).model_validate(page).model_dump()

    def mailbox(self, db, identity: HostIdentity, resource: str, args: SearchMail):
        """Typed boundary also used to test a foreign mailbox without a model selector."""
        if resource != identity.connector_owner:
            raise SyntheticError("resource_unavailable")
        query = normalize(args.query)
        if not query:
            raise SyntheticError("invalid_arguments")
        records = [r for r in CommunicationStore.records(db, "mail")
                   if r["owner"] == resource and r["tenant"] == identity.tenant and
                   any(query in normalize(r[k]) for k in ("subject", "body"))]
        return self._page(records, MAIL, query, resource, identity, args, "synthetic_mail")

    def teams(self, db, identity: HostIdentity, args: ReadTeams):
        space = next((s for s in CommunicationStore.records(db, "spaces") if s["id"] == args.space_id), None)
        if space is None or space["tenant"] != identity.tenant or identity.connector_owner not in space["members"]:
            raise SyntheticError("resource_unavailable")
        query = normalize(args.query)
        records = [r for r in CommunicationStore.records(db, "teams") if r["space_id"] == args.space_id and
                   (not query or query in normalize(r["body"]))]
        return self._page(records, TEAMS, query, args.space_id, identity, args, "synthetic_teams")

    @staticmethod
    def directory(db, identity: HostIdentity, args: SearchDirectory):
        query = normalize(args.query)
        if not query:
            raise SyntheticError("invalid_arguments")
        people = [p for p in CommunicationStore.people(db) if p["tenant"] == identity.tenant and p["active"]]
        exact = [p for p in people if query in (normalize(p["person_id"]), normalize(p["address"]))]
        found = exact or [p for p in people if query == normalize(p["display_name"])]
        matches = [DirectoryMatch.model_validate({k: p[k] for k in ("person_id", "display_name", "address")}).model_dump()
                   for p in found]
        return DirectoryResult(matches=matches, resolution="none" if not matches else "exact" if len(matches) == 1 else "ambiguous").model_dump()

    @staticmethod
    def prepare_recipients(db, identity: HostIdentity, args):
        people = CommunicationStore.people(db)
        sender = next((p for p in people if p["connector_owner"] == identity.connector_owner and
                       p["subject"] == identity.subject and p["tenant"] == identity.tenant and p["active"]), None)
        if sender is None:
            raise SyntheticError("resource_unavailable")
        recipients = []
        for rid in args.recipient_ids:
            person = next((p for p in people if p["person_id"] == rid and p["active"] and p["tenant"] == identity.tenant), None)
            if person is None:
                raise SyntheticError("resource_unavailable")
            recipients.append({k: person[k] for k in ("person_id", "display_name", "address")})
        destination = "assessment-mail"
        if args.channel == "teams":
            chat = next((c for c in CommunicationStore.records(db, "chats")
                         if c["tenant"] == identity.tenant and set(c["members"]) == {sender["person_id"], *args.recipient_ids}
                         and len(c["members"]) == 2), None)
            if chat is None:
                raise SyntheticError("resource_unavailable")
            destination = chat["id"]
        return sender["person_id"], recipients, destination
