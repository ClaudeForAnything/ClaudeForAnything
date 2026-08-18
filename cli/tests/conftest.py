# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path

import pytest
from typer.testing import CliRunner

#: A dummy that is obviously not a real credential if it ever leaks into output.
PASSWORD = "correct-horse-battery-staple"


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def marketplace(tmp_path: Path) -> Path:
    """A minimal but valid marketplace tree, matching the real repository layout."""
    catalog = tmp_path / ".claude-plugin" / "marketplace.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        json.dumps(
            {
                "name": "claudeforanything",
                "owner": {"name": "Test"},
                "plugins": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / "marketplace" / "plugins").mkdir(parents=True)
    (tmp_path / "marketplace" / "skills").mkdir(parents=True)
    return tmp_path


def payload(stdout: str) -> dict:
    """Parse the --json envelope emitted by a command."""
    return json.loads(stdout)


@pytest.fixture
def mail_home(tmp_path: Path, monkeypatch) -> Path:
    """An isolated accounts.json, so tests never touch the real one."""
    home = tmp_path / "mail-home"
    monkeypatch.setenv("EMAILS_FOR_CLAUDE_HOME", str(home))
    return home


@pytest.fixture
def fake_keyring(monkeypatch) -> dict[tuple[str, str], str]:
    """Replace the OS credential store with a dict.

    Without this a test run would write to the developer's real Keychain or
    Credential Manager, which is both rude and non-deterministic.
    """
    import keyring
    from keyring.errors import PasswordDeleteError

    vault: dict[tuple[str, str], str] = {}

    monkeypatch.setattr(keyring, "get_password", lambda s, u: vault.get((s, u)))
    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: vault.__setitem__((s, u), p))

    def delete(service: str, username: str) -> None:
        if (service, username) not in vault:
            raise PasswordDeleteError("not found")
        del vault[(service, username)]

    monkeypatch.setattr(keyring, "delete_password", delete)
    monkeypatch.setattr(keyring, "get_keyring", lambda: "test in-memory keyring")
    return vault


# --------------------------------------------------------------------------
# A scripted IMAP server
# --------------------------------------------------------------------------


def sample_message() -> bytes:
    msg = EmailMessage()
    msg["From"] = "Alice Example <alice@example.com>"
    msg["To"] = "me@example.com"
    msg["Subject"] = "Quarterly café report"
    msg["Date"] = "Tue, 18 Aug 2026 10:23:11 +0200"
    msg["Message-ID"] = "<abc@example.com>"
    msg.set_content("The numbers are attached.\n")
    msg.add_attachment(b"col\n1\n", maintype="text", subtype="csv", filename="numbers.csv")
    return msg.as_bytes()


class ScriptedImap:
    """Enough of `imaplib.IMAP4` to drive every read and write command.

    `capabilities`, `deleted` and `raw` are writable so a test can stage the
    server-side conditions it needs — a server without UIDPLUS, a mailbox where
    another client already flagged something deleted, a hostile message.
    """

    def __init__(self) -> None:
        # UIDPLUS by default because most real servers advertise it. Tests that
        # exercise the degraded paths set `capabilities` explicitly.
        self.capabilities: tuple[str, ...] = ("IMAP4REV1", "MOVE", "UIDPLUS")
        self.deleted: tuple[str, ...] = ()
        self.raw = sample_message()
        self.commands: list[tuple] = []

    def list(self, directory='""', pattern="*"):
        return "OK", [
            rb'(\HasNoChildren) "/" "INBOX"',
            rb'(\HasNoChildren \Sent) "/" "Sent"',
            rb'(\HasNoChildren \Trash) "/" "Trash"',
        ]

    def select(self, mailbox="INBOX", readonly=False):
        self.commands.append(("select", mailbox, readonly))
        return "OK", [b"1"]

    def status(self, mailbox, names):
        return "OK", [b'"INBOX" (MESSAGES 1 UNSEEN 1 RECENT 0)']

    def expunge(self):
        self.commands.append(("expunge",))
        return "OK", [b"1"]

    def append(self, mailbox, flags, date_time, message):
        self.commands.append(("append", mailbox, message))
        return "OK", [b"appended"]

    def create(self, mailbox):
        self.commands.append(("create", mailbox))
        return "OK", [b"created"]

    def uid(self, command, *args):
        self.commands.append((command, *args))
        if command == "SEARCH":
            if b"DELETED" in args:
                return "OK", [" ".join(self.deleted).encode("ascii")]
            return "OK", [b"101"]
        if command == "EXPUNGE":
            return "OK", [b"1"]
        if command == "FETCH":
            spec = args[1]
            if "RFC822.SIZE" in spec:
                return "OK", [
                    b'1 (UID 101 FLAGS () RFC822.SIZE %d '
                    b'INTERNALDATE "18-Aug-2026 10:23:11 +0200")' % len(self.raw)
                ]
            body = self.raw if "BODY.PEEK[]" in spec else self.raw.split(b"\r\n\r\n", 1)[0]
            return "OK", [(b"1 (UID 101 BODY[] {%d}" % len(body), body), b")"]
        return "OK", [b""]

    def logout(self):
        return "BYE", [b"bye"]


@pytest.fixture
def scripted(monkeypatch) -> ScriptedImap:
    """Replace the IMAP connection with the scripted fake. No socket is opened."""
    from claudeforanything.mail import imap as imap_mod

    fake = ScriptedImap()

    @contextmanager
    def connect(account, password, *, timeout=30.0):
        assert password == PASSWORD, "the stored password must reach the transport"
        yield imap_mod.Imap(fake, account)

    monkeypatch.setattr(imap_mod, "connect", connect)
    return fake


@pytest.fixture
def configured(runner: CliRunner, mail_home: Path, fake_keyring) -> None:
    """One IMAP account, with a password in the fake keyring."""
    from claudeforanything.main import app

    added = runner.invoke(
        app,
        [
            "emails-for-claude", "account", "add", "work",
            "--address", "me@example.com", "--display-name", "Me",
            "--imap-host", "imap.example.com", "--smtp-host", "smtp.example.com",
            "--password-stdin", "--json",
        ],
        input=PASSWORD + "\n",
    )
    assert added.exit_code == 0, added.stdout


def run(runner: CliRunner, *args: str, **kwargs):
    """Invoke `claudeforanything emails-for-claude <args>`."""
    from claudeforanything.main import app

    return runner.invoke(app, ["emails-for-claude", *args], **kwargs)
