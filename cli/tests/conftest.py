# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner


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
