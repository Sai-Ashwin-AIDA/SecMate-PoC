from email.message import EmailMessage
from email.policy import SMTP

import pytest

from local_document_agent.contracts import DocumentError
from local_document_agent.filesystem import RAW_LIMIT
from local_document_agent.text import extract


def test_utf8_bom_and_normalized_text():
    result = extract(b"\xef\xbb\xbfalpha\r\nbeta\rgamma\n", ".md")
    assert result.text == "alpha\nbeta\ngamma\n"
    assert result.kind == "markdown"
    assert result.representation == "normalized_text"


@pytest.mark.parametrize("raw,code", [(b"\xff", "DECODE_ERROR"), (b"text\x00binary", "UNSUPPORTED_TYPE")])
def test_invalid_or_binary_text(raw, code):
    with pytest.raises(DocumentError) as error:
        extract(raw, ".txt")
    assert error.value.error.code == code


def test_valid_utf8_replacement_character_is_preserved():
    assert extract("Already contains \ufffd.".encode("utf-8"), ".txt").text == "Already contains \ufffd."


def test_plain_email_alternative_and_attachments_not_extracted():
    message = EmailMessage()
    message["From"] = "sender@example.invalid"
    message["To"] = "reader@example.invalid"
    message["Subject"] = "Review"
    message.set_content("Tuesday review.\n")
    message.add_alternative("<p>HTML_PRIVATE_MARKER</p>", subtype="html")
    message.add_attachment(
        b"ATTACHMENT_PRIVATE_MARKER", maintype="application", subtype="octet-stream", filename="notes.bin"
    )
    result = extract(message.as_bytes(policy=SMTP), ".eml")
    assert "Subject: Review" in result.text
    assert "Tuesday review." in result.text
    assert "HTML_PRIVATE_MARKER" not in result.text
    assert "ATTACHMENT_PRIVATE_MARKER" not in result.text
    assert len(result.warnings) == 2
    assert result.representation == "extracted_email"


@pytest.mark.parametrize("raw,code", [
    (b"Content-Type: text/html\r\n\r\n<p>private</p>", "HTML_ONLY_EMAIL"),
    (b"Content-Type: application/pdf\r\n\r\nprivate", "NO_READABLE_CONTENT"),
    (b"Content-Type: multipart/mixed; boundary=missing\r\n\r\nbad", "MALFORMED_EMAIL"),
    (b"not a header\r\n\r\nbody", "MALFORMED_EMAIL"),
    (b"Content-Type: text/plain; charset=not-a-codec\r\n\r\nbody", "DECODE_ERROR"),
    (b"Content-Type: text/plain\r\nContent-Transfer-Encoding: base64\r\n\r\n!!!!", "MALFORMED_EMAIL"),
    (b"Content-Type: text/plain\r\nContent-Transfer-Encoding: quoted-printable\r\n\r\nbad=QQ", "MALFORMED_EMAIL"),
])
def test_unavailable_email_content_fails_without_body(raw, code):
    with pytest.raises(DocumentError) as error:
        extract(raw, ".eml")
    assert error.value.error.code == code
    assert "private" not in str(error.value)


def test_raw_and_decoded_email_size_limits():
    with pytest.raises(DocumentError) as error:
        extract(b"x" * (RAW_LIMIT + 1), ".txt")
    assert error.value.error.code == "FILE_TOO_LARGE"
    raw = (
        b"Content-Type: text/plain; charset=iso-8859-1\r\nContent-Transfer-Encoding: 8bit\r\n\r\n"
        + b"\xe9" * 140_000
    )
    with pytest.raises(DocumentError) as error:
        extract(raw, ".eml")
    assert error.value.error.code == "EXTRACTED_TEXT_TOO_LARGE"
