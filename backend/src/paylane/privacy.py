"""Shared sensitive-data projection; never log raw credential inputs."""

import re

EMAIL = re.compile(
    r"\b[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
PAN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
LAST4 = re.compile(r"(?<![\w-])\d{4}(?![\w-])")


SECRET = re.compile(
    r"(?i)(?:sk-or-v1-[a-z0-9]{16,}|sk-[a-z0-9_-]{20,}|bearer\s+[a-z0-9._-]{16,}|(?:password|cvv|otp)\s*(?::|=|\bis\b|\s)\s*[^\s,;]{3,})"
)


def scrub_input(text):
    return SECRET.sub("[credential redacted]", PAN.sub("[card redacted]", text))


def redact(text):
    text = SECRET.sub("[credential redacted]", str(text))
    text = EMAIL.sub("[email redacted]", text)
    text = PAN.sub("[card redacted]", text)
    return LAST4.sub("[last four redacted]", text)


def sanitize(value):
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return redact(value) if isinstance(value, str) else value
