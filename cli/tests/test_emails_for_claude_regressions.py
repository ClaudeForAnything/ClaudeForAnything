# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI-level regressions from the review of PR #1.

Each test names the behaviour that was wrong. They live apart from the main
command-surface tests so the reason they exist stays legible.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path

from typer.testing import CliRunner

from .conftest import PASSWORD, ScriptedImap, payload, run


# --------------------------------------------------------------------------
# POP3 accepted filters and ignored them
# --------------------------------------------------------------------------


def test_pop3_refuses_filters_instead_of_answering_a_different_question(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    """A filtered query answered with the whole maildrop is a wrong answer.

    Human output carried a caveat, but `--json` had nowhere to put one a caller
    is obliged to read, so an agent asking for unread mail from one sender got
    unrelated messages inside a success envelope.
    """
    run(runner, "account", "add", "pop", "--address", "me@gmail.com",
        "--protocol", "pop3", "--password-stdin", input=PASSWORD + "\n")

    result = run(runner, "inbox", "--unseen", "--from", "boss@example.com", "--json")
    assert result.exit_code == 1
    body = payload(result.stdout)["error"]
    assert body["code"] == "filters_unsupported"
    assert "UNSEEN" in body["message"]


def test_pop3_without_filters_is_still_allowed(
    runner: CliRunner, mail_home: Path, fake_keyring, monkeypatch
) -> None:
    """Refusing filters must not refuse listing the maildrop."""
    from claudeforanything.mail import pop3 as pop3_mod

    class FakeMaildrop:
        def listing(self):
            return []

        def summaries(self, entries):
            return []

    @contextmanager
    def connect(account, password, *, timeout=30.0, commit_deletes=False):
        yield FakeMaildrop()

    monkeypatch.setattr(pop3_mod, "connect", connect)
    run(runner, "account", "add", "pop", "--address", "me@gmail.com",
        "--protocol", "pop3", "--password-stdin", input=PASSWORD + "\n")

    result = run(runner, "inbox", "--json")
    assert result.exit_code == 0, result.stdout
    assert payload(result.stdout)["data"]["filtered"] is False


# --------------------------------------------------------------------------
# --protocol pop3 invented endpoints
# --------------------------------------------------------------------------


def test_pop3_is_refused_for_presets_that_declare_no_pop3_server(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    """Proton Bridge has no POP3; deriving 127.0.0.1:995 would be a fabrication."""
    result = run(
        runner, "account", "add", "proton", "--address", "me@proton.me",
        "--protocol", "pop3", "--json",
    )
    assert result.exit_code == 1
    body = payload(result.stdout)["error"]
    assert body["code"] == "no_pop3_preset"
    assert "--imap-host" in body["message"]


def test_pop3_is_allowed_for_that_preset_with_explicit_settings(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(
        runner, "account", "add", "proton", "--address", "me@proton.me",
        "--protocol", "pop3", "--imap-host", "127.0.0.1", "--imap-port", "1110",
        "--imap-security", "starttls", "--json",
    )
    assert result.exit_code == 0, result.stdout
    assert payload(result.stdout)["data"]["account"]["incoming"] == {
        "host": "127.0.0.1", "port": 1110, "security": "starttls"
    }


def test_pop3_presets_that_do_declare_a_server_still_work(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(
        runner, "account", "add", "g", "--address", "me@gmail.com",
        "--protocol", "pop3", "--json",
    )
    assert result.exit_code == 0, result.stdout
    incoming = payload(result.stdout)["data"]["account"]["incoming"]
    assert incoming == {"host": "pop.gmail.com", "port": 995, "security": "ssl"}


# --------------------------------------------------------------------------
# --format raw was neither raw nor honouring --mark-seen
# --------------------------------------------------------------------------

EIGHT_BIT = (
    b"From: a@b.c\r\nSubject: eight bit\r\n"
    b"Content-Type: text/plain; charset=iso-8859-1\r\n"
    b"Content-Transfer-Encoding: 8bit\r\n\r\n"
    b"caf\xe9 na\xefve\r\n"
)


def test_raw_output_is_byte_exact_on_stdout(
    runner: CliRunner, configured, scripted: ScriptedImap
) -> None:
    """8-bit octets are legal in a body and must survive `--format raw`.

    Decoding with errors="replace" turned them into U+FFFD, so the output was
    no longer the message the server holds and could not be round-tripped.
    """
    scripted.raw = EIGHT_BIT
    result = run(runner, "read", "101", "--format", "raw")
    assert result.exit_code == 0
    assert b"caf\xe9 na\xefve" in result.stdout_bytes
    assert b"\xef\xbf\xbd" not in result.stdout_bytes, "must not become replacement chars"


def test_raw_json_output_carries_base64_rather_than_lossy_text(
    runner: CliRunner, configured, scripted: ScriptedImap
) -> None:
    scripted.raw = EIGHT_BIT
    data = payload(run(runner, "read", "101", "--format", "raw", "--json").stdout)["data"]
    assert data["encoding"] == "base64"
    assert base64.b64decode(data["raw_base64"]) == EIGHT_BIT
    assert data["size"] == len(EIGHT_BIT)


def test_raw_format_honours_mark_seen(
    runner: CliRunner, configured, scripted: ScriptedImap
) -> None:
    """The raw path called fetch_raw(), which had no way to mark anything."""
    run(runner, "read", "101", "--format", "raw", "--mark-seen")
    store = next(cmd for cmd in scripted.commands if cmd[0] == "STORE")
    assert store[2] == "+FLAGS" and "Seen" in store[3]


def test_raw_format_still_leaves_the_message_unread_by_default(
    runner: CliRunner, configured, scripted: ScriptedImap
) -> None:
    run(runner, "read", "101", "--format", "raw")
    assert not any(cmd[0] == "STORE" for cmd in scripted.commands)


# --------------------------------------------------------------------------
# Attachments overwrote each other
# --------------------------------------------------------------------------


def _two_reports() -> bytes:
    msg = EmailMessage()
    msg["From"] = "a@b.c"
    msg["Subject"] = "two reports"
    msg.set_content("see attached")
    msg.add_attachment(b"FIRST", maintype="application", subtype="pdf",
                       filename="report.pdf")
    msg.add_attachment(b"SECOND", maintype="application", subtype="pdf",
                       filename="report.pdf")
    return msg.as_bytes()


def test_duplicate_attachment_names_do_not_overwrite_each_other(
    runner: CliRunner, configured, scripted: ScriptedImap, tmp_path: Path
) -> None:
    """Two parts legitimately named report.pdf are common in real mail.

    Both were written to one path, so the command reported two saved files
    while only the second existed.
    """
    scripted.raw = _two_reports()
    target = tmp_path / "downloads"

    data = payload(
        run(runner, "attachments", "101", "--save", str(target), "--json").stdout
    )["data"]

    assert len(data["saved"]) == 2
    assert len(set(data["saved"])) == 2, "reported paths must be distinct"
    assert sorted(p.read_bytes() for p in target.iterdir()) == [b"FIRST", b"SECOND"]


def test_an_attachment_named_dot_dot_does_not_resolve_to_the_directory(
    runner: CliRunner, configured, scripted: ScriptedImap, tmp_path: Path
) -> None:
    """`Path('..').name` is '', which would make the target the directory itself."""
    msg = EmailMessage()
    msg["From"] = "attacker@example.com"
    msg["Subject"] = "hi"
    msg.set_content("body")
    msg.add_attachment(b"payload", maintype="text", subtype="plain", filename="..")
    scripted.raw = msg.as_bytes()

    target = tmp_path / "downloads"
    result = run(runner, "attachments", "101", "--save", str(target), "--json")
    assert result.exit_code == 0, result.stdout

    saved = payload(result.stdout)["data"]["saved"]
    assert len(saved) == 1
    assert Path(saved[0]).is_file()
    assert Path(saved[0]).parent == target


# --------------------------------------------------------------------------
# Mailbox-wide EXPUNGE as collateral damage
# --------------------------------------------------------------------------


def test_purge_refuses_when_it_would_erase_other_flagged_messages(
    runner: CliRunner, configured, scripted: ScriptedImap
) -> None:
    """Plain EXPUNGE removes everything flagged deleted, not just our UIDs."""
    scripted.capabilities = ("IMAP4REV1",)
    scripted.deleted = ("50", "101")

    result = run(runner, "delete", "101", "--purge", "--yes", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "unscoped_expunge"
    assert ("expunge",) not in scripted.commands


def test_purge_uses_uid_expunge_when_the_server_supports_it(
    runner: CliRunner, configured, scripted: ScriptedImap
) -> None:
    scripted.capabilities = ("IMAP4REV1", "UIDPLUS")
    result = run(runner, "delete", "101", "--purge", "--yes", "--json")
    assert result.exit_code == 0, result.stdout
    assert ("EXPUNGE", "101") in scripted.commands
    assert ("expunge",) not in scripted.commands


def test_purge_still_works_when_nothing_else_is_flagged(
    runner: CliRunner, configured, scripted: ScriptedImap
) -> None:
    scripted.capabilities = ("IMAP4REV1",)
    scripted.deleted = ("101",)
    result = run(runner, "delete", "101", "--purge", "--yes", "--json")
    assert result.exit_code == 0, result.stdout
    assert ("expunge",) in scripted.commands


# --------------------------------------------------------------------------
# --dry-run overstated what it was showing
# --------------------------------------------------------------------------


def test_dry_run_shows_the_transmitted_bytes_not_as_string(
    runner: CliRunner, configured
) -> None:
    """`as_string()` still carried Bcc, which send_message strips before sending."""
    data = payload(
        run(
            runner, "send", "--to", "a@x.com", "--bcc", "secret@x.com",
            "--subject", "Hi", "--body", "hello", "--dry-run", "--json",
        ).stdout
    )["data"]

    assert data["exact"] is True
    assert "secret@x.com" in data["bcc"], "the envelope still carries it"
    assert "secret@x.com" not in data["message"], "the wire form must not"


def test_dry_run_admits_when_smtputf8_makes_it_inexact(
    runner: CliRunner, configured
) -> None:
    """Exact-bytes-without-a-socket is not always satisfiable, so say so.

    A non-ASCII address makes smtplib reflatten with a utf8 policy — but only
    if the live server advertises SMTPUTF8, which a preview cannot know.
    """
    data = payload(
        run(
            runner, "send", "--to", "josé@example.com", "--body", "x",
            "--dry-run", "--json",
        ).stdout
    )["data"]
    assert data["smtputf8"] is True
    assert data["exact"] is False, "the preview must not claim to be byte-exact here"


def test_dry_run_claims_exactness_only_for_plain_ascii_envelopes(
    runner: CliRunner, configured
) -> None:
    data = payload(
        run(runner, "send", "--to", "a@x.com", "--body", "x", "--dry-run", "--json").stdout
    )["data"]
    assert data["smtputf8"] is False
    assert data["exact"] is True


def test_an_ambiguous_recipient_is_refused_at_the_cli(
    runner: CliRunner, configured
) -> None:
    """Lenient parsing expands this into two recipients, one of them unseen."""
    result = run(
        runner, "send", "--to", "a@x.com <b@evil.com>", "--body", "x",
        "--dry-run", "--json",
    )
    assert result.exit_code == 1
    body = payload(result.stdout)["error"]
    assert body["code"] == "ambiguous_address"
    assert "b@evil.com" in body["message"]
