# ClaudeForAnything marketplace content

The plugins and skills published by the `claudeforanything` marketplace.

The catalog itself is **not** here — it lives at `../.claude-plugin/marketplace.json`,
at the repository root, because that is where Claude Code looks for it when a
marketplace is added by `owner/repo`. The repository root is therefore the
*marketplace root*, and every relative `source` in the catalog is written from
there: `./marketplace/plugins/<name>`.

```bash
claude plugin marketplace add ClaudeForAnything/ClaudeForAnything
claude plugin install <plugin>@claudeforanything
```

To work on it locally, point Claude Code at the repository root:

```bash
claude plugin marketplace add ./
```

## Layout

```
<repo root>/
├── .claude-plugin/
│   └── marketplace.json        # the catalog — every installable entry
└── marketplace/
    ├── plugins/
    │   └── <plugin-name>/      # one self-contained plugin per directory
    │       ├── .claude-plugin/plugin.json
    │       ├── skills/<skill>/SKILL.md
    │       ├── references/
    │       ├── scripts/
    │       └── README.md
    └── skills/
        └── <skill-name>/SKILL.md   # standalone skills, no plugin behind them
```

### `plugins/`

Full Claude Code plugins: skills plus, where warranted, agents, hooks, MCP servers,
and bundled executables.

### `skills/`

Skills for general tasks that need no plugin behind them. Plain Agent Skills
compliant with <https://agentskills.io/specification>, publishable on their own and
portable to any agent that implements the spec. To make one installable from this
marketplace, add a catalog entry pointing straight at the skill directory:

```json
{
  "name": "<skill-name>",
  "source": "./marketplace/skills/<skill-name>"
}
```

A directory with a `SKILL.md` at its root, no `skills/` subdirectory, and no
`skills` manifest field is loaded as a single-skill plugin, so no `plugin.json` is
needed. The invocation name comes from the skill's frontmatter `name`.

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

See [CONTRIBUTING.md](../CONTRIBUTING.md) at the repository root for the full
procedure, and [GOVERNANCE.md](../GOVERNANCE.md) for what gets accepted into the
catalog.

```bash
claudeforanything claude-for-plugin-authoring new-plugin <name> --description "..."
```

Before committing anything here, from the repository root:

```bash
claudeforanything claude-for-plugin-authoring check
claude plugin validate . --strict
```
