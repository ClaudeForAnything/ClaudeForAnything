---
name: review-plugin
description: Review a ClaudeForAnything plugin or the whole marketplace against the naming conventions, the plugin.json and marketplace.json schemas, the CLI-first rule, and the Agent Skill spec. Use before committing changes under marketplace/, when a plugin fails to load, or when a skill does not appear after install.
license: GPL-3.0-or-later
compatibility: Designed for the ClaudeForAnything repository. Requires the claudeforanything CLI on PATH (uv tool install ./cli) and the Claude Code CLI for validation.
---

# Review a plugin

## When to use this

- Before committing anything under `marketplace/`.
- A plugin installs but its skills, agents, or hooks do not show up.
- `claude plugin validate` fails and the error needs interpreting.

## Step 1 — Run the automated checks

```bash
claudeforanything claude-for-plugin-authoring check
claude plugin validate . --strict
```

The two cover different ground:

| Checker            | Catches                                                                        |
| :----------------- | :------------------------------------------------------------------------------ |
| `claudeforanything claude-for-plugin-authoring check` | ClaudeForAnything naming, missing manifests, plugins on disk but absent from the catalog, `SKILL.md` frontmatter name not matching its directory |
| `claude plugin validate --strict` | JSON schema errors, unrecognized and misspelled manifest fields, bad hook config |

Every CLI command takes `--json`, which emits `{"ok": ..., "data": ...}` on
stdout. Use it when you want to act on the findings rather than read them:

```bash
claudeforanything claude-for-plugin-authoring check --json | jq -r '.data.failures[].message'
```

`--strict` turns warnings into errors, which is what you want here: it catches a
field name that is one character off from a real one, which would otherwise be
silently ignored at load time.

## Step 2 — Check the naming by hand

Automated checks confirm the *shape* `claude-for-X` or `X-for-claude`. They cannot
tell you the name is meaningful. Verify:

- `claude-for-<action>` names an **action**, not a product. `claude-for-photoshop`
  passes the regex and is still wrong.
- `<tool>-for-claude` names a **tool Claude uses**, not an action.
- The name would still read correctly to someone who has never seen the repository.

Reference: `${CLAUDE_PLUGIN_ROOT}/references/conventions.md`.

## Step 3 — Check the CLI-first rule

Repository rule: the capability is implemented in `cli/` first and exposed to
Claude second. For the plugin under review:

- Does `claudeforanything <plugin-name> --help` exist? If not, is the gap recorded
  in the plugin README as debt?
- If the plugin ships an MCP server, does it expose the same surface as the CLI, or
  has it drifted into being the primary interface?
- Do the skills teach Claude to compose CLI commands, or do they hard-code tool
  calls that cannot be piped?

A plugin whose only interface is an MCP tool is not finished, however well it works.

## Step 4 — Check the structure

```
plugins/<name>/
├── .claude-plugin/plugin.json   ← only plugin.json lives here
├── skills/<skill>/SKILL.md
├── agents/  hooks/  scripts/  bin/  .mcp.json  .lsp.json   ← all at the plugin root
└── README.md
```

The single most common structural bug is components placed **inside**
`.claude-plugin/`. The plugin then loads with no components and no error. If skills
are missing after install, check this first.

Two more that bite:

- Paths in `plugin.json` must be relative and start with `./`. Absolute paths fail.
- Paths must not traverse outside the plugin root. `../shared` works locally and
  breaks after install, because only the plugin directory is copied into the cache.

Field references: `${CLAUDE_PLUGIN_ROOT}/references/plugin-manifest.md` and
`${CLAUDE_PLUGIN_ROOT}/references/marketplace-entry.md`.

## Step 5 — Check the skills

For each `SKILL.md`:

- Does `description` say both what it does **and** when to use it, in words a user
  would actually type? A skill that never fires is worse than no skill.
- Is the body a procedure — numbered steps, exact commands, a stated definition of
  done — rather than documentation?
- Is the long material in `references/` rather than inline?

Reference: `${CLAUDE_PLUGIN_ROOT}/references/skill-spec.md`.

## Step 6 — Check the cost

```bash
claude plugin details <name>@claudeforanything
```

This prints the always-on token cost the plugin adds to **every** session, plus
the on-invoke cost per component. Always-on cost is paid whether or not anything
fires, so it is the number that matters as the catalog grows. If it looks heavy,
the skill descriptions are too long or there are too many skills for one plugin.

## Step 7 — Install it clean

```bash
claude plugin marketplace add ClaudeForAnything/ClaudeForAnything
claude plugin install <name>@claudeforanything
claude --debug            # look for the plugin-loading lines
```

`--debug` reports which plugins loaded, manifest errors, and skill, agent, and hook
registration. A plugin that validates but registers nothing has a structure
problem — go back to step 4.

## Common failures

| Symptom                           | Cause                                  | Fix                                            |
| :-------------------------------- | :------------------------------------- | :--------------------------------------------- |
| Plugin does not load              | Invalid `plugin.json`                  | `claude plugin validate`                        |
| Skills do not appear              | `skills/` inside `.claude-plugin/`     | Move it to the plugin root                     |
| Hooks do not fire                 | Script not executable                  | `chmod +x`                                     |
| MCP server fails                  | Missing `${CLAUDE_PLUGIN_ROOT}`        | Use the variable for every plugin path         |
| Path errors                       | Absolute paths                         | Make relative, starting with `./`              |
| Users do not receive an update    | `version` in `plugin.json` not bumped  | Bump it, or unset it to version by commit SHA  |
