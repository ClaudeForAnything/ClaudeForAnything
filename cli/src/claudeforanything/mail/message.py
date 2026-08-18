# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Turning RFC 5322 bytes into plain dictionaries, and back.

Real mail is hostile: MIME nested four deep, headers RFC 2047-encoded in three
charsets, `Content-Type` lying about the encoding, bodies that decode to
mojibake. `email.policy.default` handles most of it; the rest is handled here,
and every extractor degrades to something printable rather than raising, because
a CLI that dies on one malformed message in an inbox of two thousand is useless.
"""

from __future__ import annotations

import email
import email.policy
import mimetypes
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from email.utils import getaddresses, parsedate_to_datetime
from typing import Any, Iterable

#: `default` gives us EmailMessage with decoded headers and get_body(). `compat32`
#: would hand back raw encoded-words, which is exactly what we do not want.
POLICY = email.policy.default

ADDRESS_HEADERS = ("from", "to", "cc", "bcc", "reply-to")

SUMMARY_HEADERS = (
    "FROM",
    "TO",
    "CC",
    "BCC",
    "SUBJECT",
    "DATE",
    "MESSAGE-ID",
    "REPLY-TO",
    "IN-REPLY-TO",
    "REFERENCES",
    "LIST-ID",
    "CONTENT-TYPE",
)


def parse(raw: bytes) -> EmailMessage:
    """Parse message bytes, tolerating malformed input."""
    parsed = email.message_from_bytes(raw, policy=POLICY)
    # message_from_bytes is typed as Message; policy=default makes it an
    # EmailMessage, which is what get_body/iter_attachments live on.
    return parsed  # type: ignore[return-value]


def parse_headers(raw: bytes) -> EmailMessage:
    """Parse a header-only blob, such as an IMAP BODY[HEADER.FIELDS (...)] part."""
    if not raw.endswith((b"\r\n\r\n", b"\n\n")):
        raw = raw.rstrip(b"\r\n") + b"\r\n\r\n"
    return parse(raw)


def header(msg: EmailMessage, name: str, default: str = "") -> str:
    """Read one header as a decoded string, whatever the source encoding."""
    value = msg.get(name)
    if value is None:
        return default
    try:
        text = str(value)
    except Exception:  # pragma: no cover - defective header objects
        return default
    return " ".join(text.split())


def addresses(msg: EmailMessage, name: str) -> list[dict[str, str]]:
    """Return [{name, address}] for an address header, empty when absent."""
    values = msg.get_all(name)
    if not values:
        return []
    try:
        pairs = getaddresses([str(v) for v in values], strict=False)
    except Exception:  # pragma: no cover - defective header objects
        return []
    return [
        {"name": " ".join(display.split()), "address": addr}
        for display, addr in pairs
        if display or addr
    ]


def address_line(msg: EmailMessage, name: str) -> str:
    """A one-line rendering of an address header, for tables."""
    parts = addresses(msg, name)
    return ", ".join(entry["name"] or entry["address"] for entry in parts)


def sent_at(msg: EmailMessage) -> datetime | None:
    """The Date: header as a datetime, or None when it is missing or garbage."""
    raw = msg.get("Date")
    if raw is None:
        return None
    try:
        return parsedate_to_datetime(str(raw))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class Attachment:
    """One attachment, described without loading twice."""

    index: int
    filename: str
    content_type: str
    size: int
    content_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "filename": self.filename,
            "content_type": self.content_type,
            "size": self.size,
            "content_id": self.content_id,
        }


def _part_bytes(part: EmailMessage) -> bytes:
    try:
        payload = part.get_payload(decode=True)
    except Exception:  # pragma: no cover - broken transfer encoding
        payload = None
    if isinstance(payload, bytes):
        return payload
    return b""


def _fallback_name(index: int, content_type: str) -> str:
    extension = mimetypes.guess_extension(content_type) or ".bin"
    return f"part-{index}{extension}"


def attachments(msg: EmailMessage) -> list[Attachment]:
    """List attachments in order. Index is stable for a given message."""
    found: list[Attachment] = []
    for index, part in enumerate(msg.iter_attachments(), start=1):
        if not isinstance(part, EmailMessage):  # pragma: no cover - compat32 parts
            continue
        content_type = part.get_content_type()
        name = part.get_filename() or _fallback_name(index, content_type)
        cid = part.get("Content-ID")
        found.append(
            Attachment(
                index=index,
                filename=name,
                content_type=content_type,
                size=len(_part_bytes(part)),
                content_id=str(cid).strip("<>") if cid else None,
            )
        )
    return found


def attachment_bytes(msg: EmailMessage, selector: str) -> tuple[str, bytes]:
    """Return (filename, data) for an attachment picked by 1-based index or name."""
    parts = [p for p in msg.iter_attachments() if isinstance(p, EmailMessage)]
    listed = attachments(msg)

    if selector.isdigit():
        wanted = int(selector)
        for meta, part in zip(listed, parts):
            if meta.index == wanted:
                return meta.filename, _part_bytes(part)
        raise KeyError(selector)

    for meta, part in zip(listed, parts):
        if meta.filename == selector:
            return meta.filename, _part_bytes(part)
    raise KeyError(selector)


def _decode(part: EmailMessage) -> str:
    """Best-effort text of one part, never raising on a bad charset."""
    try:
        content = part.get_content()
    except (LookupError, UnicodeDecodeError, KeyError):
        content = None
    if isinstance(content, str):
        return content
    payload = _part_bytes(part)
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except LookupError:
        return payload.decode("utf-8", errors="replace")


def body_text(msg: EmailMessage) -> str:
    """The text/plain body, or '' when the message only carries HTML."""
    part = msg.get_body(preferencelist=("plain",))
    return _decode(part) if isinstance(part, EmailMessage) else ""


def body_html(msg: EmailMessage) -> str:
    """The text/html body, or ''."""
    part = msg.get_body(preferencelist=("html",))
    return _decode(part) if isinstance(part, EmailMessage) else ""


def html_to_text(html: str) -> str:
    """A crude HTML-to-text fallback for messages with no text/plain part.

    Deliberately not a parser: strip scripts, turn block ends into newlines,
    drop the remaining tags, unescape entities. Good enough for Claude to read
    the content of an HTML-only newsletter, and it pulls in no dependency.
    """
    import html as html_mod
    import re

    text = re.sub(r"(?is)<(script|style|head)\b.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6]|table|blockquote)\s*>", "\n\n", text)
    text = re.sub(r"(?i)<li\b[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html_mod.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def readable_body(msg: EmailMessage) -> tuple[str, str]:
    """Return (text, source): the plain body if there is one, else HTML stripped."""
    text = body_text(msg)
    if text.strip():
        return text, "text/plain"
    html = body_html(msg)
    if html.strip():
        return html_to_text(html), "text/html (stripped)"
    return "", "none"


def summarize(msg: EmailMessage, *, uid: str | None = None,
              flags: Iterable[str] = (), size: int | None = None,
              folder: str | None = None) -> dict[str, Any]:
    """The one-line-per-message shape used by `inbox` and `search`."""
    when = sent_at(msg)
    return {
        "uid": uid,
        "folder": folder,
        "date": when.isoformat() if when else None,
        "from": address_line(msg, "From"),
        "from_addresses": addresses(msg, "From"),
        "to": address_line(msg, "To"),
        "subject": header(msg, "Subject"),
        "message_id": header(msg, "Message-ID") or None,
        "flags": list(flags),
        # A header-only fetch cannot see the MIME tree, so this is the same
        # approximation IMAP forces on a "has attachment" search: true for
        # multipart/mixed, which misses inline parts in multipart/related.
        # `detail()` replaces it with the real list.
        "likely_attachment": header(msg, "Content-Type").lower().startswith("multipart/mixed"),
        "seen": "\\Seen" in flags,
        "answered": "\\Answered" in flags,
        "flagged": "\\Flagged" in flags,
        "size": size,
    }


def detail(msg: EmailMessage, *, uid: str | None = None, flags: Iterable[str] = (),
           size: int | None = None, folder: str | None = None,
           max_chars: int | None = None) -> dict[str, Any]:
    """The full shape used by `read`: headers, both bodies, attachment list."""
    text, source = readable_body(msg)
    truncated = False
    if max_chars is not None and max_chars > 0 and len(text) > max_chars:
        text = text[:max_chars]
        truncated = True

    data = summarize(msg, uid=uid, flags=flags, size=size, folder=folder)
    data.update(
        {
            "cc": address_line(msg, "Cc"),
            "reply_to": address_line(msg, "Reply-To"),
            "to_addresses": addresses(msg, "To"),
            "cc_addresses": addresses(msg, "Cc"),
            "in_reply_to": header(msg, "In-Reply-To") or None,
            "references": header(msg, "References") or None,
            "list_id": header(msg, "List-Id") or None,
            "body": text,
            "body_source": source,
            "body_truncated": truncated,
            "has_html": bool(body_html(msg).strip()),
            "attachments": [a.to_dict() for a in attachments(msg)],
        }
    )
    return data
