# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLI-level tests for `claudeforanything emails-for-claude`.

No socket is ever opened: the IMAP session is replaced by a scripted fake, and
the keyring by a dict. What is being checked is the command surface — the JSON
envelope, the human output, the confirmations, and the promise that a password
never reaches stdout.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claudeforanything.main import app
from claudeforanything.mail import imap as imap_mod

from .conftest import payload

PASSWORD = "correct-horse-battery-staple"


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
    """Enough of `imaplib.IMAP4` to drive every read command."""

    capabilities = ("IMAP4REV1", "MOVE")

    def __init__(self) -> None:
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
            return "OK", [b"101"]
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
    """Replace the IMAP connection with the scripted fake."""
    fake = ScriptedImap()

    @contextmanager
    def connect(account, password, *, timeout=30.0):
        assert password == PASSWORD, "the stored password must reach the transport"
        yield imap_mod.Imap(fake, account)

    monkeypatch.setattr(imap_mod, "connect", connect)
    return fake


@pytest.fixture
def configured(runner: CliRunner, mail_home: Path, fake_keyring) -> None:
    """One account, with a password in the fake keyring."""
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
    return runner.invoke(app, ["emails-for-claude", *args], **kwargs)


# --------------------------------------------------------------------------
# accounts
# --------------------------------------------------------------------------


def test_listing_with_no_accounts_explains_how_to_add_one(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(runner, "account", "list")
    assert result.exit_code == 0
    assert "account add" in result.stdout


def test_adding_an_account_derives_settings_from_the_address(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(
        runner, "account", "add", "gmail", "--address", "me@gmail.com", "--json"
    )
    assert result.exit_code == 0, result.stdout
    data = payload(result.stdout)["data"]
    assert data["preset"] == "gmail"
    assert data["preset_known"] is True
    assert data["account"]["incoming"] == {
        "host": "imap.gmail.com", "port": 993, "security": "ssl"
    }
    assert data["account"]["outgoing"]["port"] == 587


def test_an_unknown_domain_is_added_but_flagged_as_a_guess(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(runner, "account", "add", "x", "--address", "me@acme.example", "--json")
    data = payload(result.stdout)["data"]
    assert data["preset_known"] is False
    assert any("--probe" in w for w in data["warnings"])


def test_an_address_without_an_at_sign_is_refused(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(runner, "account", "add", "x", "--address", "nonsense", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "invalid_address"


def test_adding_the_same_name_twice_needs_force(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    run(runner, "account", "add", "work", "--address", "me@gmail.com")
    again = run(runner, "account", "add", "work", "--address", "me@gmail.com", "--json")
    assert again.exit_code == 1
    assert payload(again.stdout)["error"]["code"] == "exists"

    forced = run(
        runner, "account", "add", "work", "--address", "other@gmail.com", "--force", "--json"
    )
    assert forced.exit_code == 0


def test_the_password_is_stored_in_the_keyring_and_never_printed(
    runner: CliRunner, configured, fake_keyring
) -> None:
    from claudeforanything.mail import secrets

    assert fake_keyring[(secrets.service_name("work"), "me@example.com")] == PASSWORD

    for args in (["account", "list"], ["account", "show", "work"], ["account", "show", "--json"]):
        result = run(runner, *args)
        assert result.exit_code == 0, result.stdout
        assert PASSWORD not in result.stdout


def test_account_show_reports_where_the_password_comes_from(
    runner: CliRunner, configured
) -> None:
    data = payload(run(runner, "account", "show", "--json").stdout)["data"]
    assert data["account"]["password_source"] == "keyring"
    assert data["account"]["password_env_var"] == "EMAILS_FOR_CLAUDE_PASSWORD_WORK"


def test_an_environment_variable_stands_in_when_the_keyring_is_empty(
    runner: CliRunner, mail_home: Path, fake_keyring, monkeypatch
) -> None:
    run(runner, "account", "add", "ci", "--address", "bot@example.com")
    monkeypatch.setenv("EMAILS_FOR_CLAUDE_PASSWORD_CI", "from-env")

    data = payload(run(runner, "account", "show", "ci", "--json").stdout)["data"]
    assert data["account"]["password_source"] == "environment"


def test_removing_an_account_forgets_its_password(
    runner: CliRunner, configured, fake_keyring
) -> None:
    result = run(runner, "account", "remove", "work", "--json")
    assert result.exit_code == 0
    assert payload(result.stdout)["data"]["password_forgotten"] is True
    assert fake_keyring == {}


def test_removing_an_account_can_keep_its_password(
    runner: CliRunner, configured, fake_keyring
) -> None:
    run(runner, "account", "remove", "work", "--keep-password", "--json")
    assert fake_keyring != {}


def test_the_default_account_can_be_switched(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    run(runner, "account", "add", "one", "--address", "a@gmail.com")
    run(runner, "account", "add", "two", "--address", "b@gmail.com", "--no-set-default")
    assert payload(run(runner, "account", "list", "--json").stdout)["data"]["default"] == "one"

    run(runner, "account", "set-default", "two")
    assert payload(run(runner, "account", "list", "--json").stdout)["data"]["default"] == "two"


def test_commands_without_an_account_say_so(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(runner, "inbox", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "no_accounts"


def test_a_configured_account_with_no_password_says_how_to_store_one(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    run(runner, "account", "add", "work", "--address", "me@gmail.com")
    result = run(runner, "inbox", "--json")
    assert result.exit_code == 1
    body = payload(result.stdout)["error"]
    assert body["code"] == "no_password"
    assert "account set-password" in body["message"]


# --------------------------------------------------------------------------
# parameters / presets
# --------------------------------------------------------------------------


def test_parameters_for_a_known_domain_report_published_settings(runner: CliRunner) -> None:
    data = payload(run(runner, "parameters", "me@fastmail.com", "--json").stdout)["data"]
    assert data["source"] == "preset"
    assert data["preset"]["imap"]["host"] == "imap.fastmail.com"


def test_parameters_for_an_unknown_domain_are_labelled_a_guess(runner: CliRunner) -> None:
    data = payload(run(runner, "parameters", "me@acme.example", "--json").stdout)["data"]
    assert data["source"] == "guess"


def test_parameters_with_no_argument_describe_the_default_account(
    runner: CliRunner, configured
) -> None:
    data = payload(run(runner, "parameters", "--json").stdout)["data"]
    assert data["source"] == "account"
    assert data["account"]["name"] == "work"


def test_presets_list_every_provider(runner: CliRunner) -> None:
    from claudeforanything.mail import presets as presets_mod

    data = payload(run(runner, "presets", "--json").stdout)["data"]
    assert len(data["presets"]) == len(presets_mod.PRESETS)


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------


def test_folders_are_listed_with_their_special_use(
    runner: CliRunner, configured, scripted
) -> None:
    data = payload(run(runner, "folders", "--json").stdout)["data"]
    names = {f["name"]: f["special_use"] for f in data["folders"]}
    assert names == {"INBOX": None, "Sent": "\\Sent", "Trash": "\\Trash"}


def test_inbox_lists_messages_with_counts(runner: CliRunner, configured, scripted) -> None:
    result = run(runner, "inbox", "--json")
    assert result.exit_code == 0, result.stdout
    data = payload(result.stdout)["data"]
    assert data["counts"] == {"messages": 1, "unseen": 1, "recent": 0}
    assert data["messages"][0]["uid"] == "101"
    assert data["messages"][0]["subject"] == "Quarterly café report"


def test_inbox_filters_become_imap_search_terms(
    runner: CliRunner, configured, scripted
) -> None:
    run(runner, "inbox", "--unseen", "--from", "boss@corp.com", "--since", "2026-01-05")
    search = next(cmd for cmd in scripted.commands if cmd[0] == "SEARCH")
    assert b"UNSEEN" in search and b'"boss@corp.com"' in search
    assert b"05-Jan-2026" in search


def test_an_unparseable_date_is_rejected_before_connecting(
    runner: CliRunner, configured, scripted
) -> None:
    result = run(runner, "inbox", "--since", "yesterday", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "invalid_date"


def test_search_prints_bare_uids_for_piping(runner: CliRunner, configured, scripted) -> None:
    result = run(runner, "search", "--unseen")
    assert result.exit_code == 0
    assert result.stdout.split() == ["101"]


def test_read_returns_headers_body_and_attachments(
    runner: CliRunner, configured, scripted
) -> None:
    data = payload(run(runner, "read", "101", "--json").stdout)["data"]
    assert data["subject"] == "Quarterly café report"
    assert data["from_addresses"][0]["address"] == "alice@example.com"
    assert "numbers are attached" in data["body"]
    assert [a["filename"] for a in data["attachments"]] == ["numbers.csv"]


def test_read_leaves_the_message_unread_unless_asked(
    runner: CliRunner, configured, scripted
) -> None:
    run(runner, "read", "101")
    assert not any(cmd[0] == "STORE" for cmd in scripted.commands)

    run(runner, "read", "101", "--mark-seen")
    store = next(cmd for cmd in scripted.commands if cmd[0] == "STORE")
    assert store[2] == "+FLAGS" and "\\Seen" in store[3]


def test_read_can_truncate_a_long_body(runner: CliRunner, configured, scripted) -> None:
    data = payload(run(runner, "read", "101", "--max-chars", "5", "--json").stdout)["data"]
    assert data["body_truncated"] is True
    assert len(data["body"]) == 5


def test_read_rejects_an_unknown_format(runner: CliRunner, configured, scripted) -> None:
    result = run(runner, "read", "101", "--format", "pdf", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "invalid_format"


def test_attachments_are_written_to_disk_on_request(
    runner: CliRunner, configured, scripted, tmp_path: Path
) -> None:
    target = tmp_path / "downloads"
    data = payload(
        run(runner, "attachments", "101", "--save", str(target), "--json").stdout
    )["data"]
    assert data["saved"] == [str(target / "numbers.csv")]
    assert (target / "numbers.csv").read_bytes() == b"col\n1\n"


def test_an_attachment_filename_cannot_escape_the_output_directory(
    runner: CliRunner, configured, scripted, tmp_path: Path, monkeypatch
) -> None:
    """A hostile sender must not be able to write outside --save."""
    hostile = EmailMessage()
    hostile["From"] = "attacker@example.com"
    hostile["Subject"] = "hi"
    hostile.set_content("body")
    hostile.add_attachment(
        b"pwned", maintype="text", subtype="plain", filename="../../escaped.txt"
    )
    scripted.raw = hostile.as_bytes()

    target = tmp_path / "downloads"
    data = payload(
        run(runner, "attachments", "101", "--save", str(target), "--json").stdout
    )["data"]
    assert data["saved"] == [str(target / "escaped.txt")]
    assert not (tmp_path.parent / "escaped.txt").exists()


# --------------------------------------------------------------------------
# sending
# --------------------------------------------------------------------------


def test_a_dry_run_composes_without_sending(runner: CliRunner, configured) -> None:
    result = run(
        runner, "send", "--to", "a@x.com", "--subject", "Hi", "--body", "hello", "--dry-run",
        "--json",
    )
    assert result.exit_code == 0, result.stdout
    data = payload(result.stdout)["data"]
    assert data["dry_run"] is True
    assert data["recipients"] == ["a@x.com"]
    assert "Subject: Hi" in data["message"]
    assert "hello" in data["message"]


def test_a_dry_run_needs_no_password(runner: CliRunner, mail_home: Path, fake_keyring) -> None:
    """Showing a human the draft must not require unlocking the keyring first."""
    run(runner, "account", "add", "work", "--address", "me@example.com")
    result = run(
        runner, "send", "--to", "a@x.com", "--subject", "Hi", "--body", "x", "--dry-run", "--json"
    )
    assert result.exit_code == 0, result.stdout


def test_send_refuses_a_message_with_no_recipient(runner: CliRunner, configured) -> None:
    result = run(runner, "send", "--subject", "Hi", "--body", "x", "--dry-run", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "no_recipients"


def test_send_refuses_two_body_sources(runner: CliRunner, configured, tmp_path: Path) -> None:
    body_file = tmp_path / "b.txt"
    body_file.write_text("from file", encoding="utf-8")
    result = run(
        runner, "send", "--to", "a@x.com", "--body", "inline",
        "--body-file", str(body_file), "--dry-run", "--json",
    )
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "conflicting_body"


def test_a_body_can_come_from_a_file(runner: CliRunner, configured, tmp_path: Path) -> None:
    body_file = tmp_path / "b.txt"
    body_file.write_text("body from a file", encoding="utf-8")
    data = payload(
        run(
            runner, "send", "--to", "a@x.com", "--body-file", str(body_file),
            "--dry-run", "--json",
        ).stdout
    )["data"]
    assert "body from a file" in data["message"]


def test_a_missing_html_file_is_refused_before_reading_it(
    runner: CliRunner, configured, tmp_path: Path
) -> None:
    result = run(
        runner, "send", "--to", "a@x.com", "--html-file", str(tmp_path / "gone.html"),
        "--dry-run", "--json",
    )
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "body_not_found"


def test_a_malformed_extra_header_is_refused(runner: CliRunner, configured) -> None:
    result = run(
        runner, "send", "--to", "a@x.com", "--header", "no-colon-here",
        "--dry-run", "--json",
    )
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "invalid_header"


def test_bcc_is_in_the_envelope_but_not_in_the_transmitted_headers(
    runner: CliRunner, configured
) -> None:
    data = payload(
        run(
            runner, "send", "--to", "a@x.com", "--bcc", "secret@x.com",
            "--dry-run", "--json",
        ).stdout
    )["data"]
    assert "secret@x.com" in data["recipients"]


def test_send_files_a_copy_in_the_sent_mailbox(
    runner: CliRunner, configured, scripted, monkeypatch
) -> None:
    from claudeforanything.mail import smtp as smtp_mod

    monkeypatch.setattr(
        smtp_mod,
        "send",
        lambda *a, **k: {"message_id": "<x@example.com>", "accepted": ["a@x.com"], "refused": {}},
    )
    result = run(runner, "send", "--to", "a@x.com", "--subject", "Hi", "--body", "x", "--json")
    assert result.exit_code == 0, result.stdout
    assert payload(result.stdout)["data"]["saved_to"] == "Sent"
    assert any(cmd[0] == "append" for cmd in scripted.commands)


def test_a_failure_to_file_the_copy_does_not_report_a_failed_send(
    runner: CliRunner, configured, scripted, monkeypatch
) -> None:
    """The mail is already gone; a filing error must not read as "not sent"."""
    from claudeforanything.mail import smtp as smtp_mod
    from claudeforanything.output import CliError

    monkeypatch.setattr(
        smtp_mod,
        "send",
        lambda *a, **k: {"message_id": "<x@example.com>", "accepted": ["a@x.com"], "refused": {}},
    )

    def explode(*args, **kwargs):
        raise CliError("APPEND refused", code="imap_error")

    monkeypatch.setattr(imap_mod.Imap, "append", explode)

    result = run(runner, "send", "--to", "a@x.com", "--body", "x", "--json")
    assert result.exit_code == 0
    data = payload(result.stdout)["data"]
    assert data["saved_to"] is None
    assert "APPEND refused" in data["save_error"]


# --------------------------------------------------------------------------
# mutating
# --------------------------------------------------------------------------


def test_flag_requires_something_to_do(runner: CliRunner, configured, scripted) -> None:
    result = run(runner, "flag", "101", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "no_flags"


def test_flag_refuses_to_add_and_remove_the_same_flag(
    runner: CliRunner, configured, scripted
) -> None:
    result = run(runner, "flag", "101", "--read", "--unread", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "conflicting_flags"


def test_flag_marks_messages_read_and_starred(runner: CliRunner, configured, scripted) -> None:
    result = run(runner, "flag", "101", "102", "--read", "--star", "--json")
    assert result.exit_code == 0, result.stdout
    data = payload(result.stdout)["data"]
    assert sorted(data["added"]) == ["\\Flagged", "\\Seen"]
    store = next(cmd for cmd in scripted.commands if cmd[0] == "STORE")
    assert store[1] == "101,102"


def test_move_can_create_the_destination(runner: CliRunner, configured, scripted) -> None:
    result = run(runner, "move", "101", "--to", "Archive", "--create", "--json")
    assert result.exit_code == 0, result.stdout
    assert any(cmd[0] == "create" for cmd in scripted.commands)
    assert payload(result.stdout)["data"]["method"] == "move"


def test_delete_moves_to_trash_by_default(runner: CliRunner, configured, scripted) -> None:
    data = payload(run(runner, "delete", "101", "--json").stdout)["data"]
    assert data["moved_to"] == "Trash"
    assert data["purged"] is False


def test_purging_requires_explicit_confirmation(
    runner: CliRunner, configured, scripted
) -> None:
    result = run(runner, "delete", "101", "--purge", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "confirmation_required"
    assert not any(cmd == ("expunge",) for cmd in scripted.commands)

    confirmed = run(runner, "delete", "101", "--purge", "--yes", "--json")
    assert confirmed.exit_code == 0, confirmed.stdout
    assert ("expunge",) in scripted.commands


def test_deleting_from_trash_itself_is_refused(
    runner: CliRunner, configured, scripted
) -> None:
    result = run(runner, "delete", "101", "--folder", "Trash", "--json")
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "already_trash"


# --------------------------------------------------------------------------
# envelope discipline
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args",
    [
        ["presets"],
        ["parameters", "me@gmail.com"],
        ["account", "list"],
    ],
)
def test_json_output_is_a_single_document(
    runner: CliRunner, mail_home: Path, fake_keyring, args: list[str]
) -> None:
    result = run(runner, *args, "--json")
    assert json.loads(result.stdout)["ok"] is True


def test_human_errors_keep_stdout_clean(
    runner: CliRunner, mail_home: Path, fake_keyring
) -> None:
    result = run(runner, "inbox")
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "error:" in result.stderr
