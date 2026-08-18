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
