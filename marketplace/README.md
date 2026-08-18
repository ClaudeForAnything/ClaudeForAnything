# ClaudeForAnything marketplace

The Claude Code marketplace for ClaudeForAnything. *Let Claude handle everything.*

```bash
claude plugin marketplace add https://github.com/<owner>/claudeforanything
claude plugin install <plugin>@claudeforanything
```

To work on it locally, point Claude Code at this directory instead:

```bash
claude plugin marketplace add ./marketplace
```

## Layout

```
marketplace/
├── .claude-plugin/
│   └── marketplace.json        # the catalog — every installable entry
├── plugins/
│   └── <plugin-name>/          # one self-contained plugin per directory
│       ├── .claude-plugin/plugin.json
│       ├── skills/<skill>/SKILL.md
│       ├── references/
│       ├── scripts/
│       └── README.md
└── skills/
    └── <skill-name>/SKILL.md   # standalone skills, no plugin behind them
```

This directory — the one holding `.claude-plugin/` — is the **marketplace root**.
Every relative `source` in `marketplace.json` resolves from here, not from the
repository root.

### `plugins/`

Full Claude Code plugins: skills plus, where warranted, agents, hooks, MCP servers,
and bundled executables.

### `skills/`

Skills for general tasks that need no plugin behind them. Plain Agent Skills
compliant with <https://agentskills.io/specification>, publishable on their own and
portable to any agent that implements the spec. To make one installable from this
marketplace, add a catalog entry pointing at the marketplace root:

```json
{
  "name": "claude-for-<action>",
  "source": "./",
  "skills": ["./skills/<skill-name>"],
  "strict": false
}
```

## Naming

Two conventions. Picking the wrong one is the most common mistake.

| The plugin is...           | Pattern               | Example                    |
| :------------------------- | :-------------------- | :------------------------- |
| Claude **doing an action** | `claude-for-{action}` | `claude-for-photo-editing` |
| **A tool Claude uses**     | `{tool}-for-claude`   | `crm-for-claude`           |

Name the action, never the product it replaces. `claude-for-photoshop` is wrong;
`claude-for-photo-editing` is right.

## Catalog

| Plugin                        | What it does                                                       |
| :---------------------------- | :----------------------------------------------------------------- |
| `claude-for-plugin-authoring` | Author, scaffold, and review plugins and skills for this marketplace |

## Contributing

Install `claude-for-plugin-authoring` and use its skills — they encode the
conventions, the schemas, and the verification steps.

```bash
python plugins/claude-for-plugin-authoring/scripts/scaffold.py plugin <name> \
  --description "..."
```

Before committing anything here:

```bash
python plugins/claude-for-plugin-authoring/scripts/scaffold.py check
claude plugin validate . --strict
```
