"""Redact sensitive text in advisory model output before local persistence."""
import os
import re


def redact_advisory_output(value):
    if isinstance(value, list):
        return [redact_advisory_output(item) for item in value]
    if isinstance(value, dict):
        return {key: redact_advisory_output(item) for key, item in value.items()}
    if not isinstance(value, str):
        return value
    for name, secret in os.environ.items():
        if secret and re.search(r"(?i)(key|token|secret|password|credential)", name):
            value = value.replace(secret, "<redacted>")
    for pattern in (
        r"(?i)(?:gsk_|sk-or-v1-|sk-(?:proj-)?)[a-z0-9_-]{8,}",
        r"AKIA[0-9A-Z]{16}", r"(?i)(?:gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,})",
        r"(?i)(?:authorization|proxy-authorization)\s*:\s*(?:basic|bearer)\s+\S+",
        r"(?i)bearer\s+[a-z0-9._-]{12,}", r"(?i)[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}",
        r"\beyJ[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\.[a-zA-Z0-9_-]{10,}\b",
        r"(?s)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r'''(?i)["']?(?:password|passwd|secret|token|credential|authorization|api[_-]?key|access[_-]?key|client[_-]?secret|private[_-]?key|connection[_-]?string)["']?\s*[:=]\s*(?:"[^"]{6,}"|'[^']{6,}'|[^\s,;}{]{6,})''',
    ):
        value = re.sub(pattern, "<redacted>", value)
    return value
