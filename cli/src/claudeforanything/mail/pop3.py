# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""POP3, over `poplib`, for accounts that offer nothing better.

POP3 is a strictly smaller protocol than IMAP and the difference matters here:
there is exactly one mailbox, no flags, no server-side search, and no stable UID
unless the server implements the optional UIDL command. Every listing therefore
downloads headers one message at a time, which is why `inbox` on a POP3 account
is slow and takes a hard `--limit`.

Deleting is also different: DELE only marks, and the deletions are committed
when QUIT succeeds. `rset()` on the way out of a read-only session is what keeps
an interrupted listing from destroying mail.
"""

from __future__ import annotations

import poplib
import socket
import ssl
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Generator, Sequence

from ..output import CliError
from . import message as message_mod
from .accounts import Account
from .imap import ssl_context
from .presets import PLAIN, SSL, STARTTLS

DEFAULT_TIMEOUT = 30.0

#: `poplib` refuses any line longer than its module-level `_MAXLINE`, which is
#: 2048 bytes. RFC 5322 keeps lines under 998, so conforming mail is fine — but
#: plenty of real senders emit one enormous unwrapped header or body line, and
#: the failure mode is `error_proto('line too long')` on an otherwise readable
#: message. There is no per-instance knob, so the module constant is what has to
#: be raised.
MAX_LINE = 1 << 20
poplib._MAXLINE = MAX_LINE  # type: ignore[attr-defined]


@dataclass(frozen=True, slots=True)
class Pop3Message:
    """One message in the maildrop."""

    number: int
    uid: str
    size: int


class Pop3:
    """A logged-in POP3 session. Build it with `connect()`."""

    def __init__(self, conn: poplib.POP3, account: Account) -> None:
        self._conn = conn
        self.account = account
        self._dirty = False

    def capabilities(self) -> dict[str, list[str]]:
        try:
            return self._conn.capa()
        except poplib.error_proto:
            return {}

    def listing(self) -> list[Pop3Message]:
        """Every message in the maildrop, oldest first.

        UIDL is optional. When the server does not implement it the message
        number is used as the identifier, and it is only stable until the next
        deletion — which is why `delete` warns on such servers.
        """
        try:
            _, lines, _ = self._conn.list()
        except poplib.error_proto as error:
            raise CliError(f"POP3 LIST failed: {error}", code="pop3_error") from error

        sizes: dict[int, int] = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit():
                sizes[int(parts[0])] = int(parts[1]) if parts[1].isdigit() else 0

        uids: dict[int, str] = {}
        try:
            _, uid_lines, _ = self._conn.uidl()
            for line in uid_lines:
                parts = line.split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    uids[int(parts[0])] = parts[1].decode("ascii", "replace")
        except poplib.error_proto:
            pass

        return [
            Pop3Message(number=number, uid=uids.get(number, str(number)), size=size)
            for number, size in sorted(sizes.items())
        ]

    def headers(self, number: int, lines: int = 0) -> bytes:
        """Fetch a message's headers with TOP, falling back to a full RETR."""
        try:
            _, raw, _ = self._conn.top(number, lines)
        except poplib.error_proto:
            return self.retrieve(number)
        return b"\r\n".join(raw)

    def retrieve(self, number: int) -> bytes:
        """Fetch a whole message."""
        try:
            _, raw, _ = self._conn.retr(number)
        except poplib.error_proto as error:
            raise CliError(
                f"POP3 RETR {number} failed: {error}", code="message_not_found"
            ) from error
        return b"\r\n".join(raw)

    def summaries(self, entries: Sequence[Pop3Message]) -> list[dict[str, Any]]:
        """Header-only summaries, one network round trip per message."""
        rows: list[dict[str, Any]] = []
        for entry in entries:
            parsed = message_mod.parse_headers(self.headers(entry.number))
            row = message_mod.summarize(
                parsed, uid=entry.uid, flags=(), size=entry.size, folder="INBOX"
            )
            row["number"] = entry.number
            rows.append(row)
        return rows

    def resolve(self, uid: str) -> Pop3Message:
        """Find a message by UIDL value, or by message number as a fallback."""
        entries = self.listing()
        for entry in entries:
            if entry.uid == uid:
                return entry
        if uid.isdigit():
            for entry in entries:
                if entry.number == int(uid):
                    return entry
        raise CliError(f"no message with id {uid!r} in the maildrop",
                       code="message_not_found")

    def delete(self, numbers: Sequence[int]) -> None:
        """Mark messages for deletion. Committed only when QUIT succeeds."""
        for number in numbers:
            try:
                self._conn.dele(number)
            except poplib.error_proto as error:
                raise CliError(f"POP3 DELE {number} failed: {error}",
                               code="pop3_error") from error
        self._dirty = True

    def close(self, *, commit: bool) -> None:
        """End the session, committing or discarding pending deletions."""
        try:
            if self._dirty and not commit:
                self._conn.rset()
            self._conn.quit()
        except (poplib.error_proto, OSError):  # pragma: no cover - teardown noise
            try:
                self._conn.close()
            except OSError:
                pass


def _open(account: Account, timeout: float) -> poplib.POP3:
    endpoint = account.incoming
    context = ssl_context(account.insecure_tls)
    if endpoint.security == SSL:
        conn: poplib.POP3 = poplib.POP3_SSL(
            endpoint.host, endpoint.port, timeout=timeout, context=context
        )
    else:
        conn = poplib.POP3(endpoint.host, endpoint.port, timeout=timeout)
        if endpoint.security == STARTTLS:
            conn.stls(context)
        elif endpoint.security != PLAIN:  # pragma: no cover - validated upstream
            raise CliError(f"unknown security mode {endpoint.security!r}",
                           code="invalid_security")
    return conn


@contextmanager
def connect(account: Account, password: str, *, timeout: float = DEFAULT_TIMEOUT,
            commit_deletes: bool = False) -> Generator[Pop3]:
    """Open a logged-in POP3 session.

    `commit_deletes` defaults to False: unless the caller explicitly asked to
    delete, an interrupted session must not lose mail.
    """
    if account.protocol != "pop3":
        raise CliError(
            f"account {account.name!r} is configured for {account.protocol}, "
            "not POP3.",
            code="not_pop3",
        )

    endpoint = account.incoming
    try:
        conn = _open(account, timeout)
    except (OSError, socket.timeout, ssl.SSLError) as error:
        raise CliError(
            f"cannot reach POP3 at {endpoint.describe()}: {error}",
            code="connection_failed",
        ) from error
    except poplib.error_proto as error:
        raise CliError(
            f"POP3 handshake failed at {endpoint.describe()}: {error}",
            code="connection_failed",
        ) from error

    try:
        conn.user(account.username)
        conn.pass_(password)
    except poplib.error_proto as error:
        try:
            conn.quit()
        except (poplib.error_proto, OSError):
            pass
        raise CliError(
            f"POP3 login rejected for {account.username!r} at {endpoint.host}: {error}. "
            "Many providers require an app-specific password here; see "
            f"`claudeforanything emails-for-claude parameters {account.address}`.",
            code="login_failed",
        ) from error

    session = Pop3(conn, account)
    try:
        yield session
    finally:
        session.close(commit=commit_deletes)
