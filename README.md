# ClaudeForAnything

**Let Claude handle everything.**

A Claude Code marketplace of plugins and Agent Skills that give Claude real
capabilities — and a CLI that exposes every one of them from a terminal.

## Install

Add the marketplace, then install what you want from it:

```bash
claude plugin marketplace add ClaudeForAnything/ClaudeForAnything
claude plugin install claude-for-plugin-authoring@claudeforanything
```

## Catalog

| Plugin                        | What it does                                                         |
| :---------------------------- | :------------------------------------------------------------------- |
| `claude-for-plugin-authoring` | Author, scaffold, and review plugins and skills for this marketplace  |

Standalone skills — for general tasks that need no plugin behind them — live in
[`marketplace/skills/`](marketplace/skills/).

## How it is built

Three rules shape everything here.

### 1. Name the action, not the product

| The plugin is...           | Pattern               | Example                    |
| :------------------------- | :-------------------- | :------------------------- |
| Claude **doing an action** | `claude-for-{action}` | `claude-for-photo-editing` |
| **A tool Claude uses**     | `{tool}-for-claude`   | `crm-for-claude`           |

`claude-for-photoshop` is wrong — Photoshop is a product. The action is photo
editing.

### 2. CLI first, tool second

Every capability ships as a `claudeforanything` subcommand before it is exposed to
Claude as an MCP tool:

```bash
claudeforanything <plugin-name> --help
claudeforanything <plugin-name> mcp     # the same surface, over MCP
```

Claude composes shell commands far better than it composes tool calls. A CLI gives
pipes, loops, and `--help` discovery for free; an MCP tool gives none of that.

### 3. Everything as a skill

Every plugin, tool, and MCP server ships at least one skill compliant with the
[Agent Skills specification](https://agentskills.io/specification). The CLI carries
the *what*; the skill carries the *how*.

Agent Skills are not Claude Code specific, so skills here stay portable to any
agent that implements the spec.

## Layout

```
marketplace/
├── .claude-plugin/marketplace.json   # the catalog
├── plugins/<plugin-name>/            # one self-contained plugin per directory
└── skills/<skill-name>/              # standalone skills, no plugin behind them
cli/                                  # the claudeforanything CLI
```

## Contributing

Install `claude-for-plugin-authoring` and use its skills — they encode the
conventions, the schemas, and the verification steps.

```bash
claudeforanything claude-for-plugin-authoring new-plugin <name> --description "..."
```

Before opening a pull request:

```bash
claudeforanything claude-for-plugin-authoring check
claude plugin validate . --strict
```

## License

[GNU General Public License v3.0 or later](LICENSE).

ClaudeForAnything is free software: you may use, study, share, and modify it. If
you distribute it, modified or not, the recipients get the same freedoms and the
corresponding source. See [choosealicense.com/licenses/gpl-3.0](https://choosealicense.com/licenses/gpl-3.0/)
for a plain-language summary.
