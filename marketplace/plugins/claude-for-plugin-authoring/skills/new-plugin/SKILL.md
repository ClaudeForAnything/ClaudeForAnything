---
name: new-plugin
description: Create a new plugin in the ClaudeForAnything marketplace, from naming through manifest, skills, CLI surface, and catalog registration. Use when adding a plugin under marketplace/plugins/, when asked to "make a plugin for X", or when deciding whether something should be claude-for-X or X-for-claude.
license: MIT
compatibility: Designed for the ClaudeForAnything repository. Requires Python 3.12 and the Claude Code CLI for validation.
---

# Create a ClaudeForAnything plugin

## When to use this

- Adding anything new under `marketplace/plugins/`.
- Someone asks for "a plugin that does X" or "Claude should be able to do X".
- You need to decide between the `claude-for-X` and `X-for-claude` naming forms.

For a skill that needs no plugin behind it, use `new-skill` instead.

## Step 1 — Name it

Read `${CLAUDE_PLUGIN_ROOT}/references/conventions.md` and answer one question:

**Does the plugin describe something Claude *does*, or something Claude *reaches for*?**

- Does → `claude-for-<action>`. The action, never the product it replaces.
  `claude-for-photo-editing`, not `claude-for-photoshop`.
- Reaches for → `<tool>-for-claude`. `crm-for-claude`, `invoicing-for-claude`.

Get this wrong and the whole catalog reads inconsistently, so settle it before
writing any files. If the user proposed a name that breaks the convention, say so
and propose the corrected one — do not silently rename.

## Step 2 — Decide what the plugin actually ships

Write down, in one line each, before scaffolding:

- The **CLI verbs**. What does `claudeforanything <name> --help` list?
- The **skills**. One per coherent procedure. Name them short — they are namespaced
  as `<plugin-name>:<skill-name>` already.
- Whether it needs **agents**, **hooks**, an **MCP server**, or none of those.

Default to skills-only. Add components when there is a concrete reason.

## Step 3 — Respect CLI-first

The repository rule is absolute: the capability is implemented in `cli/` first,
and exposed to Claude second. Concretely:

1. `claudeforanything <name> <verb>` works from a terminal.
2. `claudeforanything <name> mcp` exposes the same surface over MCP.
3. The skill teaches Claude *how* to compose those commands.

If the CLI does not exist yet, you may still ship the plugin's skills and a
bundled script under `scripts/`, but record it in the plugin README as debt to be
lifted into the CLI. Do not pretend the script is the finished design.

## Step 4 — Scaffold

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" plugin <name> \
  --description "<what it does and when to use it>" \
  --with skills
```

The script refuses names that break the convention. It creates:

```
marketplace/plugins/<name>/
├── .claude-plugin/plugin.json
├── skills/example/SKILL.md
└── README.md
```

Add `--with agents hooks mcp` for the other component folders.

## Step 5 — Write the manifest and the skills

- Fill in `plugin.json`. Field reference:
  `${CLAUDE_PLUGIN_ROOT}/references/plugin-manifest.md`.
  Keep `"version": "0.1.0"` and remember it pins the plugin — bump it for users to
  receive changes.
- Replace `skills/example/` with the real skills. Frontmatter rules:
  `${CLAUDE_PLUGIN_ROOT}/references/skill-spec.md`. The `description` field is the
  highest-leverage line in the plugin; it decides whether the skill ever fires.
- Fill in the README's skills table and CLI status.

## Step 6 — Register it in the catalog

Add an entry to `marketplace/.claude-plugin/marketplace.json`:

```json
{
  "name": "<name>",
  "source": "./plugins/<name>",
  "description": "<same one-liner>",
  "version": "0.1.0",
  "author": {
    "name": "Emerick @ ClaudeForAnything",
    "email": "emerick@claudeforanything.com"
  },
  "license": "MIT",
  "category": "<category>",
  "keywords": ["..."],
  "tags": ["..."]
}
```

Sources are written from the marketplace root — the directory holding
`.claude-plugin/`, which is `marketplace/`, not the repository root. Full field
reference: `${CLAUDE_PLUGIN_ROOT}/references/marketplace-entry.md`.

## Step 7 — Verify

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/scaffold.py" check
claude plugin validate marketplace --strict
```

Both must pass. Then install it locally and confirm the skills appear:

```bash
claude plugin marketplace add ./marketplace
claude plugin install <name>@claudeforanything
claude plugin details <name>@claudeforanything
```

`plugin details` also prints the token cost the plugin adds to every session.
If the always-on figure looks heavy, the skill descriptions are too long.

## Step 8 — Update the tree

`CLAUDE.md` requires refreshing its "Current tree" block at the end of the work:

```bash
eza --tree --level=2 -a
```
