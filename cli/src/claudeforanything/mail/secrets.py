# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""The only place a mail password is handled.

Passwords go to the OS credential store through keyring — Credential Manager on
Windows, Keychain on macOS, Secret Service or KWallet on Linux. They are never
written to accounts.json, never echoed, and never included in `--json` output.

An environment fallback exists for headless boxes where no keyring backend is
installed, because the alternative is people pasting passwords into shell
history. It is a fallback: keyring is consulted first, and `describe_source`
reports which one answered so a surprising result is visible.

keyring is imported lazily inside each function. It pulls in platform bindings
and costs real milliseconds, and `claudeforanything --help` should not pay for a
password store it is not going to open.
"""

from __future__ import annotations

import os
import re

from ..output import CliError

#: keyring service prefix. One service per account, so removing an account is a
#: single delete and two accounts on the same provider never collide.
SERVICE_PREFIX = "emails-for-claude"

ENV_PREFIX = "EMAILS_FOR_CLAUDE_PASSWORD"

KEYRING = "keyring"
ENVIRONMENT = "environment"
MISSING = "missing"


def service_name(account: str) -> str:
    """The keyring service string for an account."""
    return f"{SERVICE_PREFIX}:{account}"


def env_var_name(account: str) -> str:
    """The environment variable consulted when keyring has nothing.

    `work` becomes EMAILS_FOR_CLAUDE_PASSWORD_WORK; anything not alphanumeric
    becomes an underscore.
    """
    slug = re.sub(r"[^A-Za-z0-9]+", "_", account).strip("_").upper()
    return f"{ENV_PREFIX}_{slug}" if slug else ENV_PREFIX


def _keyring():
    """Import keyring, turning a missing install into an actionable error."""
    try:
        import keyring
    except ImportError as error:  # pragma: no cover - dependency is declared
        raise CliError(
            "keyring is not installed. Reinstall the CLI: uv tool install ./cli",
            code="keyring_missing",
        ) from error
    return keyring


def _no_backend_error(action: str, account: str) -> CliError:
    return CliError(
        f"cannot {action} the password for {account!r}: no keyring backend is "
        "available on this machine. Install one (SecretStorage or KWallet on "
        f"Linux), or set ${env_var_name(account)} instead.",
        code="no_keyring_backend",
    )


def get_password(account: str, username: str) -> str | None:
    """Return the stored password, or None. Never raises for a missing entry."""
    keyring = _keyring()
    from keyring.errors import KeyringError, NoKeyringError

    try:
        stored = keyring.get_password(service_name(account), username)
    except NoKeyringError:
        stored = None
    except KeyringError as error:
        raise CliError(
            f"keyring refused to read the password for {account!r}: {error}",
            code="keyring_error",
        ) from error

    if stored:
        return stored
    return os.environ.get(env_var_name(account)) or None


def describe_source(account: str, username: str) -> str:
    """Where the password for this account would come from: keyring, env, or nowhere.

    Used by `account show` and `parameters` so the answer is auditable without
    ever printing the value.
    """
    keyring = _keyring()
    from keyring.errors import KeyringError, NoKeyringError

    try:
        if keyring.get_password(service_name(account), username):
            return KEYRING
    except (KeyringError, NoKeyringError):
        pass
    if os.environ.get(env_var_name(account)):
        return ENVIRONMENT
    return MISSING


def set_password(account: str, username: str, password: str) -> None:
    """Store a password. The caller is responsible for never logging it."""
    if not password:
        raise CliError("refusing to store an empty password", code="empty_password")

    keyring = _keyring()
    from keyring.errors import KeyringError, NoKeyringError, PasswordSetError

    try:
        keyring.set_password(service_name(account), username, password)
    except NoKeyringError as error:
        raise _no_backend_error("store", account) from error
    except (PasswordSetError, KeyringError) as error:
        raise CliError(
            f"keyring refused to store the password for {account!r}: {error}",
            code="keyring_error",
        ) from error


def delete_password(account: str, username: str) -> bool:
    """Forget a password. Returns False when there was nothing to forget."""
    keyring = _keyring()
    from keyring.errors import KeyringError, NoKeyringError, PasswordDeleteError

    try:
        keyring.delete_password(service_name(account), username)
    except (PasswordDeleteError, NoKeyringError):
        return False
    except KeyringError as error:
        raise CliError(
            f"keyring refused to delete the password for {account!r}: {error}",
            code="keyring_error",
        ) from error
    return True


def require_password(account: str, username: str) -> str:
    """Return the password, or explain precisely how to supply one."""
    password = get_password(account, username)
    if password:
        return password
    raise CliError(
        f"no password stored for account {account!r}. Store one with:\n"
        f"  claudeforanything emails-for-claude account set-password {account}\n"
        f"or export ${env_var_name(account)}.",
        code="no_password",
    )


def backend_name() -> str:
    """A human label for the active keyring backend, for diagnostics."""
    keyring = _keyring()
    from keyring.errors import KeyringError

    try:
        return str(keyring.get_keyring())
    except KeyringError as error:  # pragma: no cover - depends on the machine
        return f"unavailable ({error})"
