"""PII redaction before embed / LLM / storage.

Strips emails, phone numbers, and account-style identifiers from free text
so they are not embedded, sent to Ollama, or persisted in ticket rows.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)

# +1 555-123-4567, (555) 123-4567, 555.123.4567, 5551234567
PHONE_RE = re.compile(
    r"(?<!\w)"
    r"(?:\+?\d{1,3}[\s\-.]*)?"
    r"(?:\(?\d{3}\)?[\s\-.]*)\d{3}[\s\-.]*\d{4}"
    r"(?!\w)"
)

# account ID ACC-998877, acct:AB-99881, customer id CUS_12345
ACCOUNT_ID_RE = re.compile(
    r"\b(?:"
    r"(?:account|acct|customer|cust|member)\s*"
    r"(?:id|number|no\.?|#)\s*[:=#\-]?\s*"
    r"[A-Za-z0-9][A-Za-z0-9\-_]{3,}"
    r"|"
    r"(?:account|acct)\s*[:=#]\s*[A-Za-z0-9][A-Za-z0-9\-_]{4,}"
    r"|"
    r"(?:ACC|ACCT|CUS|CUST|UID)[-_][A-Za-z0-9]{4,}"
    r")\b",
    re.IGNORECASE,
)

PLACEHOLDERS = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "account_id": "[ACCOUNT_ID]",
}


@dataclass
class RedactionResult:
    """Outcome of running ``redact_pii`` on a string."""

    text: str
    redacted: bool = False
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sub_count(pattern: re.Pattern[str], text: str, placeholder: str) -> tuple[str, int]:
    count = 0

    def _repl(_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return placeholder

    return pattern.sub(_repl, text), count


def redact_pii(text: str | None) -> RedactionResult:
    """Replace emails, phones, and account IDs with stable placeholders."""
    if text is None:
        return RedactionResult(text="", redacted=False, counts={})

    original = str(text)
    working = original
    counts: dict[str, int] = {}

    working, n = _sub_count(EMAIL_RE, working, PLACEHOLDERS["email"])
    if n:
        counts["email"] = n

    working, n = _sub_count(PHONE_RE, working, PLACEHOLDERS["phone"])
    if n:
        counts["phone"] = n

    working, n = _sub_count(ACCOUNT_ID_RE, working, PLACEHOLDERS["account_id"])
    if n:
        counts["account_id"] = n

    return RedactionResult(
        text=working,
        redacted=bool(counts),
        counts=counts,
    )


def redact_text(text: str | None) -> str:
    """Convenience wrapper returning only the redacted string."""
    return redact_pii(text).text


def merge_counts(*count_maps: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for cmap in count_maps:
        for key, value in (cmap or {}).items():
            out[key] = out.get(key, 0) + int(value)
    return out


def redact_chat_history(
    history: list[dict[str, str]] | None,
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Return a copy of chat messages with PII stripped from content."""
    if not history:
        return [], {}
    cleaned: list[dict[str, str]] = []
    totals: dict[str, int] = {}
    for msg in history:
        item = dict(msg)
        result = redact_pii(item.get("content"))
        item["content"] = result.text
        totals = merge_counts(totals, result.counts)
        cleaned.append(item)
    return cleaned, totals


def redact_ticket_fields(ticket: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Redact description/resolution on a ticket dict (copy)."""
    out = dict(ticket)
    totals: dict[str, int] = {}
    for key in ("description", "resolution"):
        if key in out and out[key] is not None:
            result = redact_pii(str(out[key]))
            out[key] = result.text
            totals = merge_counts(totals, result.counts)
    return out, totals


def redact_tickets(
    tickets: list[dict[str, Any]] | None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not tickets:
        return [], {}
    cleaned: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    for ticket in tickets:
        row, counts = redact_ticket_fields(ticket)
        cleaned.append(row)
        totals = merge_counts(totals, counts)
    return cleaned, totals
