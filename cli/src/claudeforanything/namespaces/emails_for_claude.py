# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""`claudeforanything emails-for-claude` — read, search, and send mail.

The verb list is deliberately small and composable, because that is how Claude
uses a terminal:

    emails-for-claude search --unseen --from boss@corp.com
    emails-for-claude read 4417 --max-chars 4000
    emails-for-claude send --to boss@corp.com --subject "Re: budget" --body-stdin

Every command takes `--json`, and nothing here ever prints a password.
"""

from __future__ import annotations

import base64
import sys
from dataclasses import replace
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Annotated, Any, Sequence

import typer

from ..mail import accounts as accounts_mod
from ..mail import imap as imap_mod
from ..mail import message as message_mod
from ..mail import pop3 as pop3_mod
from ..mail import presets as presets_mod
from ..mail import secrets, smtp as smtp_mod
from ..mail.accounts import Account, Endpoint
from ..output import CliError, JsonOption, emit, fail

app = typer.Typer(
    no_args_is_help=True,
    help="Read, search, and send email over IMAP, POP3 and SMTP.",
)

account_app = typer.Typer(
    no_args_is_help=True,
    help="Add, inspect, and remove accounts, and store their passwords in the OS keyring.",
)
app.add_typer(account_app, name="account")


# --------------------------------------------------------------------------
# Shared option types
# --------------------------------------------------------------------------

AccountOption = Annotated[
    str | None,
    typer.Option("--account", "-a", help="Account to use. Defaults to the configured default."),
]

FolderOption = Annotated[
    str, typer.Option("--folder", "-f", help="Mailbox to work in.")
]

TimeoutOption = Annotated[
    float, typer.Option("--timeout", min=1.0, help="Network timeout in seconds.")
]

YesOption = Annotated[
    bool, typer.Option("--yes", help="Confirm an irreversible operation.")
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _resolve(name: str | None) -> Account:
    return accounts_mod.load().get(name)


def _imap(name: str | None, timeout: float):
    """Open an IMAP session for an account, resolving its password first."""
    account = _resolve(name)
    password = secrets.require_password(account.name, account.username)
    return imap_mod.connect(account, password, timeout=timeout)


def _pop3(name: str | None, timeout: float, *, commit_deletes: bool = False):
    account = _resolve(name)
    password = secrets.require_password(account.name, account.username)
    return pop3_mod.connect(
        account, password, timeout=timeout, commit_deletes=commit_deletes
    )


def _short(text: str, width: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= width:
        return text.ljust(width)
    return text[: width - 1] + "…"


def _when(iso: str | None) -> str:
    if not iso:
        return " " * 16
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return _short(iso, 16)


def _row(entry: dict[str, Any]) -> str:
    """One message per line: status, uid, date, sender, subject."""
    marks = "".join(
        (
            " " if entry.get("seen") else "*",
            "!" if entry.get("flagged") else " ",
            "@" if entry.get("likely_attachment") else " ",
        )
    )
    return (
        f"{marks} {str(entry.get('uid') or ''):>7}  {_when(entry.get('date'))}  "
        f"{_short(entry.get('from') or '', 28)}  {_short(entry.get('subject') or '(no subject)', 60)}"
    ).rstrip()


def _listing_lines(entries: Sequence[dict[str, Any]], header: str) -> list[str]:
    lines = [header, ""]
    if not entries:
        lines.append("(no messages matched)")
        return lines
    lines.append(f"    {'UID':>7}  {'DATE':<16}  {'FROM':<28}  SUBJECT")
    lines += [_row(entry) for entry in entries]
    lines += ["", "* unread   ! flagged   @ likely has an attachment"]
    return lines


def _read_body(body: str | None, body_file: Path | None, body_stdin: bool) -> str:
    """Resolve the three ways a body can arrive into one string."""
    given = [x for x in (body is not None, body_file is not None, body_stdin) if x]
    if len(given) > 1:
        raise CliError(
            "pass only one of --body, --body-file, --body-stdin", code="conflicting_body"
        )
    if body_stdin:
        return sys.stdin.read()
    if body_file is not None:
        if not body_file.is_file():
            raise CliError(f"no such file: {body_file}", code="body_not_found")
        return body_file.read_text(encoding="utf-8")
    return body or ""


def _read_secret(prompt: str, *, from_stdin: bool) -> str:
    """Read a password without echoing it, or from a pipe when asked.

    `--stdin` is what makes this usable from a script:
    `pass show mail/work | claudeforanything emails-for-claude account set-password work --stdin`
    """
    if from_stdin:
        value = sys.stdin.readline().rstrip("\r\n")
    else:
        value = typer.prompt(prompt, hide_input=True)
    if not value:
        raise CliError("empty password", code="empty_password")
    return value


def _endpoints_from_preset(
    preset: presets_mod.Preset, protocol: str
) -> tuple[Endpoint | None, Endpoint]:
    """Endpoints implied by a preset. Incoming is None when the preset has none.

    A preset with `pop3_host = None` is stating that the provider offers no
    POP3, not inviting a substitute. Falling back to the IMAP host with the
    default POP3 port would invent an endpoint — Proton Bridge, which serves
    IMAP on 127.0.0.1:1143 and no POP3 at all, would come out as
    `127.0.0.1:995 ssl` — and that is exactly the guess-presented-as-fact this
    package refuses to make elsewhere. The caller turns None into an error that
    names what to pass instead.
    """
    if protocol == accounts_mod.POP3:
        incoming = (
            Endpoint(preset.pop3_host, preset.pop3_port, preset.pop3_security)
            if preset.pop3_host
            else None
        )
    else:
        incoming = Endpoint(preset.imap_host, preset.imap_port, preset.imap_security)
    outgoing = Endpoint(preset.smtp_host, preset.smtp_port, preset.smtp_security)
    return incoming, outgoing


def _account_view(account: Account, *, include_password_source: bool = True) -> dict[str, Any]:
    """The account as JSON. Never contains a password, by construction."""
    view = account.to_dict()
    view["from_header"] = account.from_header
    if include_password_source:
        view["password_source"] = secrets.describe_source(account.name, account.username)
        view["password_env_var"] = secrets.env_var_name(account.name)
    return view


def _account_lines(account: Account, store_default: str | None) -> list[str]:
    source = secrets.describe_source(account.name, account.username)
    label = {
        secrets.KEYRING: "OS keyring",
        secrets.ENVIRONMENT: f"${secrets.env_var_name(account.name)}",
        secrets.MISSING: "NOT STORED — run `account set-password`",
    }[source]
    lines = [
        f"{account.name}{'  (default)' if account.name == store_default else ''}",
        f"  address    {account.from_header}",
        f"  username   {account.username}",
        f"  incoming   {account.protocol.upper()}  {account.incoming.describe()}",
        f"  outgoing   SMTP  {account.outgoing.describe()}",
        f"  password   {label}",
    ]
    if account.sent_folder:
        lines.append(f"  sent       {account.sent_folder}")
    if account.trash_folder:
        lines.append(f"  trash      {account.trash_folder}")
    if account.insecure_tls:
        lines.append("  tls        certificate verification DISABLED (--insecure-tls)")
    if account.preset:
        lines.append(f"  preset     {account.preset}")
    return lines


# --------------------------------------------------------------------------
# account
# --------------------------------------------------------------------------


@account_app.command("add")
def account_add(
    name: Annotated[str, typer.Argument(help="Short label for this account, e.g. work.")],
    address: Annotated[str, typer.Option("--address", help="The email address.")],
    username: Annotated[
        str | None, typer.Option("--username", help="Login name. Defaults to the address.")
    ] = None,
    display_name: Annotated[
        str | None, typer.Option("--display-name", help="Name shown in the From header.")
    ] = None,
    protocol: Annotated[
        str, typer.Option("--protocol", help="Incoming protocol: imap or pop3.")
    ] = accounts_mod.IMAP,
    preset: Annotated[
        str | None,
        typer.Option("--preset", help="Provider preset key. Defaults to matching the address."),
    ] = None,
    imap_host: Annotated[str | None, typer.Option("--imap-host")] = None,
    imap_port: Annotated[int | None, typer.Option("--imap-port")] = None,
    imap_security: Annotated[
        str | None, typer.Option("--imap-security", help="ssl, starttls or none.")
    ] = None,
    smtp_host: Annotated[str | None, typer.Option("--smtp-host")] = None,
    smtp_port: Annotated[int | None, typer.Option("--smtp-port")] = None,
    smtp_security: Annotated[
        str | None, typer.Option("--smtp-security", help="ssl, starttls or none.")
    ] = None,
    sent_folder: Annotated[
        str | None, typer.Option("--sent-folder", help="Override the detected Sent mailbox.")
    ] = None,
    trash_folder: Annotated[
        str | None, typer.Option("--trash-folder", help="Override the detected Trash mailbox.")
    ] = None,
    insecure_tls: Annotated[
        bool,
        typer.Option("--insecure-tls", help="Skip certificate verification (Proton Bridge)."),
    ] = False,
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Read the password from stdin.")
    ] = False,
    prompt_password: Annotated[
        bool, typer.Option("--prompt-password", help="Prompt for the password now.")
    ] = False,
    set_default: Annotated[
        bool, typer.Option("--set-default/--no-set-default", help="Make this the default account.")
    ] = True,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing account.")] = False,
    as_json: JsonOption = False,
) -> None:
    """Add an account. Server settings come from the provider preset unless overridden."""
    try:
        protocol = accounts_mod.validate_protocol(protocol)
        if "@" not in address:
            raise CliError(f"{address!r} is not an email address", code="invalid_address")

        store = accounts_mod.load()
        if name in store.accounts and not force:
            raise CliError(
                f"account {name!r} already exists (pass --force to overwrite)", code="exists"
            )

        if preset:
            chosen = presets_mod.PRESETS_BY_KEY.get(preset)
            if chosen is None:
                known = ", ".join(sorted(presets_mod.PRESETS_BY_KEY))
                raise CliError(f"unknown preset {preset!r}. Known: {known}", code="unknown_preset")
            known_preset = True
        else:
            chosen, known_preset = presets_mod.resolve(address)

        derived, outgoing = _endpoints_from_preset(chosen, protocol)

        if derived is None and imap_host is None:
            raise CliError(
                f"preset {chosen.key!r} ({chosen.label}) declares no POP3 server, so "
                "there is nothing for --protocol pop3 to derive settings from. Pass "
                "--imap-host (with --imap-port/--imap-security as needed) using the "
                "settings your provider documents, or drop --protocol pop3 to use "
                "IMAP.",
                code="no_pop3_preset",
            )

        # When the preset had nothing, the explicit --imap-* options below are the
        # entire source of truth; seed only so they have something to replace.
        security = imap_security or presets_mod.SSL
        incoming = derived or Endpoint(
            host=imap_host or "",
            port=imap_port or accounts_mod.default_port(protocol, security),
            security=security,
        )

        if imap_security is not None:
            incoming = replace(incoming, security=accounts_mod.validate_security(imap_security))
            if imap_port is None:
                incoming = replace(
                    incoming, port=accounts_mod.default_port(protocol, incoming.security)
                )
        if imap_host is not None:
            incoming = replace(incoming, host=imap_host)
        if imap_port is not None:
            incoming = replace(incoming, port=imap_port)

        if smtp_security is not None:
            outgoing = replace(outgoing, security=accounts_mod.validate_security(smtp_security))
            if smtp_port is None:
                outgoing = replace(
                    outgoing, port=accounts_mod.default_port("smtp", outgoing.security)
                )
        if smtp_host is not None:
            outgoing = replace(outgoing, host=smtp_host)
        if smtp_port is not None:
            outgoing = replace(outgoing, port=smtp_port)

        account = Account(
            name=name,
            address=address,
            username=username or address,
            protocol=protocol,
            incoming=incoming,
            outgoing=outgoing,
            display_name=display_name,
            sent_folder=sent_folder,
            trash_folder=trash_folder,
            insecure_tls=insecure_tls,
            preset=chosen.key if known_preset else None,
        )

        store.put(account)
        if set_default or store.default is None:
            store.default = name
        path = accounts_mod.save(store)

        stored_password = False
        if password_stdin or prompt_password:
            secrets.set_password(
                name,
                account.username,
                _read_secret(f"Password for {account.address}", from_stdin=password_stdin),
            )
            stored_password = True

        warnings: list[str] = []
        if not known_preset and imap_host is None and smtp_host is None:
            warnings.append(
                f"No preset matched {presets_mod.domain_of(address)}, so the hosts above "
                f"are conventions, not published settings. Verify with: "
                f"claudeforanything emails-for-claude parameters {address} --probe"
            )
        if not stored_password:
            warnings.append(
                f"No password stored yet. Run: claudeforanything emails-for-claude "
                f"account set-password {name}"
            )

        emit(
            {
                "account": _account_view(account),
                "path": str(path),
                "default": store.default,
                "preset": chosen.key,
                "preset_known": known_preset,
                "password_stored": stored_password,
                "notes": list(chosen.notes),
                "warnings": warnings,
            },
            [
                f"added account {name}",
                "",
                *_account_lines(account, store.default),
                "",
                *(f"note: {n}" for n in chosen.notes),
                *(("",) if chosen.notes and warnings else ()),
                *(f"warning: {w}" for w in warnings),
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@account_app.command("list")
def account_list(as_json: JsonOption = False) -> None:
    """List configured accounts."""
    try:
        store = accounts_mod.load()
        views = [_account_view(a) for a in sorted(store.accounts.values(), key=lambda a: a.name)]
        lines: list[str] = []
        if not views:
            lines = [
                "no accounts configured",
                "",
                "Add one with:",
                "  claudeforanything emails-for-claude account add work "
                "--address you@example.com --prompt-password",
            ]
        else:
            for account in sorted(store.accounts.values(), key=lambda a: a.name):
                lines += _account_lines(account, store.default) + [""]
        emit(
            {
                "accounts": views,
                "default": store.default,
                "path": str(accounts_mod.accounts_path()),
            },
            lines,
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@account_app.command("show")
def account_show(
    name: Annotated[str | None, typer.Argument(help="Account name.")] = None,
    as_json: JsonOption = False,
) -> None:
    """Show one account, including where its password comes from."""
    try:
        store = accounts_mod.load()
        account = store.get(name)
        emit(
            {"account": _account_view(account), "default": store.default},
            _account_lines(account, store.default),
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@account_app.command("set-password")
def account_set_password(
    name: Annotated[str | None, typer.Argument(help="Account name.")] = None,
    from_stdin: Annotated[
        bool, typer.Option("--stdin", help="Read the password from stdin instead of prompting.")
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Store an account's password in the OS keyring.

    The value is read without echo, never written to accounts.json, and never
    printed back.
    """
    try:
        account = _resolve(name)
        password = _read_secret(f"Password for {account.address}", from_stdin=from_stdin)
        secrets.set_password(account.name, account.username, password)
        emit(
            {
                "account": account.name,
                "username": account.username,
                "backend": secrets.backend_name(),
                "service": secrets.service_name(account.name),
            },
            [
                f"stored the password for {account.name} ({account.username})",
                f"  backend  {secrets.backend_name()}",
                f"  service  {secrets.service_name(account.name)}",
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@account_app.command("set-default")
def account_set_default(
    name: Annotated[str, typer.Argument(help="Account to make the default.")],
    as_json: JsonOption = False,
) -> None:
    """Choose the account used when --account is omitted."""
    try:
        store = accounts_mod.load()
        account = store.get(name)
        store.default = account.name
        accounts_mod.save(store)
        emit({"default": account.name}, [f"default account is now {account.name}"], as_json=as_json)
    except CliError as error:
        fail(error, as_json=as_json)


@account_app.command("remove")
def account_remove(
    name: Annotated[str, typer.Argument(help="Account to remove.")],
    keep_password: Annotated[
        bool, typer.Option("--keep-password", help="Leave the password in the keyring.")
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Remove an account, and by default forget its password too."""
    try:
        store = accounts_mod.load()
        account = store.remove(name)
        accounts_mod.save(store)
        forgotten = False
        if not keep_password:
            forgotten = secrets.delete_password(account.name, account.username)
        emit(
            {"removed": account.name, "password_forgotten": forgotten, "default": store.default},
            [
                f"removed account {account.name}",
                (
                    "  password forgotten"
                    if forgotten
                    else "  password left in the keyring"
                    if keep_password
                    else "  no password was stored"
                ),
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@account_app.command("test")
def account_test(
    name: AccountOption = None,
    incoming: Annotated[
        bool, typer.Option("--incoming/--no-incoming", help="Test IMAP or POP3.")
    ] = True,
    outgoing: Annotated[
        bool, typer.Option("--outgoing/--no-outgoing", help="Test SMTP.")
    ] = True,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """Log in to the configured servers and report what happened.

    Sends nothing. This is the command to run when something else fails, since
    it separates "wrong host" from "wrong password" from "provider blocks
    password auth".
    """
    try:
        account = _resolve(name)
        password = secrets.require_password(account.name, account.username)
        results: list[dict[str, Any]] = []

        if incoming:
            entry: dict[str, Any] = {
                "leg": account.protocol,
                "endpoint": account.incoming.describe(),
            }
            try:
                if account.protocol == accounts_mod.IMAP:
                    with imap_mod.connect(account, password, timeout=timeout) as session:
                        entry["ok"] = True
                        entry["capabilities"] = list(session.capabilities)
                        entry["folders"] = len(session.folders())
                        entry["inbox"] = session.status("INBOX")
                else:
                    with pop3_mod.connect(account, password, timeout=timeout) as pop:
                        listing = pop.listing()
                        entry["ok"] = True
                        entry["messages"] = len(listing)
                        entry["capabilities"] = sorted(pop.capabilities())
            except CliError as error:
                entry["ok"] = False
                entry["error"] = error.message
            results.append(entry)

        if outgoing:
            entry = {"leg": "smtp", "endpoint": account.outgoing.describe()}
            try:
                conn = smtp_mod._open(account, timeout)
                try:
                    conn.login(account.username, password)
                    entry["ok"] = True
                    entry["extensions"] = sorted(conn.esmtp_features)
                finally:
                    try:
                        conn.quit()
                    except Exception:
                        pass
            except CliError as error:
                entry["ok"] = False
                entry["error"] = error.message
            except Exception as error:
                entry["ok"] = False
                entry["error"] = str(error)
            results.append(entry)

        passed = all(entry.get("ok") for entry in results)
        lines = [f"account {account.name} ({account.address})", ""]
        for entry in results:
            mark = "ok  " if entry.get("ok") else "FAIL"
            lines.append(f"{mark} {entry['leg']:<5} {entry['endpoint']}")
            if not entry.get("ok"):
                lines.append(f"       {entry.get('error', '')}")
            elif entry["leg"] == "imap":
                counts = entry.get("inbox", {})
                lines.append(
                    f"       {entry.get('folders', 0)} folders, INBOX has "
                    f"{counts.get('messages', '?')} messages "
                    f"({counts.get('unseen', '?')} unseen)"
                )
            elif entry["leg"] == "pop3":
                lines.append(f"       {entry.get('messages', 0)} messages in the maildrop")

        emit({"passed": passed, "account": account.name, "results": results}, lines, as_json=as_json)
        if not passed:
            raise typer.Exit(1)
    except CliError as error:
        fail(error, as_json=as_json)


# --------------------------------------------------------------------------
# parameters / presets
# --------------------------------------------------------------------------


def _probe(host: str, port: int, security: str, insecure: bool, timeout: float) -> dict[str, Any]:
    """Open a socket and read the server greeting, to confirm a host is real."""
    import socket as socket_mod
    import ssl as ssl_mod

    result: dict[str, Any] = {"host": host, "port": port, "security": security}
    try:
        raw = socket_mod.create_connection((host, port), timeout=timeout)
    except OSError as error:
        result["ok"] = False
        result["error"] = str(error)
        return result

    try:
        sock = raw
        if security == presets_mod.SSL:
            sock = imap_mod.ssl_context(insecure).wrap_socket(raw, server_hostname=host)
        sock.settimeout(timeout)
        greeting = sock.recv(512)
        result["ok"] = True
        result["greeting"] = greeting.decode("utf-8", "replace").strip()
    except (OSError, ssl_mod.SSLError) as error:
        result["ok"] = False
        result["error"] = str(error)
    finally:
        try:
            raw.close()
        except OSError:
            pass
    return result


@app.command()
def parameters(
    target: Annotated[
        str | None,
        typer.Argument(help="An email address, a domain, or a configured account name."),
    ] = None,
    probe: Annotated[
        bool, typer.Option("--probe", help="Connect to each host and read its greeting.")
    ] = False,
    timeout: TimeoutOption = 10.0,
    as_json: JsonOption = False,
) -> None:
    """Report the server settings for an address, or for a configured account.

    With no argument it describes the default account. With an address it
    answers "what do I type for host and port?" — from a published preset when
    the domain is known, and from the `imap.<domain>` convention otherwise,
    clearly labelled as a guess. `--probe` turns a guess into a fact.
    """
    try:
        store = accounts_mod.load()

        if target is not None and target in store.accounts:
            account = store.accounts[target]
        elif target is None:
            account = store.get(None)
        else:
            account = None

        if account is not None:
            candidates = [
                (account.protocol, account.incoming),
                ("smtp", account.outgoing),
            ]
            probes = (
                [
                    _probe(ep.host, ep.port, ep.security, account.insecure_tls, timeout)
                    | {"leg": leg}
                    for leg, ep in candidates
                ]
                if probe
                else []
            )
            emit(
                {
                    "source": "account",
                    "account": _account_view(account),
                    "probes": probes,
                },
                [
                    *_account_lines(account, store.default),
                    *(("",) if probes else ()),
                    *(
                        f"probe {p['leg']:<9} {p['host']}:{p['port']}  "
                        + ("ok  " + p.get("greeting", "")[:70] if p.get("ok") else "FAIL " + str(p.get("error")))
                        for p in probes
                    ),
                ],
                as_json=as_json,
            )
            return

        chosen, known = presets_mod.resolve(target)
        rows = [
            ("IMAP", chosen.imap_host, chosen.imap_port, chosen.imap_security),
            ("POP3", chosen.pop3_host or "-", chosen.pop3_port, chosen.pop3_security),
            ("SMTP", chosen.smtp_host, chosen.smtp_port, chosen.smtp_security),
        ]
        probes = (
            [
                _probe(host, port, security, False, timeout) | {"leg": label}
                for label, host, port, security in rows
                if host != "-"
            ]
            if probe
            else []
        )

        emit(
            {
                "source": "preset" if known else "guess",
                "target": target,
                "domain": presets_mod.domain_of(target) or target,
                "preset": {
                    "key": chosen.key,
                    "label": chosen.label,
                    "imap": {
                        "host": chosen.imap_host,
                        "port": chosen.imap_port,
                        "security": chosen.imap_security,
                    },
                    "pop3": {
                        "host": chosen.pop3_host,
                        "port": chosen.pop3_port,
                        "security": chosen.pop3_security,
                    },
                    "smtp": {
                        "host": chosen.smtp_host,
                        "port": chosen.smtp_port,
                        "security": chosen.smtp_security,
                    },
                    "notes": list(chosen.notes),
                },
                "probes": probes,
                "suggested_command": (
                    f"claudeforanything emails-for-claude account add <name> "
                    f"--address {target} --prompt-password"
                ),
            },
            [
                f"{chosen.label}  [{'published settings' if known else 'GUESS'}]",
                "",
                *(
                    f"  {label:<5} {host}:{port}  ({security})"
                    for label, host, port, security in rows
                ),
                "",
                *(f"  note: {n}" for n in chosen.notes),
                *(("",) if probes else ()),
                *(
                    f"  probe {p['leg']:<5} {p['host']}:{p['port']}  "
                    + (
                        "ok  " + p.get("greeting", "")[:70]
                        if p.get("ok")
                        else "FAIL " + str(p.get("error"))
                    )
                    for p in probes
                ),
                "",
                "  add it with:",
                f"    claudeforanything emails-for-claude account add <name> "
                f"--address {target} --prompt-password",
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@app.command()
def presets(as_json: JsonOption = False) -> None:
    """List the providers with built-in settings."""
    data = [
        {
            "key": preset.key,
            "label": preset.label,
            "domains": list(preset.domains),
            "imap": f"{preset.imap_host}:{preset.imap_port} ({preset.imap_security})",
            "smtp": f"{preset.smtp_host}:{preset.smtp_port} ({preset.smtp_security})",
        }
        for preset in presets_mod.PRESETS
    ]
    width = max(len(p["key"]) for p in data)
    emit(
        {"presets": data},
        [
            f"{p['key']:<{width}}  {p['label']}"
            for p in data
        ]
        + ["", "Details for one domain: emails-for-claude parameters <address>"],
        as_json=as_json,
    )


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------


@app.command()
def folders(
    account: AccountOption = None,
    counts: Annotated[
        bool, typer.Option("--counts", help="Also fetch message and unseen counts per folder.")
    ] = False,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """List the mailboxes on the server."""
    try:
        with _imap(account, timeout) as session:
            listing = [folder.to_dict() for folder in session.folders()]
            if counts:
                for entry in listing:
                    if entry["selectable"]:
                        try:
                            entry["counts"] = session.status(entry["name"])
                        except CliError:
                            entry["counts"] = None

        width = max((len(entry["name"]) for entry in listing), default=4)
        lines = []
        for entry in listing:
            suffix = entry["special_use"] or ""
            if entry.get("counts"):
                got = entry["counts"]
                suffix = (
                    f"{suffix}  {got.get('messages', 0)} messages, "
                    f"{got.get('unseen', 0)} unseen"
                ).strip()
            lines.append(f"{entry['name']:<{width}}  {suffix}".rstrip())

        emit({"folders": listing, "count": len(listing)}, lines, as_json=as_json)
    except CliError as error:
        fail(error, as_json=as_json)


def _criteria(
    unseen: bool, seen: bool, flagged: bool, answered: bool, sender: str | None,
    recipient: str | None, subject: str | None, text: str | None, body: str | None,
    since: str | None, before: str | None, larger: int | None, has_attachment: bool,
    query: str | None,
) -> imap_mod.Criteria:
    return imap_mod.Criteria(
        unseen=unseen, seen=seen, flagged=flagged, answered=answered, sender=sender,
        recipient=recipient, subject=subject, text=text, body=body, since=since,
        before=before, larger=larger, has_attachment=has_attachment, raw=query,
    )


@app.command()
def inbox(
    account: AccountOption = None,
    folder: FolderOption = "INBOX",
    limit: Annotated[int, typer.Option("--limit", "-n", min=1, help="How many to show.")] = 25,
    offset: Annotated[int, typer.Option("--offset", min=0, help="Skip this many first.")] = 0,
    oldest: Annotated[
        bool, typer.Option("--oldest", help="Oldest first. Default is newest first.")
    ] = False,
    unseen: Annotated[bool, typer.Option("--unseen", help="Only unread messages.")] = False,
    seen: Annotated[bool, typer.Option("--seen", help="Only read messages.")] = False,
    flagged: Annotated[bool, typer.Option("--flagged", help="Only flagged/starred.")] = False,
    answered: Annotated[bool, typer.Option("--answered", help="Only answered.")] = False,
    sender: Annotated[str | None, typer.Option("--from", help="Match the From header.")] = None,
    recipient: Annotated[str | None, typer.Option("--to", help="Match the To header.")] = None,
    subject: Annotated[str | None, typer.Option("--subject", help="Match the Subject.")] = None,
    text: Annotated[
        str | None, typer.Option("--search", help="Match anywhere: headers and body.")
    ] = None,
    body: Annotated[str | None, typer.Option("--body", help="Match the body only.")] = None,
    since: Annotated[str | None, typer.Option("--since", help="On or after YYYY-MM-DD.")] = None,
    before: Annotated[str | None, typer.Option("--before", help="Before YYYY-MM-DD.")] = None,
    larger: Annotated[int | None, typer.Option("--larger", help="Bigger than N bytes.")] = None,
    has_attachment: Annotated[
        bool, typer.Option("--has-attachment", help="Approximate: multipart/mixed only.")
    ] = False,
    query: Annotated[
        str | None, typer.Option("--query", help="Raw IMAP search expression, appended as-is.")
    ] = None,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """List messages in a mailbox, newest first.

    Filters map onto IMAP SEARCH and run on the server, so `--from` over a
    mailbox of 50,000 messages costs one round trip, not 50,000.
    """
    try:
        resolved = _resolve(account)
        criteria = _criteria(
            unseen, seen, flagged, answered, sender, recipient, subject, text, body,
            since, before, larger, has_attachment, query,
        )

        if resolved.protocol == accounts_mod.POP3:
            # Answering a filtered query with an unfiltered maildrop inside a
            # successful envelope is a wrong answer, not a degraded one. Human
            # output could carry a caveat; `--json` has nowhere to put one that
            # a caller is obliged to read, so this refuses instead.
            if not criteria.is_empty():
                raise CliError(
                    f"account {resolved.name!r} uses POP3, which has no server-side "
                    "search, so these filters cannot be applied: "
                    f"{criteria.describe()}. Drop them to list the maildrop, or "
                    "re-add the account over IMAP if the provider offers it.",
                    code="filters_unsupported",
                )

            with _pop3(account, timeout) as pop:
                listing = pop.listing()
                total = len(listing)
                ordered = listing if oldest else list(reversed(listing))
                window = ordered[offset : offset + limit]
                entries = pop.summaries(window)
            header = (
                f"{resolved.name}  POP3 maildrop — {total} messages, "
                f"showing {len(entries)}"
            )
            emit(
                {
                    "account": resolved.name,
                    "protocol": "pop3",
                    "folder": "INBOX",
                    "total": total,
                    "returned": len(entries),
                    "filtered": False,
                    "messages": entries,
                },
                _listing_lines(entries, header),
                as_json=as_json,
            )
            return

        with _imap(account, timeout) as session:
            uids = session.search(folder, criteria)
            ordered = uids if oldest else list(reversed(uids))
            window = ordered[offset : offset + limit]
            entries = session.summaries(folder, window)
            counts = session.status(folder)

        header = (
            f"{resolved.name}  {folder} — {counts.get('messages', 0)} messages, "
            f"{counts.get('unseen', 0)} unseen; {len(uids)} matched, showing {len(entries)}"
        )
        emit(
            {
                "account": resolved.name,
                "protocol": "imap",
                "folder": folder,
                "counts": counts,
                "matched": len(uids),
                "returned": len(entries),
                "offset": offset,
                "criteria": criteria.describe(),
                "messages": entries,
            },
            _listing_lines(entries, header),
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@app.command()
def search(
    account: AccountOption = None,
    folder: FolderOption = "INBOX",
    unseen: Annotated[bool, typer.Option("--unseen")] = False,
    seen: Annotated[bool, typer.Option("--seen")] = False,
    flagged: Annotated[bool, typer.Option("--flagged")] = False,
    answered: Annotated[bool, typer.Option("--answered")] = False,
    sender: Annotated[str | None, typer.Option("--from")] = None,
    recipient: Annotated[str | None, typer.Option("--to")] = None,
    subject: Annotated[str | None, typer.Option("--subject")] = None,
    text: Annotated[str | None, typer.Option("--search")] = None,
    body: Annotated[str | None, typer.Option("--body")] = None,
    since: Annotated[str | None, typer.Option("--since")] = None,
    before: Annotated[str | None, typer.Option("--before")] = None,
    larger: Annotated[int | None, typer.Option("--larger")] = None,
    has_attachment: Annotated[bool, typer.Option("--has-attachment")] = False,
    query: Annotated[str | None, typer.Option("--query")] = None,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """Print matching UIDs, one per line, newest first.

    The composable half of `inbox`: pipe the output into `xargs` or a loop when
    the same operation has to hit every match.
    """
    try:
        criteria = _criteria(
            unseen, seen, flagged, answered, sender, recipient, subject, text, body,
            since, before, larger, has_attachment, query,
        )
        with _imap(account, timeout) as session:
            uids = list(reversed(session.search(folder, criteria)))
        emit(
            {"folder": folder, "criteria": criteria.describe(), "count": len(uids), "uids": uids},
            uids,
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


def _safe_target(directory: Path, filename: str, taken: set[str]) -> Path:
    """A writable path inside `directory` for an attacker-supplied filename.

    Two separate hazards, both of which a message can trigger deliberately:

    * **Escaping the directory.** Only the basename is used, so `../../.bashrc`
      becomes `.bashrc` inside the target. A name that leaves nothing usable
      after that — `..`, `/`, `.` — falls back to a generated one rather than
      resolving to the directory itself, which would raise on write.
    * **Collisions.** Two parts legitimately named `report.pdf` are common in
      real mail. Writing both to one path silently destroys the first while the
      command reports two files saved, so later names get a `-2`, `-3` suffix.
    """
    stem = Path(filename.replace("\\", "/")).name.strip()
    if not stem or stem in {".", ".."}:
        stem = "attachment"

    candidate = Path(stem)
    base, suffix = candidate.stem or "attachment", candidate.suffix
    name, counter = f"{base}{suffix}", 2
    while name.lower() in taken or (directory / name).exists():
        name = f"{base}-{counter}{suffix}"
        counter += 1
    taken.add(name.lower())
    return directory / name


def _save_attachments(msg: EmailMessage, directory: Path) -> list[str]:
    directory.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    taken: set[str] = set()
    for attachment in message_mod.attachments(msg):
        _, data = message_mod.attachment_bytes(msg, str(attachment.index))
        target = _safe_target(directory, attachment.filename, taken)
        target.write_bytes(data)
        written.append(str(target))
    return written


@app.command("read")
def read_email(
    uid: Annotated[str, typer.Argument(help="Message UID, as printed by inbox or search.")],
    account: AccountOption = None,
    folder: FolderOption = "INBOX",
    output: Annotated[
        str, typer.Option("--format", help="text, html, raw or headers.")
    ] = "text",
    max_chars: Annotated[
        int, typer.Option("--max-chars", help="Truncate the body. 0 means no limit.")
    ] = 20000,
    mark_seen: Annotated[
        bool, typer.Option("--mark-seen/--keep-unread", help="Mark the message read.")
    ] = False,
    save_attachments: Annotated[
        Path | None, typer.Option("--save-attachments", help="Write attachments to this directory.")
    ] = None,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """Read one message: headers, body, and what is attached.

    Reads without marking the message seen unless `--mark-seen` is passed, so
    looking at an inbox does not change what the human sees in their client.
    """
    try:
        if output not in ("text", "html", "raw", "headers"):
            raise CliError(
                f"unknown --format {output!r}: text, html, raw or headers", code="invalid_format"
            )

        resolved = _resolve(account)

        if resolved.protocol == accounts_mod.POP3:
            with _pop3(account, timeout) as pop:
                entry = pop.resolve(uid)
                raw = pop.retrieve(entry.number)
            msg = message_mod.parse(raw)
            meta: dict[str, Any] = {"flags": (), "size": entry.size}
            folder = "INBOX"
        else:
            with _imap(account, timeout) as session:
                if output == "raw":
                    raw = session.fetch_raw(folder, uid, mark_seen=mark_seen)
                    msg = message_mod.parse(raw)
                    meta = {}
                else:
                    msg, meta = session.fetch_message(folder, uid, mark_seen=mark_seen)
                    raw = b""

        if output == "raw":
            # `raw` has to survive the trip byte for byte, so neither branch may
            # decode it. A message with 8-bit octets in the body — legal under
            # Content-Transfer-Encoding: 8bit — would otherwise come back full
            # of U+FFFD and no longer be the message the server holds.
            if as_json:
                emit(
                    {
                        "uid": uid,
                        "folder": folder,
                        "encoding": "base64",
                        "size": len(raw),
                        "raw_base64": base64.b64encode(raw).decode("ascii"),
                    },
                    [],
                    as_json=True,
                )
            else:
                sys.stdout.buffer.write(raw)
                sys.stdout.buffer.flush()
            return

        written: list[str] = []
        if save_attachments is not None:
            written = _save_attachments(msg, save_attachments)

        data = message_mod.detail(
            msg,
            uid=uid,
            flags=meta.get("flags", ()),
            size=meta.get("size"),
            folder=folder,
            max_chars=None if max_chars <= 0 else max_chars,
        )
        data["saved_attachments"] = written

        head = [
            f"From:    {data['from']}",
            f"To:      {data['to']}",
            *([f"Cc:      {data['cc']}"] if data["cc"] else []),
            f"Date:    {data['date'] or '(none)'}",
            f"Subject: {data['subject'] or '(no subject)'}",
            f"UID:     {uid}   folder: {folder}   flags: {' '.join(data['flags']) or '-'}",
        ]
        if data["attachments"]:
            head.append(
                "Attach:  "
                + ", ".join(
                    f"[{a['index']}] {a['filename']} ({a['content_type']}, {a['size']} B)"
                    for a in data["attachments"]
                )
            )
        if written:
            head.append("Saved:   " + ", ".join(written))

        if output == "headers":
            body_lines: list[str] = []
        elif output == "html":
            html = message_mod.body_html(msg)
            body_lines = ["", html or "(no HTML part)"]
        else:
            body_lines = [
                "",
                f"--- body ({data['body_source']}) ---",
                data["body"] or "(empty)",
                *(["", "[truncated: raise --max-chars for the rest]"] if data["body_truncated"] else []),
            ]

        emit(data, head + body_lines, as_json=as_json)
    except CliError as error:
        fail(error, as_json=as_json)


@app.command()
def attachments(
    uid: Annotated[str, typer.Argument(help="Message UID.")],
    account: AccountOption = None,
    folder: FolderOption = "INBOX",
    save: Annotated[
        Path | None, typer.Option("--save", help="Directory to write every attachment to.")
    ] = None,
    only: Annotated[
        str | None, typer.Option("--only", help="Save just this index or filename.")
    ] = None,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """List a message's attachments, and optionally write them to disk."""
    try:
        resolved = _resolve(account)
        if resolved.protocol == accounts_mod.POP3:
            with _pop3(account, timeout) as pop:
                raw = pop.retrieve(pop.resolve(uid).number)
            msg = message_mod.parse(raw)
        else:
            with _imap(account, timeout) as session:
                msg, _ = session.fetch_message(folder, uid, mark_seen=False)

        listed = [a.to_dict() for a in message_mod.attachments(msg)]
        written: list[str] = []

        if save is not None:
            if only is not None:
                try:
                    filename, data = message_mod.attachment_bytes(msg, only)
                except KeyError:
                    known = ", ".join(f"{a['index']}:{a['filename']}" for a in listed) or "none"
                    raise CliError(
                        f"no attachment {only!r} on message {uid}. Available: {known}",
                        code="attachment_not_found",
                    ) from None
                save.mkdir(parents=True, exist_ok=True)
                target = _safe_target(save, filename, set())
                target.write_bytes(data)
                written = [str(target)]
            else:
                written = _save_attachments(msg, save)

        emit(
            {"uid": uid, "folder": folder, "attachments": listed, "saved": written},
            [
                f"{a['index']}  {a['filename']}  {a['content_type']}  {a['size']} B"
                for a in listed
            ]
            or ["(no attachments)"],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------


@app.command("send")
def send_email(
    to: Annotated[
        list[str] | None,
        typer.Option("--to", help="Recipient. Repeatable, and accepts comma-separated lists."),
    ] = None,
    cc: Annotated[list[str] | None, typer.Option("--cc", help="Carbon copy.")] = None,
    bcc: Annotated[list[str] | None, typer.Option("--bcc", help="Blind carbon copy.")] = None,
    subject: Annotated[str, typer.Option("--subject", help="Subject line.")] = "",
    body: Annotated[str | None, typer.Option("--body", help="Plain text body.")] = None,
    body_file: Annotated[
        Path | None, typer.Option("--body-file", help="Read the body from a file.")
    ] = None,
    body_stdin: Annotated[
        bool, typer.Option("--body-stdin", help="Read the body from stdin.")
    ] = False,
    html_file: Annotated[
        Path | None, typer.Option("--html-file", help="Add an HTML alternative from a file.")
    ] = None,
    attach: Annotated[
        list[Path] | None, typer.Option("--attach", help="File to attach. Repeatable.")
    ] = None,
    reply_to: Annotated[str | None, typer.Option("--reply-to")] = None,
    in_reply_to: Annotated[
        str | None,
        typer.Option("--in-reply-to", help="Message-ID being replied to. Sets threading headers."),
    ] = None,
    references: Annotated[str | None, typer.Option("--references")] = None,
    header: Annotated[
        list[str] | None, typer.Option("--header", help="Extra header as 'Name: value'.")
    ] = None,
    account: AccountOption = None,
    save_to_sent: Annotated[
        bool,
        typer.Option("--save-to-sent/--no-save-to-sent", help="File a copy in the Sent mailbox."),
    ] = True,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Compose and print the message; send nothing."),
    ] = False,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """Send a message.

    `--dry-run` composes and prints the exact bytes that would be transmitted
    without opening a socket. Use it to show a human the draft before anything
    leaves the machine — mail cannot be unsent.
    """
    try:
        resolved = _resolve(account)

        extra: list[tuple[str, str]] = []
        for entry in header or []:
            name, sep, value = entry.partition(":")
            if not sep or not name.strip():
                raise CliError(
                    f"--header {entry!r} is not in 'Name: value' form", code="invalid_header"
                )
            extra.append((name.strip(), value.strip()))

        if html_file is not None and not html_file.is_file():
            raise CliError(f"no such file: {html_file}", code="body_not_found")

        draft = smtp_mod.Draft(
            to=smtp_mod.split_addresses(to or [], "--to"),
            cc=smtp_mod.split_addresses(cc or [], "--cc"),
            bcc=smtp_mod.split_addresses(bcc or [], "--bcc"),
            subject=subject,
            body=_read_body(body, body_file, body_stdin),
            html=html_file.read_text(encoding="utf-8") if html_file else None,
            reply_to=reply_to,
            in_reply_to=in_reply_to,
            references=references,
            attachments=[smtp_mod.Attachment.load(path) for path in (attach or [])],
            headers=extra,
        )

        msg = smtp_mod.compose(resolved, draft)
        recipients = draft.recipients()
        # The transmitted payload, not `as_string()`: Bcc removed and CRLF line
        # endings, exactly as smtplib will flatten it.
        transmitted = smtp_mod.serialize(msg)
        smtputf8 = smtp_mod.needs_smtputf8(resolved.address, recipients)

        summary = {
            "account": resolved.name,
            "from": resolved.from_header,
            "to": draft.to,
            "cc": draft.cc,
            "bcc": draft.bcc,
            "subject": subject,
            "recipients": recipients,
            "attachments": [a.to_dict() for a in draft.attachments],
            "size": len(transmitted),
        }

        if dry_run:
            preview = transmitted.decode("utf-8", "replace")
            caveat = (
                "An address here is non-ASCII. If the server advertises SMTPUTF8 it "
                "will reflatten with a utf8 policy, so the transmitted bytes may "
                "differ from this preview."
            )
            emit(
                {
                    **summary,
                    "dry_run": True,
                    "smtputf8": smtputf8,
                    "exact": not smtputf8,
                    "message": preview,
                },
                [
                    "DRY RUN — nothing was sent.",
                    *([f"note: {caveat}", ""] if smtputf8 else [""]),
                    preview,
                ],
                as_json=as_json,
            )
            return

        result = smtp_mod.send(
            resolved,
            secrets.require_password(resolved.name, resolved.username),
            msg,
            recipients,
            timeout=timeout,
        )

        filed: str | None = None
        file_error: str | None = None
        if save_to_sent and resolved.protocol == accounts_mod.IMAP:
            try:
                with _imap(account, timeout) as session:
                    target = session.sent_folder()
                    if target is None:
                        file_error = (
                            "no Sent mailbox found; set one with "
                            "`account add --sent-folder`"
                        )
                    else:
                        session.append(target, msg.as_bytes())
                        filed = target
            except CliError as error:
                # The mail is already gone. Filing the copy is bookkeeping, and
                # failing the command here would wrongly suggest it was not sent.
                file_error = error.message

        emit(
            {**summary, **result, "saved_to": filed, "save_error": file_error},
            [
                f"sent to {', '.join(recipients)}",
                f"  message-id  {result['message_id']}",
                *([f"  refused     {result['refused']}"] if result["refused"] else []),
                *([f"  filed in    {filed}"] if filed else []),
                *([f"  not filed   {file_error}"] if file_error else []),
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


# --------------------------------------------------------------------------
# Mutating a mailbox
# --------------------------------------------------------------------------


@app.command()
def flag(
    uids: Annotated[list[str], typer.Argument(help="One or more message UIDs.")],
    account: AccountOption = None,
    folder: FolderOption = "INBOX",
    read: Annotated[bool, typer.Option("--read", help="Mark as seen.")] = False,
    unread: Annotated[bool, typer.Option("--unread", help="Mark as unseen.")] = False,
    star: Annotated[bool, typer.Option("--star", help="Add the \\Flagged flag.")] = False,
    unstar: Annotated[bool, typer.Option("--unstar", help="Remove the \\Flagged flag.")] = False,
    add: Annotated[
        list[str] | None, typer.Option("--add", help="Arbitrary flag to add, e.g. \\Answered.")
    ] = None,
    remove: Annotated[list[str] | None, typer.Option("--remove", help="Flag to remove.")] = None,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """Change message flags: read, unread, starred, or anything the server allows."""
    try:
        to_add = list(add or []) + (["\\Seen"] if read else []) + (["\\Flagged"] if star else [])
        to_remove = (
            list(remove or [])
            + (["\\Seen"] if unread else [])
            + (["\\Flagged"] if unstar else [])
        )
        if not to_add and not to_remove:
            raise CliError(
                "nothing to do: pass --read, --unread, --star, --unstar, --add or --remove",
                code="no_flags",
            )
        if overlap := sorted(set(to_add) & set(to_remove)):
            raise CliError(
                f"cannot add and remove the same flag: {', '.join(overlap)}",
                code="conflicting_flags",
            )

        with _imap(account, timeout) as session:
            if to_add:
                session.store(folder, uids, "+FLAGS", to_add)
            if to_remove:
                session.store(folder, uids, "-FLAGS", to_remove)

        emit(
            {"folder": folder, "uids": uids, "added": to_add, "removed": to_remove},
            [
                f"updated {len(uids)} message(s) in {folder}",
                *([f"  added    {' '.join(to_add)}"] if to_add else []),
                *([f"  removed  {' '.join(to_remove)}"] if to_remove else []),
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@app.command()
def move(
    uids: Annotated[list[str], typer.Argument(help="One or more message UIDs.")],
    destination: Annotated[str, typer.Option("--to", help="Destination mailbox.")],
    account: AccountOption = None,
    folder: FolderOption = "INBOX",
    create: Annotated[
        bool, typer.Option("--create", help="Create the destination if it does not exist.")
    ] = False,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """Move messages to another mailbox.

    On a server without RFC 6851 MOVE this is COPY plus a deletion of the
    source, and that deletion is only performed when it can be scoped to these
    UIDs. When it cannot, the copies arrive and the originals are left flagged
    rather than risking other messages — reported, not silently.
    """
    try:
        with _imap(account, timeout) as session:
            if create and destination not in {f.name for f in session.folders()}:
                session.create(destination)
            method = session.move(folder, uids, destination)

        incomplete = method == "copy+flag"
        emit(
            {
                "folder": folder,
                "destination": destination,
                "uids": uids,
                "method": method,
                "sources_removed": not incomplete,
            },
            [
                f"copied {len(uids)} message(s) from {folder} to {destination}"
                if incomplete
                else f"moved {len(uids)} message(s) from {folder} to {destination} ({method})",
                *(
                    [
                        "",
                        f"warning: the originals are still in {folder}, flagged deleted.",
                        "  This server supports neither MOVE nor UIDPLUS, so it offers "
                        "no way to remove them without a mailbox-wide EXPUNGE that "
                        "would also erase anything else flagged deleted there.",
                    ]
                    if incomplete
                    else []
                ),
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@app.command()
def delete(
    uids: Annotated[list[str], typer.Argument(help="One or more message UIDs.")],
    account: AccountOption = None,
    folder: FolderOption = "INBOX",
    purge: Annotated[
        bool,
        typer.Option("--purge", help="Erase permanently instead of moving to Trash."),
    ] = False,
    yes: YesOption = False,
    timeout: TimeoutOption = 30.0,
    as_json: JsonOption = False,
) -> None:
    """Delete messages.

    Moves them to Trash by default, which is recoverable. `--purge` expunges
    them for good and therefore requires `--yes`.
    """
    try:
        resolved = _resolve(account)

        if resolved.protocol == accounts_mod.POP3:
            if not yes:
                raise CliError(
                    "POP3 deletion is permanent and has no Trash. Re-run with --yes.",
                    code="confirmation_required",
                )
            with _pop3(account, timeout, commit_deletes=True) as pop:
                numbers = [pop.resolve(uid).number for uid in uids]
                pop.delete(numbers)
            emit(
                {"protocol": "pop3", "uids": uids, "purged": True},
                [f"deleted {len(uids)} message(s) from the maildrop"],
                as_json=as_json,
            )
            return

        if purge and not yes:
            raise CliError(
                "--purge erases messages permanently. Re-run with --yes, or drop "
                "--purge to move them to Trash instead.",
                code="confirmation_required",
            )

        with _imap(account, timeout) as session:
            if purge:
                if "UIDPLUS" not in session.capabilities:
                    # Checked before flagging anything, so a refusal leaves the
                    # mailbox exactly as it was.
                    raise CliError(
                        "this server does not advertise UIDPLUS, so it offers no "
                        "way to expunge specific messages — only a mailbox-wide "
                        "EXPUNGE, which would also permanently erase anything "
                        f"else in {folder!r} that is flagged deleted, including "
                        "messages flagged by another client. Nothing was "
                        "changed. Drop --purge to move them to Trash instead.",
                        code="unscoped_expunge",
                    )
                session.store(folder, uids, "+FLAGS", ["\\Deleted"])
                session.purge(folder, uids)
                target = None
                method = "expunged"
            else:
                target = session.trash_folder()
                if target is None:
                    raise CliError(
                        "no Trash mailbox found. Set one with `account add --trash-folder`, "
                        "or pass --purge --yes to erase permanently.",
                        code="no_trash_folder",
                    )
                if target == folder:
                    raise CliError(
                        f"{folder!r} is already the Trash mailbox; pass --purge --yes to "
                        "erase permanently.",
                        code="already_trash",
                    )
                method = session.move(folder, uids, target)

        emit(
            {
                "folder": folder,
                "uids": uids,
                "purged": purge,
                "moved_to": target,
                "method": method,
            },
            [
                f"purged {len(uids)} message(s) from {folder}"
                if purge
                else f"moved {len(uids)} message(s) from {folder} to {target}"
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)
