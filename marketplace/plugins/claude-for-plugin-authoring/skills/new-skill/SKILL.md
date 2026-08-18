---
name: new-skill
description: Write an agentskills.io-compliant Agent Skill, either inside a ClaudeForAnything plugin or standalone under marketplace/skills/. Use when adding or rewriting a SKILL.md, when a skill is not firing when it should, or when deciding what belongs in SKILL.md versus references/.
license: MIT
compatibility: Designed for the ClaudeForAnything repository. Requires the claudeforanything CLI on PATH (uv tool install ./cli).
---

# Write an Agent Skill

## When to use this

- Adding a `SKILL.md` anywhere under `marketplace/`.
- A skill exists but never fires — that is almost always a `description` problem.
- Deciding whether a capability needs a whole plugin or just a skill.

## Step 1 — Plugin skill or standalone?

| The skill...                                            | Goes to                            |
| :------------------------------------------------------- | :--------------------------------- |
| Drives a CLI, MCP server, or other plugin machinery      | `marketplace/plugins/<plugin>/skills/<name>/` |
| Teaches a general task needing nothing but Claude itself | `marketplace/skills/<name>/`       |

Standalone skills are plain Agent Skills. They stay portable to any agent that
implements <https://agentskills.io/specification>, so keep Claude-Code-only
constructs out of them and declare limits in `compatibility:`.

## Step 2 — Name it

`a-z`, `0-9`, hyphens. 1–64 characters. No leading or trailing hyphen, no `--`.
**The `name` in frontmatter must match the directory name.**

Inside a plugin the skill is namespaced as `<plugin-name>:<skill-name>`, so the
plugin name already carries the domain. Keep the skill name to the verb:
`crm-for-claude:add-contact`, not `crm-for-claude:add-a-contact-to-the-crm`.

## Step 3 — Scaffold

```bash
# Inside a plugin
claudeforanything claude-for-plugin-authoring new-skill <name> \
  --plugin <plugin-name> --description "<...>"

# Standalone
claudeforanything claude-for-plugin-authoring new-skill <name> --description "<...>"
```

## Step 4 — Write the description

This is the whole job. The description is the only part of a skill loaded into
every session, and it is what decides whether the skill fires at all. Everything
else is dead weight if this line is vague.

Cover both halves:

- **What** it does, concretely.
- **When** to use it — including the words a user would actually type.

Good:

```yaml
description: Extracts text and tables from PDF files, fills PDF forms, and merges
  multiple PDFs. Use when working with PDF documents or when the user mentions
  PDFs, forms, or document extraction.
```

Poor:

```yaml
description: Helps with PDFs.
```

Maximum 1024 characters. Full frontmatter reference:
`${CLAUDE_PLUGIN_ROOT}/references/skill-spec.md`.

## Step 5 — Write the body as a procedure

`SKILL.md` is instructions for an agent, not documentation for a human. That means:

- Numbered steps in the order they are performed.
- Decision rules where there is a choice, with the criterion stated.
- Exact commands, copy-pasteable.
- What "done" looks like, and how to verify it.

Leave out: marketing, history, restatements of the description, and anything the
agent can read off the code.

## Step 6 — Push detail into references/

Keep `SKILL.md` to the procedure. Schemas, long tables, worked examples, and API
surfaces go in `references/` and are linked from the body, so they cost context
only when they are actually needed.

```
skill-name/
├── SKILL.md
├── references/schema.md
├── scripts/
└── assets/
```

Inside a plugin, shared reference files live at the plugin root and are addressed
as `${CLAUDE_PLUGIN_ROOT}/references/<file>.md` — that variable is substituted in
skill content at load time. Standalone skills use plain relative paths so they
stay portable.

## Step 7 — Verify

```bash
claudeforanything claude-for-plugin-authoring check
claude plugin validate . --strict
```

`check` enforces the frontmatter-name-matches-directory rule that the JSON schema
validator does not cover.

Then confirm the skill actually triggers: start a session, phrase a request the
way a real user would, and see whether it fires without being named. If it does
not, the description is the thing to fix.
