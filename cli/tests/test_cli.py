from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from claudeforanything import __version__
from claudeforanything.main import app

from .conftest import payload


def test_bare_invocation_shows_help(runner: CliRunner) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0  # no_args_is_help exits with the usage code
    assert "claude-for-plugin-authoring" in result.output


def test_version(runner: CliRunner) -> None:
    result = runner.invoke(app, ["version", "--json"])
    assert result.exit_code == 0
    assert payload(result.stdout)["data"]["version"] == __version__


def test_list_reports_every_registered_namespace(runner: CliRunner) -> None:
    from claudeforanything.namespaces import NAMESPACES

    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0
    names = [n["name"] for n in payload(result.stdout)["data"]["namespaces"]]
    assert names == list(NAMESPACES)


def test_every_namespace_name_matches_the_plugin_naming_convention() -> None:
    """A namespace is a plugin's CLI surface, so it inherits the plugin rules."""
    from claudeforanything.naming import check_plugin_name
    from claudeforanything.namespaces import NAMESPACES

    for name in NAMESPACES:
        assert check_plugin_name(name) == [], name


def test_json_output_is_a_single_parseable_document(runner: CliRunner) -> None:
    result = runner.invoke(app, ["list", "--json"])
    json.loads(result.stdout)  # raises if anything else was written to stdout


def test_root_is_discovered_from_the_working_directory(
    runner: CliRunner, marketplace: Path, monkeypatch
) -> None:
    nested = marketplace / "marketplace" / "plugins"
    monkeypatch.chdir(nested)
    result = runner.invoke(app, ["claude-for-plugin-authoring", "check", "--json"])
    assert result.exit_code == 0, result.stdout
    assert Path(payload(result.stdout)["data"]["root"]) == marketplace.resolve()


def test_root_env_var_overrides_discovery(
    runner: CliRunner, marketplace: Path, tmp_path: Path, monkeypatch
) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("CLAUDEFORANYTHING_ROOT", str(marketplace))

    result = runner.invoke(app, ["claude-for-plugin-authoring", "check", "--json"])
    assert result.exit_code == 0, result.stdout
    assert Path(payload(result.stdout)["data"]["root"]) == marketplace.resolve()


def test_outside_a_marketplace_reports_a_json_error(
    runner: CliRunner, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CLAUDEFORANYTHING_ROOT", raising=False)

    result = runner.invoke(app, ["claude-for-plugin-authoring", "check", "--json"])
    assert result.exit_code == 1
    body = payload(result.stdout)
    assert body["ok"] is False
    assert body["error"]["code"] == "root_not_found"


def test_error_envelope_matches_the_success_envelope_shape(
    runner: CliRunner, marketplace: Path
) -> None:
    """A caller must be able to branch on `.ok` without knowing the command."""
    ok = payload(runner.invoke(app, ["version", "--json"]).stdout)
    err = payload(
        runner.invoke(
            app,
            [
                "claude-for-plugin-authoring", "new-plugin", "bad-name",
                "--description", "x", "--root", str(marketplace), "--json",
            ],
        ).stdout
    )
    assert ok["ok"] is True and "data" in ok
    assert err["ok"] is False and "error" in err
    assert set(err["error"]) == {"code", "message"}


def test_human_errors_go_to_stderr_not_stdout(runner: CliRunner, marketplace: Path) -> None:
    """Without --json, stdout stays clean so it is still safe to pipe."""
    result = runner.invoke(
        app,
        [
            "claude-for-plugin-authoring", "new-plugin", "bad-name",
            "--description", "x", "--root", str(marketplace),
        ],
    )
    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "error:" in result.stderr


def test_unknown_root_is_reported(runner: CliRunner, tmp_path: Path) -> None:
    missing = tmp_path / "not-a-marketplace"
    missing.mkdir()
    result = runner.invoke(
        app, ["claude-for-plugin-authoring", "check", "--root", str(missing), "--json"]
    )
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "root_not_found"


def test_module_entry_point_is_importable() -> None:
    """`python -m claudeforanything` must keep working alongside the script."""
    assert os.path.isfile(
        Path(__file__).parent.parent / "src" / "claudeforanything" / "__main__.py"
    )
