# ClaudeForAnything conventions

Source of truth: `CLAUDE.md` at the repository root. This file is the operational
restatement of it for plugin authoring. If the two disagree, `CLAUDE.md` wins.

## 1. Naming

Two conventions, and picking the wrong one is the most common mistake.

| The plugin is...                              | Pattern              | Example                     |
| :-------------------------------------------- | :------------------- | :-------------------------- |
| Claude **doing an action**                     | `claude-for-{action}` | `claude-for-photo-editing`  |
| **A tool Claude uses**                         | `{tool}-for-claude`  | `crm-for-claude`            |

Rules:

- Name the **action**, never the SaaS product it replaces.
  `claude-for-photoshop` is wrong — Photoshop is a product. `claude-for-photo-editing` is right.
- kebab-case, lowercase, no spaces, no consecutive hyphens.
- The name is public-facing: users type `/plugin install <name>@claudeforanything`.

Ask one question to choose: *does the plugin describe something Claude does, or
something Claude reaches for?* Actions get `claude-for-`, tools get `-for-claude`.

## 2. CLI first, tool second

Every capability ships as a `claudeforanything` subcommand **before** it is
exposed to Claude as an MCP tool or a bundled script.

```
claudeforanything <plugin-name> --help
claudeforanything <plugin-name> <verb> [args]
claudeforanything <plugin-name> mcp        # exposes the same surface over MCP
```

Why: Claude composes shell commands far better than it composes tool calls. A CLI
gives pipes, loops, and `--help` discovery for free. An MCP tool gives none of that.

Order of work, without exception:

1. Implement the capability in `cli/`.
2. Expose it as MCP / bundled scripts afterward.
3. Write the skill that teaches Claude *how* to use it.

A plugin that bundles a script under `scripts/` before that logic exists in the CLI
is carrying technical debt. Say so in the plugin README and open the follow-up.

## 3. Everything as a skill

Every plugin, tool, and MCP server ships at least one skill compliant with
<https://agentskills.io/specification>. The skill carries the *how*: procedure,
decision rules, worked examples. The CLI carries the *what*.

Agent Skills are not Claude Code specific. Keep skills portable: prefer plain
relative paths and documented CLI invocations over Claude-Code-only constructs.
When a skill genuinely needs Claude Code, say so in its `compatibility:` field.

## 4. Layout

```
.claude-plugin/marketplace.json          # the catalog, at the repository root
marketplace/
├── plugins/<plugin-name>/              # one directory per plugin
│   ├── .claude-plugin/plugin.json
│   ├── skills/<skill-name>/SKILL.md
│   ├── references/                     # shared reference docs (plugin root)
│   ├── scripts/
│   └── README.md
└── skills/<skill-name>/SKILL.md        # standalone skills, no plugin needed
```

`marketplace/skills/` holds skills for general tasks that need no plugin behind
them. They are plain Agent Skills, publishable on their own.

## 5. Registering a plugin

Add an entry to `.claude-plugin/marketplace.json` at the **repository root**.
Use an explicit relative source that starts with `./`, written from the
marketplace root — which is the repository root, not `marketplace/`:

```json
{ "name": "crm-for-claude", "source": "./marketplace/plugins/crm-for-claude" }
```

Then validate: `claude plugin validate . --strict`.
