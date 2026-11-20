"""Strict bounded UTF-8 and standard-library plain-text email extraction."""

import codecs
import re
from dataclasses import dataclass
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Literal

from .contracts import DocumentError
from .filesystem import RAW_LIMIT


@dataclass(frozen=True)
class ExtractedText:
    kind: Literal["text", "markdown", "email"]
    representation: Literal["normalized_text", "extracted_email"]
    text: str
    warnings: tuple[str, ...] = ()


def normalize(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def decode(data: bytes, charset: str = "utf-8-sig") -> str:
    try:
        # Restrict codecs to actual text encodings, not arbitrary codec transforms.
        codecs.lookup(charset)
        result = data.decode(charset, errors="strict")
        return normalize(result)
    except (LookupError, UnicodeError, ValueError):
        raise DocumentError("DECODE_ERROR", "Text decoding failed; convert a copy to valid UTF-8.") from None


def email_text(raw: bytes) -> ExtractedText:
    try:
        message = BytesParser(policy=policy.default).parsebytes(raw)
    except (ValueError, TypeError, IndexError, RecursionError):
        raise DocumentError("MALFORMED_EMAIL", "The email could not be parsed reliably.") from None
    bodies: list[str] = []
    attachment_count = 0
    html_count = 0
    part_count = 0
    headers: list[str] = []
    warnings: list[str] = []

    def visit(part: EmailMessage, depth: int = 0) -> None:
        nonlocal attachment_count, html_count, part_count
        part_count += 1
        if part_count > 200 or depth > 20:
            raise DocumentError("MALFORMED_EMAIL", "The email MIME structure is too complex.")
        if part.defects:
            raise DocumentError("MALFORMED_EMAIL", "The email contains parser defects.")
        for name in ("Content-Type", "Content-Transfer-Encoding", "Content-Disposition", "MIME-Version"):
            if len(part.get_all(name, [])) > 1:
                raise DocumentError("MALFORMED_EMAIL", "The email has ambiguous duplicate MIME headers.")
        # Validate declared encoded-word charsets before HeaderRegistry silently
        # falls back to ASCII/replacement decoding for an unknown charset.
        for _, raw_header in part.raw_items():
            for match in re.finditer(r"=\?([^?]+)\?[bBqQ]\?[^?]*\?=", raw_header):
                try:
                    codecs.lookup(match.group(1))
                    for chunk, charset in decode_header(match.group(0)):
                        if isinstance(chunk, bytes):
                            chunk.decode(charset or "ascii", errors="strict")
                except (LookupError, UnicodeError, ValueError):
                    raise DocumentError("MALFORMED_EMAIL", "An encoded email header cannot be decoded reliably.") from None
        # Accessing structured headers exposes additional header defects.
        for name in part.keys():
            for header in part.get_all(name, []):
                if getattr(header, "defects", ()) or "\ufffd" in str(header):
                    raise DocumentError("MALFORMED_EMAIL", "The email contains malformed headers.")
        if part.get_content_disposition() == "attachment" or part.get_filename() is not None:
            attachment_count += 1
            return
        if part.get_content_type() == "message/rfc822":
            attachment_count += 1
            return
        if part.is_multipart():
            for child in part.iter_parts():
                visit(child, depth + 1)
            return
        if part.get_content_type() == "text/html":
            html_count += 1
            return
        if part.get_content_type() != "text/plain":
            attachment_count += 1
            return
        transfer = (part.get("Content-Transfer-Encoding") or "7bit").lower()
        if transfer not in ("7bit", "8bit", "binary", "base64", "quoted-printable"):
            raise DocumentError("MALFORMED_EMAIL", "Unsupported email transfer encoding.")
        payload_text = part.get_payload()
        if not isinstance(payload_text, str):
            raise DocumentError("MALFORMED_EMAIL", "The email body is unavailable.")
        if transfer == "quoted-printable" and re.search(r"=(?![0-9A-Fa-f]{2}|\r?\n)", payload_text):
            raise DocumentError("MALFORMED_EMAIL", "The email transfer encoding is malformed.")
        payload = part.get_payload(decode=True)
        if part.defects or not isinstance(payload, bytes):
            raise DocumentError("MALFORMED_EMAIL", "The email transfer encoding is malformed.")
        if transfer == "7bit" and any(byte > 127 for byte in payload):
            raise DocumentError("MALFORMED_EMAIL", "The email declares invalid 7bit content.")
        body = decode(payload, part.get_content_charset() or "utf-8")
        if body.strip():
            bodies.append(body)

    try:
        visit(message)
        for name in ("From", "To", "Cc", "Subject", "Date"):
            if message.get(name) is not None:
                headers.append(f"{name}: {message[name]}")
    except DocumentError:
        raise
    except (ValueError, TypeError, IndexError, UnicodeError, LookupError, RecursionError):
        raise DocumentError("MALFORMED_EMAIL", "The email could not be extracted reliably.") from None
    if not bodies:
        if html_count:
            raise DocumentError("HTML_ONLY_EMAIL", "The email has no supported plain-text body; HTML was not read.")
        raise DocumentError("NO_READABLE_CONTENT", "The email has no readable inline plain-text body.")
    body = bodies[0] if len(bodies) == 1 else "\n\n".join(
        f"--- Plain-text part {index} ---\n{text}" for index, text in enumerate(bodies, 1)
    )
    if attachment_count:
        warnings.append(f"{attachment_count} attachment(s) omitted; payloads were not extracted.")
    if html_count:
        warnings.append(f"{html_count} HTML part(s) omitted; HTML was not read.")
    text = "\n".join(headers) + "\n\n" + body
    if warnings:
        text += "\n\n[Extraction notice: " + " ".join(warnings) + "]"
    return ExtractedText("email", "extracted_email", normalize(text), tuple(warnings))


def extract(raw: bytes, suffix: str) -> ExtractedText:
    if len(raw) > RAW_LIMIT:
        raise DocumentError("FILE_TOO_LARGE", "The raw file exceeds 256 KiB.")
    suffix = suffix.casefold()
    if suffix == ".eml":
        result = email_text(raw)
    elif suffix in (".txt", ".md"):
        if b"\x00" in raw:
            raise DocumentError("UNSUPPORTED_TYPE", "NUL-containing binary-like text is unsupported.")
        result = ExtractedText(
            "markdown" if suffix == ".md" else "text", "normalized_text", decode(raw)
        )
    else:
        raise DocumentError("UNSUPPORTED_TYPE", "Only .txt, .md, and .eml files are supported.")
    try:
        size = len(result.text.encode("utf-8"))
    except UnicodeError:
        raise DocumentError("DECODE_ERROR", "The extracted text is not valid UTF-8.") from None
    if size > RAW_LIMIT:
        raise DocumentError("EXTRACTED_TEXT_TOO_LARGE", "The extracted UTF-8 text exceeds 256 KiB.")
    return result
