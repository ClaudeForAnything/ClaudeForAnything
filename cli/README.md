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
uv tool install -e ./cli    # or install it on your PATH, editable
```

## Use

```bash
claudeforanything                       # help
claudeforanything list --json           # the plugin namespaces this CLI exposes
claudeforanything version --json

claudeforanything tree                  # depth 2, .gitignore respected
claudeforanything tree --depth 3 --json
claudeforanything tree --no-gitignore   # everything, like `eza --tree --level=2 -a`
claudeforanything tree --ascii          # ASCII connectors

claudeforanything claude-for-plugin-authoring --help
claudeforanything claude-for-plugin-authoring check --json
claudeforanything claude-for-plugin-authoring new-plugin crm-for-claude \
  --description "A CRM for Claude."
claudeforanything claude-for-plugin-authoring new-skill add-contact \
  --plugin crm-for-claude --description "..."

claudeforanything emails-for-claude --help
claudeforanything emails-for-claude parameters you@example.com --probe
claudeforanything emails-for-claude account add work --address you@example.com
claudeforanything emails-for-claude account set-password work
claudeforanything emails-for-claude inbox --unseen --json
claudeforanything emails-for-claude read 4417 --json
claudeforanything emails-for-claude send --to a@example.com --subject Hi \
  --body "..." --dry-run
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
├── mail/             # the emails-for-claude engine: imaplib, poplib, smtplib, keyring
├── output.py         # --json envelope, CliError, emit/fail
├── paths.py          # marketplace root discovery
├── naming.py         # the claude-for-X / X-for-claude conventions
└── templates.py      # scaffolded file bodies
```

Adding a plugin namespace means writing `namespaces/<plugin>.py` with a
`typer.Typer` app and adding one line to `NAMESPACES`. The namespace name must
match the plugin name in the marketplace catalog.

A namespace that needs real logic keeps it in its own package next to
`namespaces/` — `mail/` for `emails-for-claude` — so the Typer module stays a
thin command surface and the engine is testable without going through the CLI.

## Secrets

`emails-for-claude` is the first namespace that handles a credential. The rule it
sets: secrets go to the OS keyring and nowhere else. Nothing writes a password to
a config file, a command line, or stdout, and `--json` output reports only *where*
a password came from. Tests replace the keyring with an in-memory dict (see the
`fake_keyring` fixture) so a test run never touches the developer's real
credential store.

## Test

```bash
uv run pytest
```

## Why `tree` is built in

`eza --tree` writes its listing to the Windows console handle rather than to
stdout, so the output vanishes the moment it is piped or captured — which is
exactly what an agent does. `eza --version` prints fine, which makes it look
like the tool works. Git for Windows ships no `tree` binary either.

Two things any replacement has to survive, and this one does:

- Box-drawing characters cannot encode to cp1252, the default Windows stdout
  encoding. `main.py` forces UTF-8 on stdout for every command; `--ascii` is the
  fallback.
- Ignored directories must not be descended into. `vendor_docs/` alone is 6,000
  files, so honouring `.gitignore` is correctness, not polish.

`claudeforanything tree --no-gitignore` reproduces `eza --tree --level=2 -a`
line for line, which is what the tree block in `CLAUDE.md` expects.

