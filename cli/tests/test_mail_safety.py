# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for the ways this plugin could lose or misdirect mail.

Everything here corresponds to a specific way the code was wrong, or could
quietly become wrong again. Each test says which.
"""

from __future__ import annotations

import poplib
import tomllib
from pathlib import Path

import pytest

from claudeforanything.mail import compat, message as message_mod, pop3 as pop3_mod
from claudeforanything.mail import smtp as smtp_mod
from claudeforanything.mail.accounts import Account, Endpoint
from claudeforanything.output import CliError


def account(**overrides) -> Account:
    base = dict(
        name="work",
        address="me@example.com",
        username="me@example.com",
        protocol="imap",
        incoming=Endpoint("imap.example.com", 993, "ssl"),
        outgoing=Endpoint("smtp.example.com", 587, "starttls"),
    )
    return Account(**{**base, **overrides})


# --------------------------------------------------------------------------
# Address parsing across Python versions
# --------------------------------------------------------------------------


def test_address_parsing_never_passes_strict_to_a_python_that_lacks_it() -> None:
    """`strict` landed in 3.12.6, but pyproject declares >=3.12.

    On 3.12.0-3.12.5 an unguarded `strict=` raises TypeError, which
    `message.addresses()` would swallow — silently emptying every From/To/Cc.
    """
    assert compat.get_addresses(["a@x.com"]) == [("", "a@x.com")]
    assert compat.parse_address("Bob <b@x.com>") == ("Bob", "b@x.com")


def test_the_fallback_path_matches_the_strict_capable_path() -> None:
    """Simulate an older 3.12 and confirm behaviour does not change."""
    values = ["a@x.com, Bob <b@x.com>", "c@x.com"]
    modern = compat.get_addresses(values)

    original = compat.SUPPORTS_STRICT
    try:
        compat.SUPPORTS_STRICT = False
        legacy = compat.get_addresses(values)
    finally:
        compat.SUPPORTS_STRICT = original

    assert legacy == modern


def test_declared_python_floor_is_consistent_with_how_the_code_calls_email_utils() -> None:
    """If someone re-raises the floor to >=3.12.6, the shim may be dropped.

    Until then the shim is load-bearing, so this pins the two together.
    """
    pyproject = tomllib.loads(
        (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    )
    floor = pyproject["project"]["requires-python"]
    assert floor == ">=3.12", (
        "requires-python changed; if the floor is now >=3.12.6, compat.py can be "
        "removed and email.utils called directly"
    )


def test_headers_still_parse_when_strict_is_unavailable(monkeypatch) -> None:
    """The bug this shim prevents: addresses vanishing rather than erroring."""
    monkeypatch.setattr(compat, "SUPPORTS_STRICT", False)
    parsed = message_mod.parse_headers(
        b"From: Alice <alice@example.com>\r\nTo: bob@example.com\r\n"
    )
    assert message_mod.addresses(parsed, "From") == [
        {"name": "Alice", "address": "alice@example.com"}
    ]


def test_detection_survives_a_genuinely_old_email_utils(monkeypatch) -> None:
    """Simulate 3.12.0-3.12.5 exactly: the keyword does not exist at all."""

    def legacy_getaddresses(fieldvalues):
        return [("", "a@x.com")]

    def legacy_parseaddr(addr):
        return ("", "a@x.com")

    monkeypatch.setattr(compat, "_getaddresses", legacy_getaddresses)
    monkeypatch.setattr(compat, "_parseaddr", legacy_parseaddr)
    monkeypatch.setattr(compat, "SUPPORTS_STRICT", compat._detect_strict_support())

    assert compat.SUPPORTS_STRICT is False, "detection must notice the keyword is gone"
    assert compat.get_addresses(["anything"]) == [("", "a@x.com")]
    assert compat.parse_address("anything") == ("", "a@x.com")


@pytest.mark.parametrize(
    "address",
    [
        "user+tag@sub.domain.co.uk",
        "a.b-c_d@example.museum",
        "x@localhost",
        "user%name@example.com",
        "o'brien@example.ie",
        "josé@example.com",
        "a@[192.168.0.1]",
    ],
)
def test_legitimate_addresses_survive_the_stricter_outbound_check(address: str) -> None:
    """The tightened validation must not start rejecting real mail."""
    assert smtp_mod.split_addresses([address], "--to") == [address]


# --------------------------------------------------------------------------
# Recipient smuggling
# --------------------------------------------------------------------------


def test_one_option_value_cannot_silently_become_two_recipients() -> None:
    """Lenient parsing turns this into two addresses; only one is visible."""
    with pytest.raises(CliError) as caught:
        smtp_mod.split_addresses(["a@x.com <b@evil.com>"], "--to")
    assert caught.value.code == "ambiguous_address"
    assert "b@evil.com" in caught.value.message


def test_a_comma_separated_list_is_still_allowed() -> None:
    """The check must not break the documented `--to "a@x, b@x"` form."""
    assert smtp_mod.split_addresses(["a@x.com, Bob <b@x.com>"], "--to") == [
        "a@x.com",
        "Bob <b@x.com>",
    ]


def test_a_display_name_with_an_address_is_not_treated_as_smuggling() -> None:
    assert smtp_mod.split_addresses(['"Bob Smith" <bob@x.com>'], "--to") == [
        "Bob Smith <bob@x.com>"
    ]


@pytest.mark.parametrize(
    "bad",
    ["no-at-sign", "two@at@signs.com", "spaces in@x.com", "trailing@", "@nolocal.com"],
)
def test_implausible_addresses_are_refused(bad: str) -> None:
    """What matters is that nothing is sent, not which refusal code fires.

    Input that leaves no parseable addr-spec at all trips `no_recipients`
    first, which is the accurate description of that state.
    """
    with pytest.raises(CliError) as caught:
        smtp_mod.compose(account(), smtp_mod.Draft(to=[bad]))
    assert caught.value.code in {"invalid_address", "ambiguous_address", "no_recipients"}


@pytest.mark.parametrize(
    ("written", "sent"),
    [("a@x.com>", "a@x.com"), ("<a@x.com", "a@x.com"), (" a@x.com ", "a@x.com")],
)
def test_a_stray_bracket_is_normalised_rather_than_refused(written: str, sent: str) -> None:
    """These are typos with one obvious reading, and the result is shown in --dry-run."""
    assert smtp_mod.split_addresses([written], "--to") == [sent]


def test_a_semicolon_separated_list_is_refused_rather_than_guessed() -> None:
    """Outlook uses `;`. Lenient parsing splits on it, which is a silent expansion."""
    with pytest.raises(CliError) as caught:
        smtp_mod.split_addresses(["a@x.com;b@y.com"], "--to")
    assert caught.value.code == "ambiguous_address"


# --------------------------------------------------------------------------
# What --dry-run actually shows
# --------------------------------------------------------------------------


def test_serialize_matches_what_smtplib_transmits() -> None:
    """`as_string()` is not the wire form; `serialize()` has to be."""
    msg = smtp_mod.compose(
        account(),
        smtp_mod.Draft(to=["a@x.com"], bcc=["secret@x.com"], subject="Hi", body="hello"),
    )
    wire = smtp_mod.serialize(msg)

    assert b"secret@x.com" not in wire, "Bcc must not be transmitted"
    assert wire.count(b"\n") == wire.count(b"\r\n"), "every newline must be CRLF"
    assert b"Subject: Hi" in wire

    # as_string() is the thing this used to show, and it differs on both counts.
    assert "secret@x.com" in msg.as_string()
    assert wire.decode() != msg.as_string()


def test_serialize_leaves_the_original_message_intact() -> None:
    """The Sent copy should still record who was Bcc'd."""
    msg = smtp_mod.compose(account(), smtp_mod.Draft(to=["a@x.com"], bcc=["s@x.com"]))
    smtp_mod.serialize(msg)
    assert msg["Bcc"] == "s@x.com"


def test_smtputf8_is_detected_so_the_preview_can_admit_it_is_not_exact() -> None:
    assert smtp_mod.needs_smtputf8("me@example.com", ["a@x.com"]) is False
    assert smtp_mod.needs_smtputf8("me@example.com", ["josé@example.com"]) is True


# --------------------------------------------------------------------------
# POP3 deletion is a commit
# --------------------------------------------------------------------------


class FakePop3:
    """A POP3 connection that fails DELE on a chosen message number."""

    def __init__(self, fail_on: int | None = None) -> None:
        self.fail_on = fail_on
        self.commands: list[str] = []

    def dele(self, which):
        if which == self.fail_on:
            raise poplib.error_proto(b"-ERR no such message")
        self.commands.append(f"DELE {which}")

    def rset(self):
        self.commands.append("RSET")

    def quit(self):
        self.commands.append("QUIT")

    def close(self):
        self.commands.append("CLOSE")


def test_a_clean_pop3_delete_commits() -> None:
    fake = FakePop3()
    session = pop3_mod.Pop3(fake, account(protocol="pop3"))  # type: ignore[arg-type]
    session.delete([1, 2])
    session.close(commit=True)
    assert fake.commands == ["DELE 1", "DELE 2", "QUIT"]


def test_a_half_finished_pop3_delete_is_discarded_not_committed() -> None:
    """The regression: QUIT commits, so a failed batch must RSET first.

    Deleting [1, 2] where 2 fails used to leave `_dirty` False, so the
    context manager's commit path sent QUIT and made the deletion of 1
    permanent — while the command reported failure.
    """
    fake = FakePop3(fail_on=2)
    session = pop3_mod.Pop3(fake, account(protocol="pop3"))  # type: ignore[arg-type]

    with pytest.raises(CliError):
        session.delete([1, 2])

    session.close(commit=False)
    assert fake.commands == ["DELE 1", "RSET", "QUIT"]
    assert fake.commands.index("RSET") < fake.commands.index("QUIT")


def test_an_exception_in_the_pop3_session_discards_pending_deletions(monkeypatch) -> None:
    """End to end through the context manager, which is where the bug lived."""
    fake = FakePop3()
    monkeypatch.setattr(pop3_mod, "_open", lambda account, timeout: fake)
    fake.user = lambda name: None  # type: ignore[attr-defined]
    fake.pass_ = lambda pw: None  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError):
        with pop3_mod.connect(
            account(protocol="pop3"), "pw", commit_deletes=True
        ) as session:
            session.delete([1])
            raise RuntimeError("something went wrong afterwards")

    assert "RSET" in fake.commands, "an aborted session must not commit deletions"


def test_deleting_nothing_marks_nothing() -> None:
    fake = FakePop3()
    session = pop3_mod.Pop3(fake, account(protocol="pop3"))  # type: ignore[arg-type]
    session.delete([])
    session.close(commit=False)
    assert fake.commands == ["QUIT"], "no RSET, because nothing was marked"
