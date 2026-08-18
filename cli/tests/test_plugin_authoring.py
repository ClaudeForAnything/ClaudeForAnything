from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from claudeforanything.main import app

from .conftest import payload

NS = "claude-for-plugin-authoring"


def run(runner: CliRunner, root: Path, *args: str):
    return runner.invoke(app, [NS, *args, "--root", str(root)])


def test_new_plugin_writes_the_expected_tree(runner: CliRunner, marketplace: Path) -> None:
    result = run(runner, marketplace, "new-plugin", "crm-for-claude", "--description", "A CRM.")
    assert result.exit_code == 0, result.output

    plugin = marketplace / "marketplace" / "plugins" / "crm-for-claude"
    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text("utf-8"))
    assert manifest["name"] == "crm-for-claude"
    assert manifest["description"] == "A CRM."
    assert (plugin / "README.md").is_file()
    assert (plugin / "skills" / "example" / "SKILL.md").is_file()


def test_new_plugin_reports_the_catalog_entry_to_add(runner: CliRunner, marketplace: Path) -> None:
    result = run(
        runner, marketplace, "new-plugin", "crm-for-claude", "--description", "x", "--json"
    )
    entry = payload(result.stdout)["data"]["catalog"]["entry"]
    assert entry == {
        "name": "crm-for-claude",
        "source": "./marketplace/plugins/crm-for-claude",
    }


def test_new_plugin_rejects_a_name_breaking_the_convention(
    runner: CliRunner, marketplace: Path
) -> None:
    result = run(runner, marketplace, "new-plugin", "photo-editing", "--description", "x", "--json")
    assert result.exit_code == 1
    body = payload(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_name"
    assert not (marketplace / "marketplace" / "plugins" / "photo-editing").exists()


def test_new_plugin_refuses_to_overwrite_without_force(
    runner: CliRunner, marketplace: Path
) -> None:
    run(runner, marketplace, "new-plugin", "crm-for-claude", "--description", "first")
    result = run(
        runner, marketplace, "new-plugin", "crm-for-claude", "--description", "second", "--json"
    )
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "exists"

    manifest = json.loads(
        (
            marketplace / "marketplace" / "plugins" / "crm-for-claude" / ".claude-plugin"
            / "plugin.json"
        ).read_text("utf-8")
    )
    assert manifest["description"] == "first", "the original must survive"


def test_new_plugin_rejects_unknown_component(runner: CliRunner, marketplace: Path) -> None:
    result = run(
        runner, marketplace, "new-plugin", "crm-for-claude",
        "--description", "x", "--with", "nonsense", "--json",
    )
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "invalid_component"


def test_new_skill_standalone_lands_under_marketplace_skills(
    runner: CliRunner, marketplace: Path
) -> None:
    result = run(runner, marketplace, "new-skill", "summarize-a-repo", "--description", "x")
    assert result.exit_code == 0, result.output
    assert (marketplace / "marketplace" / "skills" / "summarize-a-repo" / "SKILL.md").is_file()


def test_new_skill_in_a_plugin(runner: CliRunner, marketplace: Path) -> None:
    run(runner, marketplace, "new-plugin", "crm-for-claude", "--description", "x")
    result = run(
        runner, marketplace, "new-skill", "add-contact", "--plugin", "crm-for-claude",
        "--description", "x",
    )
    assert result.exit_code == 0, result.output
    skill = (
        marketplace / "marketplace" / "plugins" / "crm-for-claude" / "skills" / "add-contact"
        / "SKILL.md"
    )
    assert skill.is_file()
    assert "name: add-contact" in skill.read_text("utf-8")


def test_new_skill_rejects_an_unknown_plugin(runner: CliRunner, marketplace: Path) -> None:
    result = run(
        runner, marketplace, "new-skill", "x", "--plugin", "nope", "--description", "y", "--json"
    )
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "plugin_not_found"


def test_check_passes_on_an_empty_marketplace(runner: CliRunner, marketplace: Path) -> None:
    result = run(runner, marketplace, "check", "--json")
    assert result.exit_code == 0
    assert payload(result.stdout)["data"]["passed"] is True


def test_check_flags_a_plugin_missing_from_the_catalog(
    runner: CliRunner, marketplace: Path
) -> None:
    run(runner, marketplace, "new-plugin", "crm-for-claude", "--description", "x")
    result = run(runner, marketplace, "check", "--json")

    assert result.exit_code == 1
    data = payload(result.stdout)["data"]
    assert data["passed"] is False
    assert [f["kind"] for f in data["failures"]] == ["catalog"]


def test_check_flags_frontmatter_name_not_matching_its_directory(
    runner: CliRunner, marketplace: Path
) -> None:
    skill = marketplace / "marketplace" / "skills" / "renamed"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: original\ndescription: x\n---\n", encoding="utf-8"
    )

    result = run(runner, marketplace, "check", "--json")
    assert result.exit_code == 1
    failures = payload(result.stdout)["data"]["failures"]
    assert any("does not match directory" in f["message"] for f in failures)


def test_check_does_not_walk_outside_the_marketplace_directory(
    runner: CliRunner, marketplace: Path
) -> None:
    """The glob must stay scoped: at the repo root it would walk vendor_docs/."""
    stray = marketplace / "vendor_docs" / "some-plugin"
    stray.mkdir(parents=True)
    (stray / "SKILL.md").write_text("---\nname: wrong\ndescription: x\n---\n", encoding="utf-8")

    result = run(runner, marketplace, "check", "--json")
    assert result.exit_code == 0, result.stdout
    assert payload(result.stdout)["data"]["passed"] is True
