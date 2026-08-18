# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""The `claudeforanything` root command.

Every plugin, tool, and MCP server in the marketplace is reachable here, because
Claude composes shell pipelines far better than it composes tool calls. Each
plugin gets a namespace matching its marketplace name:

    claudeforanything --help
    claudeforanything claude-for-plugin-authoring --help
    claudeforanything claude-for-plugin-authoring check --json
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from . import __version__, tree as tree_mod
from .namespaces import NAMESPACES
from .output import CliError, JsonOption, emit, fail

# Windows defaults stdout to cp1252, which cannot encode the box-drawing
# characters `tree` emits. Done once here so every command is safe rather than
# each one remembering. Guarded because test runners replace stdout with a
# stream that has no reconfigure().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

app = typer.Typer(
    name="claudeforanything",
    help="Let Claude handle everything. Every marketplace plugin, from a terminal.",
    no_args_is_help=True,
    add_completion=True,
    suggest_commands=True,
)

for _name, (_sub_app, _help) in NAMESPACES.items():
    app.add_typer(_sub_app, name=_name, help=_help)


@app.command()
def version(as_json: JsonOption = False) -> None:
    """Print the CLI version."""
    emit(
        {"name": "claudeforanything", "version": __version__},
        [f"claudeforanything {__version__}"],
        as_json=as_json,
    )


@app.command("list")
def list_namespaces(as_json: JsonOption = False) -> None:
    """List the plugin namespaces this CLI exposes."""
    namespaces = [{"name": name, "help": help_text} for name, (_, help_text) in NAMESPACES.items()]
    width = max((len(n["name"]) for n in namespaces), default=0)
    emit(
        {"namespaces": namespaces},
        [f"{n['name']:<{width}}  {n['help']}" for n in namespaces],
        as_json=as_json,
    )


@app.command()
def tree(
    path: Annotated[Path, typer.Argument(help="Directory to render.")] = Path("."),
    depth: Annotated[
        int, typer.Option("--depth", "-L", min=1, help="How many levels to descend.")
    ] = 2,
    all_: Annotated[
        bool,
        typer.Option("--all/--no-hidden", "-a", help="Include dot-files and dot-directories."),
    ] = True,
    gitignore: Annotated[
        bool,
        typer.Option(
            "--gitignore/--no-gitignore",
            help="Skip paths git ignores. Off outside a git work tree.",
        ),
    ] = True,
    ascii_only: Annotated[
        bool, typer.Option("--ascii", help="Use ASCII connectors instead of box-drawing.")
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Render a directory tree.

    Depth 2 by default, matching the tree block CLAUDE.md asks to be kept
    current. `.git` is never shown.
    """
    try:
        if not path.is_dir():
            raise CliError(f"not a directory: {path}", code="not_a_directory")

        label = str(path) if str(path) != "." else "."
        node = tree_mod.build(
            path.resolve(),
            depth=depth,
            show_hidden=all_,
            use_gitignore=gitignore,
            label=label,
        )
        emit(
            {
                "root": str(path.resolve()),
                "depth": depth,
                "counts": tree_mod.count(node),
                "tree": node,
            },
            tree_mod.render(node, ascii_only=ascii_only),
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


if __name__ == "__main__":
    app()
