# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Composing and sending, over `email.message` and `smtplib`.

Composition and transmission are kept apart on purpose. `compose()` is pure — it
takes a `Draft` and returns an `EmailMessage` and touches no socket — and
`serialize()` produces the transmitted form from that message. `send --dry-run`
prints what `serialize()` returns rather than `as_string()`, so the preview is
the flattened payload rather than a near-miss (see `serialize` for the one
documented divergence).

`Bcc` is set on the draft and removed during serialization, since the header
would otherwise be delivered to every recipient and defeat the point.
"""

from __future__ import annotations

import copy
import email.generator
import io
import mimetypes
import re
import smtplib
import socket
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from typing import Any, Sequence

from ..output import CliError
from .accounts import Account
from .compat import get_addresses, parse_address
from .imap import ssl_context
from .presets import PLAIN, SSL, STARTTLS

DEFAULT_TIMEOUT = 30.0

#: A conservative addr-spec: one @, no whitespace, and none of the characters
#: that separate or delimit addresses in a header. Deliberately stricter than
#: RFC 5321 — quoted local parts like `"a b"@x.com` are legal and rejected here,
#: because an outbound recipient that needs them is far rarer than a mistake
#: that looks like one.
_ADDR_SPEC_RE = re.compile(r"^[^\s<>,;:\"\\]+@[^\s<>,;:\"\\@]+$")


def split_addresses(values: Sequence[str], label: str = "address") -> list[str]:
    """Flatten repeated options and comma-separated lists into one address list.

    `--to a@x --to "b@x, c@x"` and `--to a@x,b@x,c@x` have to mean the same
    thing, because both read naturally and Claude will write both.

    This is also the only place that sees one raw option value before it becomes
    several recipients, so it is where the ambiguity check has to happen. Lenient
    parsing — required for cross-version consistency, see `compat.py` — turns
    `a@x.com <b@evil.com>` into *two* recipients with no comma in sight. That is
    a recipient-smuggling shape rather than a typo, and mail delivered to an
    address the user never saw cannot be recalled, so it is refused rather than
    silently expanded.
    """
    flattened: list[str] = []
    for value in values:
        parsed = [(display, addr) for display, addr in get_addresses([value]) if addr]
        if len(parsed) > 1 and "," not in value:
            raise CliError(
                f"{label} {value!r} is ambiguous: it parses as {len(parsed)} separate "
                f"recipients ({', '.join(addr for _, addr in parsed)}). Separate "
                "addresses with a comma, or pass the option once per recipient.",
                code="ambiguous_address",
            )
        flattened += [
            f"{display} <{addr}>" if display else addr for display, addr in parsed
        ]
    return flattened


def bare_addresses(values: Sequence[str]) -> list[str]:
    """Just the addr-spec parts, which is what the SMTP envelope needs."""
    return [address for _, address in get_addresses(list(values)) if address]


def _validate(values: Sequence[str], label: str) -> None:
    """Check every outbound addr-spec.

    Runs on already-split addresses, so it is the second line of defence behind
    `split_addresses`: it also covers a `Draft` built in Python rather than from
    the command line. Lenient parsing accepts `no-at-sign` as an address, which
    is why the shape is checked explicitly rather than inferred from the parse
    succeeding.
    """
    for entry in values:
        _, address = parse_address(entry)
        if not _ADDR_SPEC_RE.match(address):
            raise CliError(
                f"{label} {entry!r} is not an email address", code="invalid_address"
            )


def serialize(msg: EmailMessage) -> bytes:
    """Flatten a message the way `smtplib.send_message()` will.

    Mirrors the flattening in `SMTP.send_message`, which is what makes
    `send --dry-run` show the transmitted payload rather than a near-miss:
    a `copy` with `Bcc`/`Resent-Bcc` removed, flattened by `BytesGenerator`
    with CRLF line endings.

    **The one divergence, stated rather than hidden:** if any address carries
    non-ASCII and the server advertises SMTPUTF8, `send_message` reflattens with
    a `utf8=True` policy. That depends on a capability only the live server can
    report, so a preview computed without a socket cannot always be byte-exact.
    `needs_smtputf8()` detects that case, and `send --dry-run` reports it in
    `smtputf8` rather than letting the preview quietly overstate itself.
    """
    transmitted = copy.copy(msg)
    del transmitted["Bcc"]
    del transmitted["Resent-Bcc"]
    with io.BytesIO() as buffer:
        email.generator.BytesGenerator(buffer).flatten(transmitted, linesep="\r\n")
        return buffer.getvalue()


def needs_smtputf8(sender: str, recipients: Sequence[str]) -> bool:
    """True when the envelope requires SMTPUTF8, and a preview cannot be exact."""
    try:
        "".join([sender, *recipients]).encode("ascii")
    except UnicodeEncodeError:
        return True
    return False


@dataclass(slots=True)
class Attachment:
    """A file to attach, read from disk at compose time."""

    path: Path
    filename: str
    maintype: str
    subtype: str
    data: bytes

    @classmethod
    def load(cls, path: Path) -> Attachment:
        if not path.is_file():
            raise CliError(f"no such file to attach: {path}", code="attachment_not_found")
        guessed, _ = mimetypes.guess_type(path.name)
        maintype, _, subtype = (guessed or "application/octet-stream").partition("/")
        return cls(
            path=path,
            filename=path.name,
            maintype=maintype,
            subtype=subtype or "octet-stream",
            data=path.read_bytes(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "filename": self.filename,
            "content_type": f"{self.maintype}/{self.subtype}",
            "size": len(self.data),
        }


@dataclass(slots=True)
class Draft:
    """Everything needed to build a message, and nothing about how to send it."""

    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    subject: str = ""
    body: str = ""
    html: str | None = None
    reply_to: str | None = None
    in_reply_to: str | None = None
    references: str | None = None
    attachments: list[Attachment] = field(default_factory=list)
    headers: list[tuple[str, str]] = field(default_factory=list)

    def recipients(self) -> list[str]:
        """The SMTP envelope recipients: To, Cc and Bcc together."""
        return bare_addresses([*self.to, *self.cc, *self.bcc])

    def validate(self) -> None:
        if not self.recipients():
            raise CliError("a message needs at least one recipient (--to)",
                           code="no_recipients")
        _validate(self.to, "--to")
        _validate(self.cc, "--cc")
        _validate(self.bcc, "--bcc")
        if self.reply_to:
            _validate([self.reply_to], "--reply-to")


def compose(account: Account, draft: Draft) -> EmailMessage:
    """Build the message. No sockets, no side effects."""
    draft.validate()

    msg = EmailMessage()
    msg["From"] = account.from_header
    if draft.to:
        msg["To"] = ", ".join(draft.to)
    if draft.cc:
        msg["Cc"] = ", ".join(draft.cc)
    if draft.bcc:
        # Kept on the object so a dry run shows it; stripped in `send`.
        msg["Bcc"] = ", ".join(draft.bcc)
    msg["Subject"] = draft.subject
    msg["Date"] = formatdate(localtime=True)

    domain = account.address.rpartition("@")[2] or None
    msg["Message-ID"] = make_msgid(domain=domain)

    if draft.reply_to:
        msg["Reply-To"] = draft.reply_to
    if draft.in_reply_to:
        msg["In-Reply-To"] = draft.in_reply_to
        # Threading in every mail client depends on References, not just
        # In-Reply-To, so seed it from the parent when the caller did not.
        msg["References"] = draft.references or draft.in_reply_to
    elif draft.references:
        msg["References"] = draft.references

    for name, value in draft.headers:
        msg[name] = value

    msg.set_content(draft.body or "")
    if draft.html:
        msg.add_alternative(draft.html, subtype="html")

    for attachment in draft.attachments:
        msg.add_attachment(
            attachment.data,
            maintype=attachment.maintype,
            subtype=attachment.subtype,
            filename=attachment.filename,
        )
    return msg


def _open(account: Account, timeout: float) -> smtplib.SMTP:
    endpoint = account.outgoing
    context = ssl_context(account.insecure_tls)
    if endpoint.security == SSL:
        return smtplib.SMTP_SSL(
            endpoint.host, endpoint.port, timeout=timeout, context=context
        )

    conn = smtplib.SMTP(endpoint.host, endpoint.port, timeout=timeout)
    conn.ehlo()
    if endpoint.security == STARTTLS:
        conn.starttls(context=context)
        # The capability list is renegotiated after the upgrade; AUTH is
        # usually only advertised once the channel is encrypted.
        conn.ehlo()
    elif endpoint.security != PLAIN:  # pragma: no cover - validated upstream
        raise CliError(f"unknown security mode {endpoint.security!r}",
                       code="invalid_security")
    return conn


def send(account: Account, password: str, msg: EmailMessage,
         recipients: Sequence[str], *, timeout: float = DEFAULT_TIMEOUT
         ) -> dict[str, Any]:
    """Send a composed message, returning what the server said.

    `recipients` is the envelope, taken from the draft rather than re-derived
    from headers, so Bcc recipients still receive their copy. `send_message`
    flattens a local copy with `Bcc` removed, so the message handed in keeps its
    Bcc header and can still be filed to Sent intact.
    """
    endpoint = account.outgoing
    try:
        conn = _open(account, timeout)
    except smtplib.SMTPException as error:
        raise CliError(
            f"SMTP handshake failed at {endpoint.describe()}: {error}",
            code="connection_failed",
        ) from error
    except (OSError, socket.timeout, ssl.SSLError) as error:
        raise CliError(
            f"cannot reach SMTP at {endpoint.describe()}: {error}",
            code="connection_failed",
        ) from error

    try:
        try:
            conn.login(account.username, password)
        except smtplib.SMTPNotSupportedError:
            # Some relays (a local MTA, Proton Bridge on plain) accept mail
            # without authentication. Only tolerated when the server itself
            # says AUTH is not offered.
            pass
        except smtplib.SMTPAuthenticationError as error:
            raise CliError(
                f"SMTP authentication rejected for {account.username!r} at "
                f"{endpoint.host}: {error.smtp_code} {error.smtp_error!r}. Many "
                "providers require an app-specific password here.",
                code="login_failed",
            ) from error

        try:
            refused = conn.send_message(
                msg, from_addr=account.address, to_addrs=list(recipients)
            )
        except smtplib.SMTPRecipientsRefused as error:
            raise CliError(
                f"every recipient was refused: {error.recipients}",
                code="recipients_refused",
            ) from error
        except smtplib.SMTPSenderRefused as error:
            raise CliError(
                f"the server refused {error.sender!r} as the sender: "
                f"{error.smtp_code} {error.smtp_error!r}. It usually has to match "
                "the authenticated account.",
                code="sender_refused",
            ) from error
        except smtplib.SMTPException as error:
            raise CliError(f"SMTP send failed: {error}", code="smtp_error") from error
    finally:
        try:
            conn.quit()
        except (smtplib.SMTPException, OSError):  # pragma: no cover - teardown noise
            pass

    return {
        "message_id": str(msg.get("Message-ID", "")),
        "accepted": [r for r in recipients if r not in refused],
        "refused": {addr: list(detail) for addr, detail in refused.items()},
    }
