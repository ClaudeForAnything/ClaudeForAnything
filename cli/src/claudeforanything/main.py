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

import typer

from . import __version__
from .namespaces import NAMESPACES
from .output import JsonOption, emit

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


if __name__ == "__main__":
    app()
