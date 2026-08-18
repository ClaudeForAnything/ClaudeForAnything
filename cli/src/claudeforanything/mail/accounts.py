# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where accounts live, and what an account is.

Two stores, deliberately split:

* everything non-secret — addresses, hosts, ports, TLS mode — in a JSON file
  under the user's config directory, readable and diffable;
* the password, and only the password, in the OS credential store via keyring
  (see `secrets.py`).

Nothing in this module ever holds a password, which is what makes it safe to
dump an account to stdout.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from ..output import CliError
from .presets import PLAIN, SECURITY_CHOICES, SSL, STARTTLS

#: Bumped only if the on-disk shape changes incompatibly.
STORE_VERSION = 1

HOME_ENV_VAR = "EMAILS_FOR_CLAUDE_HOME"

IMAP = "imap"
POP3 = "pop3"
INCOMING_PROTOCOLS = (IMAP, POP3)

DEFAULT_PORTS = {
    (IMAP, SSL): 993,
    (IMAP, STARTTLS): 143,
    (IMAP, PLAIN): 143,
    (POP3, SSL): 995,
    (POP3, STARTTLS): 110,
    (POP3, PLAIN): 110,
    ("smtp", SSL): 465,
    ("smtp", STARTTLS): 587,
    ("smtp", PLAIN): 25,
}


def config_home() -> Path:
    """The directory holding accounts.json.

    $EMAILS_FOR_CLAUDE_HOME wins, so tests and throwaway profiles never touch
    the real one. Otherwise %APPDATA% on Windows and $XDG_CONFIG_HOME (or
    ~/.config) elsewhere.
    """
    override = os.environ.get(HOME_ENV_VAR)
    if override:
        return Path(override).expanduser()

    if os.name == "nt":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    else:
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"

    return root / "claudeforanything" / "emails-for-claude"


def accounts_path() -> Path:
    return config_home() / "accounts.json"


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One server to talk to."""

    host: str
    port: int
    security: str

    def describe(self) -> str:
        return f"{self.host}:{self.port} ({self.security})"


@dataclass(frozen=True, slots=True)
class Account:
    """One mailbox, with no secret in it."""

    name: str
    address: str
    username: str
    protocol: str
    incoming: Endpoint
    outgoing: Endpoint
    display_name: str | None = None
    sent_folder: str | None = None
    trash_folder: str | None = None
    insecure_tls: bool = False
    preset: str | None = None

    @property
    def from_header(self) -> str:
        """The From: value, `Name <addr>` when a display name is configured."""
        from email.utils import formataddr

        if self.display_name:
            return formataddr((self.display_name, self.address))
        return self.address

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _endpoint_from_dict(raw: object, *, where: str) -> Endpoint:
    if not isinstance(raw, dict):
        raise CliError(f"malformed account store: {where} is not an object", code="bad_store")
    try:
        return Endpoint(
            host=str(raw["host"]),
            port=int(raw["port"]),
            security=str(raw["security"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CliError(
            f"malformed account store: {where} is missing host/port/security ({error})",
            code="bad_store",
        ) from error


def _optional_str(raw: dict[str, object], key: str) -> str | None:
    value = raw.get(key)
    return str(value) if value else None


def _account_from_dict(name: str, raw: dict[str, object]) -> Account:
    return Account(
        name=name,
        address=str(raw.get("address", "")),
        username=str(raw.get("username", "")),
        protocol=str(raw.get("protocol", IMAP)),
        incoming=_endpoint_from_dict(raw.get("incoming"), where=f"{name}.incoming"),
        outgoing=_endpoint_from_dict(raw.get("outgoing"), where=f"{name}.outgoing"),
        display_name=_optional_str(raw, "display_name"),
        sent_folder=_optional_str(raw, "sent_folder"),
        trash_folder=_optional_str(raw, "trash_folder"),
        insecure_tls=bool(raw.get("insecure_tls", False)),
        preset=_optional_str(raw, "preset"),
    )


@dataclass(slots=True)
class Store:
    """The whole accounts.json, in memory."""

    accounts: dict[str, Account]
    default: str | None = None
    path: Path | None = None

    def get(self, name: str | None) -> Account:
        """Resolve an account by name, falling back to the configured default."""
        if name is None:
            if self.default and self.default in self.accounts:
                return self.accounts[self.default]
            if len(self.accounts) == 1:
                return next(iter(self.accounts.values()))
            if not self.accounts:
                raise CliError(
                    "no accounts configured. Add one with: claudeforanything "
                    "emails-for-claude account add <name> --address <you@example.com>",
                    code="no_accounts",
                )
            raise CliError(
                "several accounts configured and no default set. Pass --account, "
                f"or run `account set-default <name>`. Known: {', '.join(sorted(self.accounts))}",
                code="ambiguous_account",
            )
        try:
            return self.accounts[name]
        except KeyError:
            known = ", ".join(sorted(self.accounts)) or "none"
            raise CliError(
                f"no such account: {name!r}. Known: {known}", code="account_not_found"
            ) from None

    def put(self, account: Account) -> None:
        self.accounts[account.name] = account

    def remove(self, name: str) -> Account:
        account = self.get(name)
        del self.accounts[name]
        if self.default == name:
            self.default = next(iter(sorted(self.accounts)), None)
        return account


def load(path: Path | None = None) -> Store:
    """Read the account store. A missing file is an empty store, not an error."""
    target = path or accounts_path()
    if not target.is_file():
        return Store(accounts={}, default=None, path=target)

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CliError(f"cannot read {target}: {error}", code="bad_store") from error

    if not isinstance(raw, dict):
        raise CliError(f"malformed account store: {target} is not an object", code="bad_store")

    version = raw.get("version", STORE_VERSION)
    if version != STORE_VERSION:
        raise CliError(
            f"{target} is version {version}, this CLI understands version {STORE_VERSION}",
            code="store_version",
        )

    entries = raw.get("accounts") or {}
    if not isinstance(entries, dict):
        raise CliError(f"malformed account store: {target}.accounts", code="bad_store")

    accounts = {
        name: _account_from_dict(name, entry)
        for name, entry in entries.items()
        if isinstance(entry, dict)
    }
    default = raw.get("default")
    return Store(
        accounts=accounts,
        default=str(default) if default in accounts else None,
        path=target,
    )


def save(store: Store, path: Path | None = None) -> Path:
    """Write the store back, owner-readable only."""
    target = path or store.path or accounts_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "version": STORE_VERSION,
        "default": store.default,
        "accounts": {
            name: {k: v for k, v in account.to_dict().items() if k != "name"}
            for name, account in sorted(store.accounts.items())
        },
    }
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    # No secret is in here, but the file still maps a person's mail servers.
    # Best-effort: some filesystems (and Windows) will not honour this.
    try:
        target.chmod(0o600)
    except OSError:
        pass
    return target


def default_port(kind: str, security: str) -> int:
    """The standard port for a protocol/TLS-mode pair."""
    try:
        return DEFAULT_PORTS[(kind, security)]
    except KeyError:
        raise CliError(
            f"no default port for {kind} over {security!r}; pass the port explicitly",
            code="invalid_security",
        ) from None


def validate_security(security: str) -> str:
    if security not in SECURITY_CHOICES:
        raise CliError(
            f"invalid security {security!r}: pick one of {', '.join(SECURITY_CHOICES)}",
            code="invalid_security",
        )
    return security


def validate_protocol(protocol: str) -> str:
    if protocol not in INCOMING_PROTOCOLS:
        raise CliError(
            f"invalid protocol {protocol!r}: pick one of {', '.join(INCOMING_PROTOCOLS)}",
            code="invalid_protocol",
        )
    return protocol


def with_endpoint(account: Account, *, incoming: Endpoint | None = None,
                  outgoing: Endpoint | None = None) -> Account:
    """Return a copy of the account with endpoints replaced."""
    changes: dict[str, object] = {}
    if incoming is not None:
        changes["incoming"] = incoming
    if outgoing is not None:
        changes["outgoing"] = outgoing
    return replace(account, **changes)  # type: ignore[arg-type]
