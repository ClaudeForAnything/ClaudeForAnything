# claudeforanything

The ClaudeForAnything CLI. Every plugin, tool, and MCP server in the marketplace,
usable from a terminal.

## Why a CLI first

Claude composes shell commands far better than it composes tool calls. A CLI
gives pipes, loops, and `--help` discovery for free; an MCP tool gives none of
that. So every capability lands here first and is exposed to Claude second.

Every command accepts `--json`, which emits a stable envelope on stdout:

```json
{"ok": true,  "data": {}}
{"ok": false, "error": {"code": "", "message": ""}}
```

Successes and failures share the shape, so a caller can branch on `.ok` without
knowing which command produced the document.

## Install

```bash
uv sync                     # development, from this directory
uv run claudeforanything --help
```

```bash
uv tool install ./cli       # or install it on your PATH
```

## Use

```bash
claudeforanything                       # help
claudeforanything list --json           # the plugin namespaces this CLI exposes
claudeforanything version --json

claudeforanything claude-for-plugin-authoring --help
claudeforanything claude-for-plugin-authoring check --json
claudeforanything claude-for-plugin-authoring new-plugin crm-for-claude \
  --description "A CRM for Claude."
claudeforanything claude-for-plugin-authoring new-skill add-contact \
  --plugin crm-for-claude --description "..."
```

Commands that operate on the marketplace find its root by walking up from the
working directory for `.claude-plugin/marketplace.json`. Override with `--root`
or `$CLAUDEFORANYTHING_ROOT`.

## Layout

```
src/claudeforanything/
├── main.py           # the root app; registers one namespace per plugin
├── namespaces/
│   ├── __init__.py   # NAMESPACES: the explicit, greppable registry
│   └── <plugin>.py   # one module per marketplace plugin
├── output.py         # --json envelope, CliError, emit/fail
├── paths.py          # marketplace root discovery
├── naming.py         # the claude-for-X / X-for-claude conventions
└── templates.py      # scaffolded file bodies
```

Adding a plugin namespace means writing `namespaces/<plugin>.py` with a
`typer.Typer` app and adding one line to `NAMESPACES`. The namespace name must
match the plugin name in the marketplace catalog.

## Test

```bash
uv run pytest
```
