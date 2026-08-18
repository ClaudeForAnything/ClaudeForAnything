# Agent Skill spec

Distilled from `vendor_docs/agentskills/specification.md`
(<https://agentskills.io/specification>).

## Directory

```
skill-name/
├── SKILL.md      # required: frontmatter + instructions
├── scripts/      # optional: executable code
├── references/   # optional: documentation loaded on demand
└── assets/       # optional: templates, resources
```

## Frontmatter

| Field           | Required | Constraints                                                                             |
| :-------------- | :------- | :--------------------------------------------------------------------------------------- |
| `name`          | Yes      | 1–64 chars, `a-z0-9-` only, no leading/trailing hyphen, no `--`. **Must match the directory name.** |
| `description`   | Yes      | 1–1024 chars. What it does **and** when to use it.                                       |
| `license`       | No       | License name or bundled license file                                                     |
| `compatibility` | No       | ≤500 chars. Environment requirements: product, system packages, network access.           |
| `metadata`      | No       | Map of string keys to string values                                                      |
| `allowed-tools` | No       | Space-separated pre-approved tools (experimental)                                        |

## Writing the description

This is the single highest-leverage field: it is the only thing loaded into every
session, and it is what decides whether the skill fires at all.

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

Include the concrete trigger words a user would actually type. State the *when*,
not only the *what*.

## Progressive disclosure

Keep `SKILL.md` to the procedure. Push schemas, long tables, and worked examples
into `references/` and link to them, so the agent pays for that context only when
it needs it. Inside a Claude Code plugin, reference plugin-root files with
`${CLAUDE_PLUGIN_ROOT}/references/<file>.md`.

## Naming inside a plugin

Skills in a plugin are namespaced as `<plugin-name>:<skill-name>`. Keep skill names
short — the plugin name already carries the domain. `crm-for-claude:add-contact`
reads well; `crm-for-claude:add-a-contact-to-the-crm` does not.
