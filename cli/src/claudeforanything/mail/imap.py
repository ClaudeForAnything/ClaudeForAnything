# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""IMAP, over `imaplib`, with the protocol's sharp edges filed down.

`imaplib` is a thin transport: it sends the bytes you hand it and returns the
bytes the server sent back, unparsed. Three things have to be dealt with before
that is usable, and each has a section below:

* mailbox names are modified UTF-7 (RFC 3501 §5.1.3), not UTF-8;
* FETCH responses interleave metadata strings with literal blobs, so a response
  is a list of mixed `bytes` and `(prefix, literal)` tuples;
* SEARCH arguments have to be pre-encoded, because `imaplib` encodes `str`
  arguments as ASCII and raises on anything else.

Everything here addresses messages by UID, never by sequence number. Sequence
numbers shift under you the moment another client expunges something, which
makes them unusable for an agent that reads an inbox listing in one command and
acts on it in the next.
"""

from __future__ import annotations

import base64
import imaplib
import re
import socket
import ssl
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from email.message import EmailMessage
from typing import Any, Generator, Sequence

from ..output import CliError
from . import message as message_mod
from .accounts import Account
from .presets import PLAIN, SSL, STARTTLS

DEFAULT_TIMEOUT = 30.0

#: Special-use mailbox attributes (RFC 6154), the reliable way to find Sent and
#: Trash without guessing at localized folder names.
SPECIAL_USE = ("\\Sent", "\\Trash", "\\Drafts", "\\Junk", "\\Archive", "\\All", "\\Flagged")

_LIST_RE = re.compile(rb'^\((?P<flags>[^)]*)\)\s+(?P<delim>"(?:[^"\\]|\\.)*"|NIL)\s+(?P<name>.+)$')
_UID_RE = re.compile(rb"\bUID\s+(\d+)")
_FLAGS_RE = re.compile(rb"\bFLAGS\s+\(([^)]*)\)")
_SIZE_RE = re.compile(rb"\bRFC822\.SIZE\s+(\d+)")
_INTERNALDATE_RE = re.compile(rb'\bINTERNALDATE\s+"([^"]*)"')

_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


# --------------------------------------------------------------------------
# Mailbox names: modified UTF-7
# --------------------------------------------------------------------------


def encode_mailbox(name: str) -> bytes:
    """Encode a mailbox name to modified UTF-7 (RFC 3501 §5.1.3).

    Printable ASCII passes through; `&` doubles as `&-`; anything else is
    UTF-16BE base64 between `&` and `-`, with `/` written as `,`.
    """
    out = bytearray()
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        encoded = base64.b64encode("".join(buffer).encode("utf-16-be"))
        out.extend(b"&" + encoded.rstrip(b"=").replace(b"/", b",") + b"-")
        buffer.clear()

    for char in name:
        if char == "&":
            flush()
            out.extend(b"&-")
        elif 0x20 <= ord(char) <= 0x7E:
            flush()
            out.extend(char.encode("ascii"))
        else:
            buffer.append(char)
    flush()
    return bytes(out)


def decode_mailbox(raw: bytes | str) -> str:
    """Decode a modified UTF-7 mailbox name back to text."""
    text = raw.decode("ascii", "replace") if isinstance(raw, bytes) else raw
    out: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char != "&":
            out.append(char)
            index += 1
            continue
        end = text.find("-", index + 1)
        if end == -1:
            out.append(char)
            index += 1
            continue
        chunk = text[index + 1 : end]
        if not chunk:
            out.append("&")
        else:
            padded = chunk.replace(",", "/")
            padded += "=" * (-len(padded) % 4)
            try:
                out.append(base64.b64decode(padded).decode("utf-16-be"))
            except (ValueError, UnicodeDecodeError):
                out.append(text[index : end + 1])
        index = end + 1
    return "".join(out)


def quote(raw: bytes) -> bytes:
    """Wrap a byte string as an IMAP quoted-string."""
    return b'"' + raw.replace(b"\\", b"\\\\").replace(b'"', b'\\"') + b'"'


def _unquote(raw: bytes) -> bytes:
    if len(raw) >= 2 and raw[:1] == b'"' and raw[-1:] == b'"':
        return raw[1:-1].replace(b'\\"', b'"').replace(b"\\\\", b"\\")
    return raw


def mailbox_arg(name: str) -> str:
    """A mailbox name ready to hand to imaplib.

    Modified UTF-7 output is pure ASCII by construction, so decoding it back to
    `str` is lossless and keeps `imaplib`'s ASCII encoding step happy.
    """
    return quote(encode_mailbox(name)).decode("ascii")


# --------------------------------------------------------------------------
# Search criteria
# --------------------------------------------------------------------------


def _imap_date(value: str) -> str:
    """Accept YYYY-MM-DD (or DD-Mon-YYYY) and return IMAP's DD-Mon-YYYY."""
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            parsed: date = datetime.strptime(text, fmt).date()
        except ValueError:
            continue
        return f"{parsed.day:02d}-{_MONTHS[parsed.month - 1]}-{parsed.year}"
    raise CliError(
        f"cannot read {value!r} as a date; use YYYY-MM-DD", code="invalid_date"
    )


def _quoted(value: str) -> bytes:
    """A search argument as bytes, quoted and UTF-8 encoded."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return b'"' + escaped.encode("utf-8") + b'"'


@dataclass(slots=True)
class Criteria:
    """The filters `inbox` and `search` accept, assembled into IMAP terms."""

    unseen: bool = False
    seen: bool = False
    flagged: bool = False
    answered: bool = False
    sender: str | None = None
    recipient: str | None = None
    subject: str | None = None
    text: str | None = None
    body: str | None = None
    since: str | None = None
    before: str | None = None
    larger: int | None = None
    has_attachment: bool = False
    raw: str | None = None

    def terms(self) -> list[bytes]:
        """The IMAP search terms, or [b'ALL'] when nothing was asked for."""
        terms: list[bytes] = []
        if self.unseen:
            terms.append(b"UNSEEN")
        if self.seen:
            terms.append(b"SEEN")
        if self.flagged:
            terms.append(b"FLAGGED")
        if self.answered:
            terms.append(b"ANSWERED")
        if self.sender:
            terms += [b"FROM", _quoted(self.sender)]
        if self.recipient:
            terms += [b"TO", _quoted(self.recipient)]
        if self.subject:
            terms += [b"SUBJECT", _quoted(self.subject)]
        if self.text:
            terms += [b"TEXT", _quoted(self.text)]
        if self.body:
            terms += [b"BODY", _quoted(self.body)]
        if self.since:
            terms += [b"SINCE", _imap_date(self.since).encode("ascii")]
        if self.before:
            terms += [b"BEFORE", _imap_date(self.before).encode("ascii")]
        if self.larger is not None:
            terms += [b"LARGER", str(self.larger).encode("ascii")]
        if self.has_attachment:
            # No IMAP predicate for "has an attachment"; this is the closest
            # portable approximation and is documented as approximate.
            terms += [b"HEADER", b"Content-Type", b'"multipart/mixed"']
        if self.raw:
            terms.append(self.raw.encode("utf-8"))
        return terms or [b"ALL"]

    def needs_utf8(self) -> bool:
        """True when any term carries non-ASCII and CHARSET UTF-8 is required."""
        return any(not term.isascii() for term in self.terms())

    def is_empty(self) -> bool:
        """True when no filter was asked for, so this matches everything.

        POP3 has no server-side search at all, and answering a filtered query
        with unfiltered results would be a wrong answer wearing a success
        envelope. The POP3 path uses this to tell "list the mailbox" apart from
        "find these messages" and refuse only the second.
        """
        return self.terms() == [b"ALL"]

    def describe(self) -> str:
        return " ".join(term.decode("utf-8", "replace") for term in self.terms())


# --------------------------------------------------------------------------
# Connection
# --------------------------------------------------------------------------


def ssl_context(insecure: bool) -> ssl.SSLContext:
    """A verifying TLS context, or a deliberately permissive one."""
    context = ssl.create_default_context()
    if insecure:
        # Only reachable through the account's --insecure-tls, which exists for
        # Proton Bridge and self-hosted servers with a self-signed certificate.
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    return context


@dataclass(frozen=True, slots=True)
class Folder:
    """One mailbox as reported by LIST."""

    name: str
    delimiter: str
    flags: tuple[str, ...]

    @property
    def special_use(self) -> str | None:
        for flag in self.flags:
            if flag in SPECIAL_USE:
                return flag
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "delimiter": self.delimiter,
            "flags": list(self.flags),
            "special_use": self.special_use,
            "selectable": "\\Noselect" not in self.flags,
        }


class Imap:
    """A logged-in IMAP session. Build it with `connect()`."""

    def __init__(self, conn: imaplib.IMAP4, account: Account) -> None:
        self._conn = conn
        self.account = account
        self._selected: tuple[str, bool] | None = None

    # -- plumbing ---------------------------------------------------------

    @property
    def capabilities(self) -> tuple[str, ...]:
        return tuple(self._conn.capabilities)

    def _uid(self, command: str, *args: Any) -> list[Any]:
        try:
            typ, data = self._conn.uid(command, *args)
        except imaplib.IMAP4.abort as error:
            raise CliError(f"IMAP connection aborted during {command}: {error}",
                           code="imap_aborted") from error
        except imaplib.IMAP4.error as error:
            raise CliError(f"IMAP {command} failed: {error}", code="imap_error") from error
        if typ != "OK":
            raise CliError(f"IMAP {command} returned {typ}: {data!r}", code="imap_error")
        return list(data)

    def select(self, folder: str, *, readonly: bool = True) -> int:
        """Select a mailbox, returning its message count.

        Re-selecting the same mailbox in the same mode is a no-op, so callers
        can select defensively without paying a round trip.
        """
        if self._selected == (folder, readonly):
            return -1
        try:
            typ, data = self._conn.select(mailbox_arg(folder), readonly)
        except imaplib.IMAP4.error as error:
            raise CliError(f"cannot open folder {folder!r}: {error}",
                           code="folder_error") from error
        if typ != "OK":
            names = ", ".join(f.name for f in self.folders()[:20]) or "none"
            raise CliError(
                f"cannot open folder {folder!r}. Available: {names}",
                code="folder_not_found",
            )
        self._selected = (folder, readonly)
        count = data[0] if data else None
        try:
            return int(count) if count is not None else -1
        except (TypeError, ValueError):
            return -1

    def logout(self) -> None:
        try:
            self._conn.logout()
        except (imaplib.IMAP4.error, OSError):  # pragma: no cover - teardown noise
            pass

    # -- folders ----------------------------------------------------------

    def folders(self) -> list[Folder]:
        """Every mailbox the account can see."""
        try:
            typ, data = self._conn.list()
        except imaplib.IMAP4.error as error:
            raise CliError(f"LIST failed: {error}", code="imap_error") from error
        if typ != "OK":
            raise CliError(f"LIST returned {typ}", code="imap_error")

        found: list[Folder] = []
        for item in data:
            line = item[0] + item[1] if isinstance(item, tuple) else item
            if not isinstance(line, bytes):
                continue
            match = _LIST_RE.match(line.strip())
            if not match:
                continue
            flags = tuple(
                token.decode("ascii", "replace")
                for token in match.group("flags").split()
            )
            delimiter = _unquote(match.group("delim")).decode("ascii", "replace")
            found.append(
                Folder(
                    name=decode_mailbox(_unquote(match.group("name").strip())),
                    delimiter="" if delimiter == "NIL" else delimiter,
                    flags=flags,
                )
            )
        return sorted(found, key=lambda f: f.name.lower())

    def find_special(self, use: str, fallbacks: Sequence[str]) -> str | None:
        """Locate a special-use mailbox by RFC 6154 flag, then by common name."""
        listing = self.folders()
        for folder in listing:
            if use in folder.flags:
                return folder.name
        lowered = {folder.name.lower(): folder.name for folder in listing}
        for candidate in fallbacks:
            if candidate.lower() in lowered:
                return lowered[candidate.lower()]
        return None

    def sent_folder(self) -> str | None:
        if self.account.sent_folder:
            return self.account.sent_folder
        return self.find_special(
            "\\Sent",
            ("Sent", "Sent Items", "Sent Messages", "INBOX.Sent", "[Gmail]/Sent Mail",
             "Éléments envoyés", "Messages envoyés"),
        )

    def trash_folder(self) -> str | None:
        if self.account.trash_folder:
            return self.account.trash_folder
        return self.find_special(
            "\\Trash",
            ("Trash", "Deleted Items", "Deleted Messages", "INBOX.Trash",
             "[Gmail]/Trash", "Corbeille"),
        )

    # -- searching --------------------------------------------------------

    def search(self, folder: str, criteria: Criteria) -> list[str]:
        """Return matching UIDs, oldest first."""
        self.select(folder, readonly=True)
        terms = criteria.terms()
        args: list[Any] = ["CHARSET", "UTF-8", *terms] if criteria.needs_utf8() else list(terms)
        try:
            data = self._uid("SEARCH", *args)
        except CliError:
            if not criteria.needs_utf8():
                raise
            # Servers that do not advertise SEARCH CHARSET reject the prefix
            # outright. Retrying without it still works for ASCII-representable
            # terms, which is most of them.
            data = self._uid("SEARCH", *terms)
        raw = data[0] if data and isinstance(data[0], bytes) else b""
        return [uid.decode("ascii") for uid in raw.split()]

    # -- fetching ---------------------------------------------------------

    def _fetch_metadata(self, uids: Sequence[str]) -> dict[str, dict[str, Any]]:
        """UID -> {flags, size, internaldate}, in one round trip."""
        if not uids:
            return {}
        data = self._uid("FETCH", ",".join(uids), "(UID FLAGS RFC822.SIZE INTERNALDATE)")
        meta: dict[str, dict[str, Any]] = {}
        for item in data:
            line = item[0] if isinstance(item, tuple) else item
            if not isinstance(line, bytes):
                continue
            uid_match = _UID_RE.search(line)
            if not uid_match:
                continue
            flags_match = _FLAGS_RE.search(line)
            size_match = _SIZE_RE.search(line)
            date_match = _INTERNALDATE_RE.search(line)
            meta[uid_match.group(1).decode("ascii")] = {
                "flags": tuple(
                    token.decode("ascii", "replace")
                    for token in (flags_match.group(1).split() if flags_match else [])
                ),
                "size": int(size_match.group(1)) if size_match else None,
                "internaldate": (
                    date_match.group(1).decode("ascii", "replace") if date_match else None
                ),
            }
        return meta

    def _fetch_parts(self, uids: Sequence[str], spec: str) -> dict[str, bytes]:
        """UID -> literal payload, for a fetch spec that returns exactly one literal."""
        if not uids:
            return {}
        data = self._uid("FETCH", ",".join(uids), spec)
        payloads: dict[str, bytes] = {}
        for item in data:
            if not isinstance(item, tuple) or len(item) < 2:
                continue
            prefix, literal = item[0], item[1]
            if not isinstance(prefix, bytes) or not isinstance(literal, bytes):
                continue
            uid_match = _UID_RE.search(prefix)
            if uid_match:
                payloads[uid_match.group(1).decode("ascii")] = literal
        return payloads

    def summaries(self, folder: str, uids: Sequence[str]) -> list[dict[str, Any]]:
        """Header-only summaries for a UID list, in the order given."""
        if not uids:
            return []
        self.select(folder, readonly=True)
        meta = self._fetch_metadata(uids)
        spec = f"(UID BODY.PEEK[HEADER.FIELDS ({' '.join(message_mod.SUMMARY_HEADERS)})])"
        headers = self._fetch_parts(uids, spec)

        rows: list[dict[str, Any]] = []
        for uid in uids:
            raw = headers.get(uid)
            if raw is None:
                continue
            info = meta.get(uid, {})
            parsed = message_mod.parse_headers(raw)
            row = message_mod.summarize(
                parsed,
                uid=uid,
                flags=info.get("flags", ()),
                size=info.get("size"),
                folder=folder,
            )
            row["internaldate"] = info.get("internaldate")
            rows.append(row)
        return rows

    def fetch_message(self, folder: str, uid: str, *, mark_seen: bool = False
                      ) -> tuple[EmailMessage, dict[str, Any]]:
        """Fetch one whole message, plus its flags and size.

        BODY.PEEK never sets \\Seen; `mark_seen` asks for it explicitly, so
        reading a message is non-destructive unless the caller says otherwise.
        """
        self.select(folder, readonly=not mark_seen)
        meta = self._fetch_metadata([uid]).get(uid, {})
        payloads = self._fetch_parts([uid], "(UID BODY.PEEK[])")
        raw = payloads.get(uid)
        if raw is None:
            raise CliError(
                f"no message with UID {uid} in {folder!r}", code="message_not_found"
            )
        if mark_seen:
            self.store(folder, [uid], "+FLAGS", ["\\Seen"])
        return message_mod.parse(raw), meta

    def fetch_raw(self, folder: str, uid: str, *, mark_seen: bool = False) -> bytes:
        """The message exactly as the server holds it, byte for byte."""
        self.select(folder, readonly=not mark_seen)
        payloads = self._fetch_parts([uid], "(UID BODY.PEEK[])")
        raw = payloads.get(uid)
        if raw is None:
            raise CliError(
                f"no message with UID {uid} in {folder!r}", code="message_not_found"
            )
        if mark_seen:
            self.store(folder, [uid], "+FLAGS", ["\\Seen"])
        return raw

    # -- mutating ---------------------------------------------------------

    def store(self, folder: str, uids: Sequence[str], operation: str,
              flags: Sequence[str]) -> None:
        """Apply +FLAGS / -FLAGS / FLAGS to a set of UIDs."""
        if not uids:
            return
        self.select(folder, readonly=False)
        self._uid("STORE", ",".join(uids), operation, f"({' '.join(flags)})")

    def move(self, folder: str, uids: Sequence[str], destination: str) -> str:
        """Move messages, returning the method used.

        RFC 6851 MOVE is atomic and preferred. Without it the old COPY, mark
        \\Deleted, expunge dance is needed — and that last step cannot always be
        done safely, so it is delegated to `purge()`. Returns 'move',
        'copy+uid-expunge', or 'copy+flag' when the source copies had to be left
        flagged rather than removed.
        """
        if not uids:
            return "move"
        self.select(folder, readonly=False)
        uid_set = ",".join(uids)
        if "MOVE" in self.capabilities:
            self._uid("MOVE", uid_set, mailbox_arg(destination))
            return "move"

        self._uid("COPY", uid_set, mailbox_arg(destination))
        self._uid("STORE", uid_set, "+FLAGS", "(\\Deleted)")
        # The copy already exists at the destination, so refusing outright would
        # strand the operation half-done. Leaving the sources flagged is the
        # honest degraded outcome; the caller reports it rather than claiming a
        # completed move.
        return "copy+uid-expunge" if self.purge(folder, uids) else "copy+flag"

    def purge(self, folder: str, uids: Sequence[str]) -> bool:
        """Expunge exactly these UIDs. False means the server cannot do it safely.

        **This package never issues a mailbox-wide EXPUNGE for a UID-scoped
        request.** Plain EXPUNGE removes every message carrying \\Deleted in the
        selected mailbox at the moment it runs — not the ones named here — so a
        message another client flagged would be destroyed as collateral.

        Checking first does not fix that. RFC 3501 lets other connections change
        flags while a mailbox is selected, so `SEARCH DELETED` followed by
        `EXPUNGE` is check-then-act with a network round trip in the middle:

            us:    SEARCH DELETED  ->  101          (only our target)
            them:  STORE 777 +FLAGS (\\Deleted)
            us:    EXPUNGE                          (erases 101 *and* 777)

        Avoiding exactly that race is why RFC 4315 defines UID EXPUNGE. That RFC
        also sketches a fallback — temporarily clear \\Deleted from everything
        you do not want expunged, EXPUNGE, then put the flags back — which is
        not used here: it has the same race in both directions, it mutates other
        clients' flags as a side effect, and an interruption between the clear
        and the restore loses them for good.

        So: UID EXPUNGE when UIDPLUS is advertised, and otherwise report that it
        could not be done and let the caller decide what to say.
        """
        if not uids:
            return True
        if "UIDPLUS" not in self.capabilities:
            return False
        self.select(folder, readonly=False)
        self._uid("EXPUNGE", ",".join(uids))
        return True

    def append(self, folder: str, raw: bytes, flags: Sequence[str] = ("\\Seen",)) -> None:
        """Add a message to a mailbox, used to file a copy of what we send."""
        try:
            typ, data = self._conn.append(
                mailbox_arg(folder),
                f"({' '.join(flags)})" if flags else None,
                imaplib.Time2Internaldate(time.time()),
                raw,
            )
        except imaplib.IMAP4.error as error:
            raise CliError(f"APPEND to {folder!r} failed: {error}",
                           code="imap_error") from error
        if typ != "OK":
            raise CliError(f"APPEND to {folder!r} returned {typ}: {data!r}",
                           code="imap_error")

    def create(self, folder: str) -> None:
        try:
            typ, data = self._conn.create(mailbox_arg(folder))
        except imaplib.IMAP4.error as error:
            raise CliError(f"CREATE {folder!r} failed: {error}",
                           code="imap_error") from error
        if typ != "OK":
            raise CliError(f"CREATE {folder!r} returned {typ}: {data!r}",
                           code="imap_error")

    def status(self, folder: str) -> dict[str, int]:
        """MESSAGES / UNSEEN / RECENT counts for a mailbox, without selecting it."""
        try:
            typ, data = self._conn.status(mailbox_arg(folder), "(MESSAGES UNSEEN RECENT)")
        except imaplib.IMAP4.error as error:
            raise CliError(f"STATUS {folder!r} failed: {error}",
                           code="imap_error") from error
        if typ != "OK" or not data:
            raise CliError(f"STATUS {folder!r} returned {typ}", code="imap_error")
        line = data[0] if isinstance(data[0], bytes) else b""
        counts: dict[str, int] = {}
        for key, value in re.findall(rb"(MESSAGES|UNSEEN|RECENT)\s+(\d+)", line):
            counts[key.decode("ascii").lower()] = int(value)
        return counts


def _open(account: Account, timeout: float) -> imaplib.IMAP4:
    endpoint = account.incoming
    context = ssl_context(account.insecure_tls)
    if endpoint.security == SSL:
        return imaplib.IMAP4_SSL(
            endpoint.host, endpoint.port, ssl_context=context, timeout=timeout
        )

    conn = imaplib.IMAP4(endpoint.host, endpoint.port, timeout=timeout)
    if endpoint.security == STARTTLS:
        conn.starttls(context)
    elif endpoint.security != PLAIN:  # pragma: no cover - validated upstream
        raise CliError(f"unknown security mode {endpoint.security!r}",
                       code="invalid_security")
    return conn


@contextmanager
def connect(account: Account, password: str, *, timeout: float = DEFAULT_TIMEOUT
            ) -> Generator[Imap]:
    """Open a logged-in IMAP session and guarantee it is closed."""
    if account.protocol != "imap":
        raise CliError(
            f"account {account.name!r} is configured for {account.protocol}, "
            "and this command needs IMAP. POP3 has no folders, flags, or "
            "server-side search.",
            code="not_imap",
        )

    endpoint = account.incoming
    try:
        conn = _open(account, timeout)
    except (OSError, socket.timeout, ssl.SSLError) as error:
        raise CliError(
            f"cannot reach IMAP at {endpoint.describe()}: {error}",
            code="connection_failed",
        ) from error
    except imaplib.IMAP4.error as error:
        raise CliError(
            f"IMAP handshake failed at {endpoint.describe()}: {error}",
            code="connection_failed",
        ) from error

    try:
        conn.login(account.username, password)
    except imaplib.IMAP4.error as error:
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
        raise CliError(
            f"IMAP login rejected for {account.username!r} at {endpoint.host}: {error}. "
            "Many providers require an app-specific password here; see "
            f"`claudeforanything emails-for-claude parameters {account.address}`.",
            code="login_failed",
        ) from error

    session = Imap(conn, account)
    try:
        yield session
    finally:
        session.logout()
