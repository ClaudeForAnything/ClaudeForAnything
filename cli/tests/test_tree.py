# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from claudeforanything import tree as tree_mod
from claudeforanything.main import app

from .conftest import payload


@pytest.fixture
def sample(tmp_path: Path) -> Path:
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "a.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "deep" / "b.py").write_text("", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    (tmp_path / ".hidden").write_text("", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("", encoding="utf-8")
    return tmp_path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A real repository, so gitignore behaviour is exercised rather than mocked."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(
        "/vendor/\n/vendor_docs/\nNOTES.md\n/build/\n", encoding="utf-8"
    )
    for name in ("vendor", "vendor_docs", "build", "keep"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "f.txt").write_text("", encoding="utf-8")
    (tmp_path / "NOTES.md").write_text("", encoding="utf-8")
    (tmp_path / "README.md").write_text("", encoding="utf-8")
    return tmp_path


def names(node: dict) -> list[str]:
    return [c["name"] for c in node["children"]]


def test_depth_limits_descent(sample: Path) -> None:
    one = tree_mod.build(sample, depth=1)
    assert all(not c.get("children") for c in one["children"])

    two = tree_mod.build(sample, depth=2)
    src = next(c for c in two["children"] if c["name"] == "src")
    assert sorted(n["name"] for n in src["children"]) == ["a.py", "deep"]
    deep = next(c for c in src["children"] if c["name"] == "deep")
    assert deep["children"] == [], "depth 2 must not reach into deep/"

    three = tree_mod.build(sample, depth=3)
    src = next(c for c in three["children"] if c["name"] == "src")
    deep = next(c for c in src["children"] if c["name"] == "deep")
    assert names(deep) == ["b.py"]


def test_git_directory_is_never_shown(sample: Path) -> None:
    assert ".git" not in names(tree_mod.build(sample, depth=3))


def test_hidden_files_toggle(sample: Path) -> None:
    assert ".hidden" in names(tree_mod.build(sample, depth=1, show_hidden=True))
    assert ".hidden" not in names(tree_mod.build(sample, depth=1, show_hidden=False))


def test_entries_are_sorted_case_insensitively(sample: Path) -> None:
    shown = names(tree_mod.build(sample, depth=1, show_hidden=False))
    assert shown == sorted(shown, key=str.lower)


def test_gitignored_paths_are_skipped(git_repo: Path) -> None:
    shown = names(tree_mod.build(git_repo, depth=2, use_gitignore=True))
    assert "keep" in shown and "README.md" in shown
    for ignored in ("vendor", "vendor_docs", "build", "NOTES.md"):
        assert ignored not in shown, f"{ignored} is gitignored and must not appear"


def test_every_ignored_path_is_detected_not_only_the_last(git_repo: Path) -> None:
    """Regression: the ignore list was passed to `git check-ignore` over a text
    pipe, and on Windows Python rewrote each "\\n" separator as "\\r\\n". Git then
    saw paths ending in a stray "\\r" and matched none of them — except the final
    path, which has no separator after it. The result looked like gitignore was
    mostly working, while every entry but the last leaked into the tree.
    """
    entries = [p for p in sorted(git_repo.iterdir()) if p.name != ".git"]
    ignored = {p.name for p in tree_mod.batch_ignored(git_repo, entries)}
    assert ignored == {"vendor", "vendor_docs", "build", "NOTES.md"}


def test_no_gitignore_shows_everything(git_repo: Path) -> None:
    shown = names(tree_mod.build(git_repo, depth=1, use_gitignore=False))
    assert {"vendor", "vendor_docs", "build", "NOTES.md", "keep"} <= set(shown)


def test_outside_a_git_repo_renders_rather_than_failing(sample: Path) -> None:
    assert tree_mod.batch_ignored(sample, [sample / "README.md"]) == set()
    assert "README.md" in names(tree_mod.build(sample, depth=1, use_gitignore=True))


def test_render_uses_box_drawing_and_ascii(sample: Path) -> None:
    node = tree_mod.build(sample, depth=1, show_hidden=False)
    box = tree_mod.render(node)
    assert box[0] == "."
    assert any(line.startswith("├── ") for line in box)
    assert box[-1].startswith("└── ")

    plain = tree_mod.render(node, ascii_only=True)
    assert any(line.startswith("|-- ") for line in plain)
    assert plain[-1].startswith("`-- ")
    assert all(line.isascii() for line in plain)


def test_render_indents_nested_levels(sample: Path) -> None:
    lines = tree_mod.render(tree_mod.build(sample, depth=2, show_hidden=False))
    assert any(line.startswith(("│   ", "    ")) and "a.py" in line for line in lines)


def test_counts(sample: Path) -> None:
    counts = tree_mod.count(tree_mod.build(sample, depth=3, show_hidden=False))
    assert counts == {"directories": 3, "files": 3}


def test_cli_renders(runner: CliRunner, sample: Path) -> None:
    result = runner.invoke(app, ["tree", str(sample), "--depth", "1"])
    assert result.exit_code == 0, result.output
    assert "README.md" in result.stdout


def test_cli_json_shape(runner: CliRunner, sample: Path) -> None:
    result = runner.invoke(app, ["tree", str(sample), "--depth", "2", "--json"])
    assert result.exit_code == 0
    data = payload(result.stdout)["data"]
    assert data["depth"] == 2
    assert data["tree"]["type"] == "directory"
    assert set(data["counts"]) == {"directories", "files"}
    assert "README.md" in [c["name"] for c in data["tree"]["children"]]


def test_cli_rejects_a_file(runner: CliRunner, sample: Path) -> None:
    result = runner.invoke(app, ["tree", str(sample / "README.md"), "--json"])
    assert result.exit_code == 1
    assert payload(result.stdout)["error"]["code"] == "not_a_directory"


def test_cli_rejects_zero_depth(runner: CliRunner, sample: Path) -> None:
    assert runner.invoke(app, ["tree", str(sample), "--depth", "0"]).exit_code != 0
