# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine-level tests: no sockets, no CLI, no keyring."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from claudeforanything.mail import accounts as accounts_mod
from claudeforanything.mail import imap as imap_mod
from claudeforanything.mail import message as message_mod
from claudeforanything.mail import presets as presets_mod
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
# presets
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("address", "key"),
    [
        ("someone@gmail.com", "gmail"),
        ("SOMEONE@GMAIL.COM", "gmail"),
        ("a.b+tag@googlemail.com", "gmail"),
        ("x@icloud.com", "icloud"),
        ("x@hotmail.fr", "outlook"),
    ],
)
def test_known_domains_resolve_to_their_preset(address: str, key: str) -> None:
    chosen, known = presets_mod.resolve(address)
    assert known is True
    assert chosen.key == key


def test_unknown_domain_falls_back_to_a_labelled_guess() -> None:
    chosen, known = presets_mod.resolve("me@acme-widgets.example")
    assert known is False
    assert chosen.key == "generic"
    assert chosen.imap_host == "imap.acme-widgets.example"
    assert chosen.notes, "a guess must say it is a guess"


def test_every_preset_domain_is_indexed_once() -> None:
    """A domain listed under two presets would resolve arbitrarily."""
    seen: set[str] = set()
    for preset in presets_mod.PRESETS:
        for domain in preset.domains:
            assert domain not in seen, domain
            seen.add(domain)


def test_domain_of_handles_a_bare_domain() -> None:
    assert presets_mod.domain_of("example.com") == ""
    assert presets_mod.domain_of("me@Example.COM") == "example.com"


# --------------------------------------------------------------------------
# accounts store
# --------------------------------------------------------------------------


def test_store_round_trips_through_disk(tmp_path: Path) -> None:
    store = accounts_mod.Store(accounts={}, default=None, path=tmp_path / "accounts.json")
    store.put(account(display_name="Me", insecure_tls=True, sent_folder="Sent"))
    store.default = "work"
    accounts_mod.save(store)

    reloaded = accounts_mod.load(tmp_path / "accounts.json")
    assert reloaded.default == "work"
    assert reloaded.get("work") == store.get("work")


def test_a_missing_store_is_empty_rather_than_an_error(tmp_path: Path) -> None:
    assert accounts_mod.load(tmp_path / "nope.json").accounts == {}


def test_resolving_without_a_default_and_several_accounts_is_an_error(tmp_path: Path) -> None:
    store = accounts_mod.Store(accounts={}, default=None, path=tmp_path / "a.json")
    store.put(account(name="one"))
    store.put(account(name="two"))
    with pytest.raises(CliError) as caught:
        store.get(None)
    assert caught.value.code == "ambiguous_account"


def test_a_single_account_needs_no_default(tmp_path: Path) -> None:
    store = accounts_mod.Store(accounts={}, default=None, path=tmp_path / "a.json")
    store.put(account(name="only"))
    assert store.get(None).name == "only"


def test_removing_the_default_promotes_another_account(tmp_path: Path) -> None:
    store = accounts_mod.Store(accounts={}, default="one", path=tmp_path / "a.json")
    store.put(account(name="one"))
    store.put(account(name="two"))
    store.remove("one")
    assert store.default == "two"


def test_the_stored_file_never_contains_a_password(tmp_path: Path) -> None:
    """The whole point of the keyring split, asserted rather than assumed."""
    store = accounts_mod.Store(accounts={}, default=None, path=tmp_path / "accounts.json")
    store.put(account())
    accounts_mod.save(store)
    text = (tmp_path / "accounts.json").read_text(encoding="utf-8")
    assert "password" not in text.lower()


def test_default_port_follows_the_security_mode() -> None:
    assert accounts_mod.default_port("imap", "ssl") == 993
    assert accounts_mod.default_port("imap", "starttls") == 143
    assert accounts_mod.default_port("smtp", "ssl") == 465
    assert accounts_mod.default_port("pop3", "ssl") == 995


# --------------------------------------------------------------------------
# IMAP wire encoding
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    ["INBOX", "Sent", "[Gmail]/Sent Mail", "Éléments envoyés", "日本語", "R&D", "A&B-C", "a/b"],
)
def test_mailbox_names_round_trip_through_modified_utf7(name: str) -> None:
    assert imap_mod.decode_mailbox(imap_mod.encode_mailbox(name)) == name


def test_modified_utf7_matches_the_rfc_examples() -> None:
    # RFC 3501 §5.1.3 gives this exact pair.
    assert imap_mod.encode_mailbox("~peter/mail/台北/日本語") == (
        b"~peter/mail/&U,BTFw-/&ZeVnLIqe-"
    )
    assert imap_mod.decode_mailbox(b"~peter/mail/&U,BTFw-/&ZeVnLIqe-") == (
        "~peter/mail/台北/日本語"
    )


def test_encoded_mailbox_arguments_are_pure_ascii() -> None:
    """imaplib encodes str arguments as ASCII, so anything else raises."""
    arg = imap_mod.mailbox_arg("Éléments envoyés")
    assert arg.isascii()
    assert arg.startswith('"') and arg.endswith('"')


def test_mailbox_quoting_escapes_quotes_and_backslashes() -> None:
    assert imap_mod.mailbox_arg('we"ird\\name') == '"we\\"ird\\\\name"'


def test_search_criteria_are_assembled_in_imap_form() -> None:
    criteria = imap_mod.Criteria(unseen=True, sender="boss@corp.com", since="2026-01-05")
    assert criteria.terms() == [b"UNSEEN", b"FROM", b'"boss@corp.com"', b"SINCE", b"05-Jan-2026"]
    assert criteria.needs_utf8() is False


def test_empty_criteria_search_everything() -> None:
    assert imap_mod.Criteria().terms() == [b"ALL"]


def test_non_ascii_criteria_request_a_utf8_charset() -> None:
    criteria = imap_mod.Criteria(subject="café")
    assert criteria.needs_utf8() is True
    assert b'"caf\xc3\xa9"' in criteria.terms()


def test_a_bad_date_is_rejected_before_it_reaches_the_server() -> None:
    with pytest.raises(CliError) as caught:
        imap_mod.Criteria(since="last tuesday").terms()
    assert caught.value.code == "invalid_date"


def test_search_values_containing_quotes_are_escaped() -> None:
    assert imap_mod.Criteria(subject='a "b"').terms()[1] == b'"a \\"b\\""'


# --------------------------------------------------------------------------
# IMAP response parsing, against a scripted server
# --------------------------------------------------------------------------

HEADER_BLOB = (
    b"From: Alice Example <alice@example.com>\r\n"
    b"To: me@example.com\r\n"
    b"Subject: =?utf-8?B?Y2Fmw6kgcMOpdGl0IGTDqWpldW5lcg==?=\r\n"
    b"Date: Tue, 18 Aug 2026 10:23:11 +0200\r\n"
    b"Message-ID: <abc@example.com>\r\n"
)


class FakeImap:
    """A scripted `imaplib.IMAP4`, replaying the byte shapes real servers send."""

    def __init__(self, *, capabilities: tuple[str, ...] = ("IMAP4REV1", "MOVE")) -> None:
        self.capabilities = capabilities
        self.commands: list[tuple] = []

    def list(self, directory='""', pattern="*"):
        return "OK", [
            rb'(\HasNoChildren) "/" "INBOX"',
            rb'(\HasNoChildren \Sent) "/" "[Gmail]/Sent Mail"',
            rb'(\HasNoChildren \Trash) "/" "Corbeille"',
            rb'(\Noselect \HasChildren) "/" "[Gmail]"',
            rb'(\HasNoChildren) "/" "&AMk-l&AOk-ments"',
        ]

    def select(self, mailbox="INBOX", readonly=False):
        self.commands.append(("select", mailbox, readonly))
        return "OK", [b"42"]

    def status(self, mailbox, names):
        return "OK", [b'"INBOX" (MESSAGES 42 UNSEEN 7 RECENT 0)']

    def expunge(self):
        self.commands.append(("expunge",))
        return "OK", [b"1"]

    def uid(self, command, *args):
        self.commands.append((command, *args))
        if command == "SEARCH":
            return "OK", [b"101 102 103"]
        if command == "FETCH":
            spec = args[1]
            if "RFC822.SIZE" in spec:
                return "OK", [
                    b'1 (UID 101 FLAGS (\\Seen) RFC822.SIZE 2048 '
                    b'INTERNALDATE "18-Aug-2026 10:23:11 +0200")',
                    b'2 (UID 102 FLAGS () RFC822.SIZE 900 '
                    b'INTERNALDATE "17-Aug-2026 09:00:00 +0200")',
                ]
            return "OK", [
                (b"1 (UID 101 BODY[HEADER.FIELDS (FROM)] {%d}" % len(HEADER_BLOB), HEADER_BLOB),
                b")",
                (b"2 (UID 102 BODY[HEADER.FIELDS (FROM)] {%d}" % len(HEADER_BLOB), HEADER_BLOB),
                b")",
            ]
        return "OK", [b""]

    def logout(self):
        return "BYE", [b"logging out"]


def session() -> imap_mod.Imap:
    return imap_mod.Imap(FakeImap(), account())  # type: ignore[arg-type]


def test_folders_are_parsed_with_flags_delimiter_and_decoded_names() -> None:
    listing = {folder.name: folder for folder in session().folders()}
    assert "INBOX" in listing
    assert listing["INBOX"].delimiter == "/"
    assert listing["Éléments"].name == "Éléments"
    assert listing["[Gmail]"].to_dict()["selectable"] is False
    assert listing["[Gmail]/Sent Mail"].special_use == "\\Sent"


def test_special_use_flags_locate_sent_and_trash_whatever_they_are_called() -> None:
    live = session()
    assert live.sent_folder() == "[Gmail]/Sent Mail"
    assert live.trash_folder() == "Corbeille"


def test_a_configured_folder_overrides_special_use_detection() -> None:
    live = imap_mod.Imap(FakeImap(), account(sent_folder="Custom/Sent"))  # type: ignore[arg-type]
    assert live.sent_folder() == "Custom/Sent"


def test_search_returns_uids_as_strings() -> None:
    assert session().search("INBOX", imap_mod.Criteria(unseen=True)) == ["101", "102", "103"]


def test_summaries_join_flags_size_and_decoded_headers() -> None:
    rows = session().summaries("INBOX", ["101", "102"])
    assert [row["uid"] for row in rows] == ["101", "102"]

    first = rows[0]
    assert first["from"] == "Alice Example"
    assert first["from_addresses"] == [{"name": "Alice Example", "address": "alice@example.com"}]
    assert first["subject"] == "café pétit déjeuner", "RFC 2047 words must be decoded"
    assert first["seen"] is True
    assert first["size"] == 2048
    assert first["date"].startswith("2026-08-18T10:23:11")

    assert rows[1]["seen"] is False


def test_a_listing_marks_probable_attachments_from_the_content_type() -> None:
    """A header-only fetch cannot walk the MIME tree, so this is an approximation."""
    mixed = message_mod.parse_headers(
        b"From: a@b.c\r\nSubject: x\r\n"
        b'Content-Type: multipart/mixed; boundary="x"\r\n'
    )
    plain = message_mod.parse_headers(
        b"From: a@b.c\r\nSubject: x\r\nContent-Type: text/plain\r\n"
    )
    assert message_mod.summarize(mixed)["likely_attachment"] is True
    assert message_mod.summarize(plain)["likely_attachment"] is False


def test_summaries_of_nothing_do_not_hit_the_server() -> None:
    live = session()
    assert live.summaries("INBOX", []) == []


def test_move_prefers_the_atomic_move_command_when_available() -> None:
    fake = FakeImap(capabilities=("IMAP4REV1", "MOVE"))
    live = imap_mod.Imap(fake, account())  # type: ignore[arg-type]
    assert live.move("INBOX", ["101"], "Archive") == "move"
    assert any(cmd[0] == "MOVE" for cmd in fake.commands)


def test_move_falls_back_to_copy_and_expunge_without_the_move_capability() -> None:
    fake = FakeImap(capabilities=("IMAP4REV1",))
    live = imap_mod.Imap(fake, account())  # type: ignore[arg-type]
    assert live.move("INBOX", ["101"], "Archive") == "copy+expunge"
    issued = [cmd[0] for cmd in fake.commands]
    assert "COPY" in issued and "STORE" in issued and ("expunge",) in fake.commands


def test_status_counts_are_parsed() -> None:
    assert session().status("INBOX") == {"messages": 42, "unseen": 7, "recent": 0}


def test_selecting_twice_in_the_same_mode_costs_one_round_trip() -> None:
    fake = FakeImap()
    live = imap_mod.Imap(fake, account())  # type: ignore[arg-type]
    live.select("INBOX", readonly=True)
    live.select("INBOX", readonly=True)
    assert [c for c in fake.commands if c[0] == "select"] == [("select", '"INBOX"', True)]


def test_reading_uses_body_peek_so_the_seen_flag_is_untouched() -> None:
    fake = FakeImap()
    live = imap_mod.Imap(fake, account())  # type: ignore[arg-type]
    live.fetch_message("INBOX", "101", mark_seen=False)
    specs = [cmd[2] for cmd in fake.commands if cmd[0] == "FETCH"]
    assert any("BODY.PEEK" in spec for spec in specs)
    assert not any(cmd[0] == "STORE" for cmd in fake.commands)


# --------------------------------------------------------------------------
# message parsing
# --------------------------------------------------------------------------


def build_message() -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "Bob <bob@example.com>, carol@example.com"
    msg["Subject"] = "Quarterly café report"
    msg["Date"] = "Tue, 18 Aug 2026 10:23:11 +0200"
    msg.set_content("Plain body with an accent: é\n")
    msg.add_alternative("<p>HTML body with an accent: &eacute;</p>", subtype="html")
    msg.add_attachment(b"%PDF-1.4 fake", maintype="application", subtype="pdf",
                       filename="report.pdf")
    msg.add_attachment("a,b\n1,2\n".encode(), maintype="text", subtype="csv",
                       filename="numbers.csv")
    return msg


def test_headers_and_addresses_are_decoded() -> None:
    parsed = message_mod.parse(build_message().as_bytes())
    assert message_mod.header(parsed, "Subject") == "Quarterly café report"
    assert message_mod.addresses(parsed, "To") == [
        {"name": "Bob", "address": "bob@example.com"},
        {"name": "", "address": "carol@example.com"},
    ]
    assert message_mod.sent_at(parsed) is not None


def test_both_bodies_are_reachable_and_plain_text_wins() -> None:
    parsed = message_mod.parse(build_message().as_bytes())
    assert "Plain body" in message_mod.body_text(parsed)
    assert "<p>" in message_mod.body_html(parsed)
    text, source = message_mod.readable_body(parsed)
    assert source == "text/plain"
    assert "Plain body" in text


def test_an_html_only_message_still_yields_readable_text() -> None:
    msg = EmailMessage()
    msg["From"] = "a@b.c"
    msg["Subject"] = "html only"
    msg.set_content("<h1>Title</h1><p>One</p><p>Two &amp; three</p>", subtype="html")

    parsed = message_mod.parse(msg.as_bytes())
    text, source = message_mod.readable_body(parsed)
    assert source == "text/html (stripped)"
    assert "Title" in text and "Two & three" in text
    assert "<" not in text


def test_html_stripping_drops_scripts_entirely() -> None:
    stripped = message_mod.html_to_text("<p>keep</p><script>alert('x')</script>")
    assert "keep" in stripped
    assert "alert" not in stripped


def test_attachments_are_listed_with_stable_indexes() -> None:
    parsed = message_mod.parse(build_message().as_bytes())
    listed = message_mod.attachments(parsed)
    assert [a.filename for a in listed] == ["report.pdf", "numbers.csv"]
    assert [a.index for a in listed] == [1, 2]
    assert listed[0].content_type == "application/pdf"
    assert listed[0].size == len(b"%PDF-1.4 fake")


def test_an_attachment_can_be_fetched_by_index_or_by_name() -> None:
    parsed = message_mod.parse(build_message().as_bytes())
    assert message_mod.attachment_bytes(parsed, "1") == ("report.pdf", b"%PDF-1.4 fake")
    assert message_mod.attachment_bytes(parsed, "numbers.csv")[1] == b"a,b\n1,2\n"
    with pytest.raises(KeyError):
        message_mod.attachment_bytes(parsed, "missing.txt")


def test_a_body_can_be_truncated_and_says_so() -> None:
    parsed = message_mod.parse(build_message().as_bytes())
    data = message_mod.detail(parsed, uid="1", max_chars=5)
    assert data["body_truncated"] is True
    assert len(data["body"]) == 5


def test_a_message_with_a_broken_charset_does_not_crash() -> None:
    raw = (
        b"From: a@b.c\r\n"
        b"Subject: broken\r\n"
        b'Content-Type: text/plain; charset="definitely-not-a-charset"\r\n'
        b"\r\n"
        b"body bytes \xff\xfe\r\n"
    )
    parsed = message_mod.parse(raw)
    text, _ = message_mod.readable_body(parsed)
    assert "body bytes" in text


def test_a_message_with_no_date_reports_none_rather_than_raising() -> None:
    parsed = message_mod.parse(b"From: a@b.c\r\nSubject: x\r\n\r\nhi\r\n")
    assert message_mod.sent_at(parsed) is None
    assert message_mod.summarize(parsed, uid="1")["date"] is None


# --------------------------------------------------------------------------
# composing
# --------------------------------------------------------------------------


def test_addresses_flatten_from_repeats_and_comma_lists() -> None:
    assert smtp_mod.split_addresses(["a@x.com", "b@x.com, Carol <c@x.com>"]) == [
        "a@x.com",
        "b@x.com",
        "Carol <c@x.com>",
    ]


def test_the_envelope_covers_to_cc_and_bcc() -> None:
    draft = smtp_mod.Draft(to=["a@x.com"], cc=["b@x.com"], bcc=["c@x.com"])
    assert draft.recipients() == ["a@x.com", "b@x.com", "c@x.com"]


def test_a_message_with_no_recipient_is_refused_before_connecting() -> None:
    with pytest.raises(CliError) as caught:
        smtp_mod.compose(account(), smtp_mod.Draft(subject="hi"))
    assert caught.value.code == "no_recipients"


def test_a_malformed_recipient_is_refused() -> None:
    with pytest.raises(CliError) as caught:
        smtp_mod.compose(account(), smtp_mod.Draft(to=["not-an-address"]))
    assert caught.value.code == "invalid_address"


def test_compose_sets_the_headers_a_client_needs() -> None:
    msg = smtp_mod.compose(
        account(display_name="Emerick"),
        smtp_mod.Draft(to=["a@x.com"], cc=["b@x.com"], subject="Hello"),
    )
    assert msg["From"] == "Emerick <me@example.com>"
    assert msg["To"] == "a@x.com"
    assert msg["Cc"] == "b@x.com"
    assert msg["Subject"] == "Hello"
    assert msg["Date"] and msg["Message-ID"]


def test_replying_sets_both_threading_headers() -> None:
    msg = smtp_mod.compose(
        account(), smtp_mod.Draft(to=["a@x.com"], in_reply_to="<parent@x.com>")
    )
    assert msg["In-Reply-To"] == "<parent@x.com>"
    assert msg["References"] == "<parent@x.com>", "clients thread on References"


def test_an_html_alternative_produces_a_multipart_message() -> None:
    msg = smtp_mod.compose(
        account(), smtp_mod.Draft(to=["a@x.com"], body="plain", html="<b>rich</b>")
    )
    parsed = message_mod.parse(msg.as_bytes())
    assert message_mod.body_text(parsed).strip() == "plain"
    assert "<b>rich</b>" in message_mod.body_html(parsed)


def test_attachments_survive_a_compose_and_reparse(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello attachment", encoding="utf-8")

    msg = smtp_mod.compose(
        account(),
        smtp_mod.Draft(
            to=["a@x.com"], body="see attached",
            attachments=[smtp_mod.Attachment.load(source)],
        ),
    )
    parsed = message_mod.parse(msg.as_bytes())
    listed = message_mod.attachments(parsed)
    assert [a.filename for a in listed] == ["notes.txt"]
    assert message_mod.attachment_bytes(parsed, "1")[1] == b"hello attachment"


def test_attaching_a_missing_file_fails_early() -> None:
    with pytest.raises(CliError) as caught:
        smtp_mod.Attachment.load(Path("no-such-file.bin"))
    assert caught.value.code == "attachment_not_found"


def test_bcc_is_on_the_draft_but_stripped_from_what_is_transmitted() -> None:
    """send_message flattens a copy without Bcc; the original keeps it for Sent."""
    import copy as copy_mod

    msg = smtp_mod.compose(account(), smtp_mod.Draft(to=["a@x.com"], bcc=["secret@x.com"]))
    assert msg["Bcc"] == "secret@x.com"

    transmitted = copy_mod.copy(msg)
    del transmitted["Bcc"]
    assert "secret@x.com" not in transmitted.as_string()
