# claude-for-plugin-authoring

Author, scaffold, and review ClaudeForAnything plugins and Agent Skills.

This plugin is an action Claude performs: authoring plugins. It is the meta-plugin
of the marketplace — it encodes the conventions from `CLAUDE.md` and the Claude
Code plugin schemas so every later plugin is built the same way.

## Skills

| Skill           | What it does                                                                    |
| :-------------- | :------------------------------------------------------------------------------ |
| `new-plugin`    | Create a plugin end to end: naming, manifest, skills, CLI surface, registration  |
| `new-skill`     | Write an agentskills.io-compliant `SKILL.md`, in a plugin or standalone          |
| `review-plugin` | Review a plugin or the whole marketplace against the conventions and the schemas |

## References

Distilled schemas, so the skills never re-read 60 KB of vendor docs:

| File                              | Covers                                                |
| :-------------------------------- | :---------------------------------------------------- |
| `references/conventions.md`       | ClaudeForAnything naming, CLI-first, everything-as-a-skill |
| `references/plugin-manifest.md`   | `plugin.json` schema, component locations, path variables |
| `references/marketplace-entry.md` | `marketplace.json` schema, plugin sources, strict mode |
| `references/skill-spec.md`        | Agent Skill frontmatter and structure                 |

Sources: `vendor_docs/claude_code/plugins-reference.md`,
`vendor_docs/claude_code/plugin-marketplaces.md`,
`vendor_docs/agentskills/specification.md`. When a field is not in the distilled
reference, read the vendor doc — never guess a signature.

## CLI

```bash
claudeforanything claude-for-plugin-authoring --help
claudeforanything claude-for-plugin-authoring scaffold plugin <name> --description "..."
claudeforanything claude-for-plugin-authoring check
```

**Status: not implemented.** `cli/` is empty, so the logic currently lives in
`scripts/scaffold.py`, written stdlib-only and CLI-shaped so it lifts into the CLI
unchanged. This is debt, and it is the first thing to pay down once `cli/` exists.

Until then:

```bash
python scripts/scaffold.py plugin <name> --description "..." [--with skills agents hooks mcp]
python scripts/scaffold.py skill <name> --description "..." [--plugin <plugin-name>]
python scripts/scaffold.py check
```

`check` enforces what `claude plugin validate` does not: the ClaudeForAnything
naming conventions, plugins present on disk but missing from the catalog, and
`SKILL.md` frontmatter names matching their directories.

## Install

```bash
claude plugin marketplace add ClaudeForAnything/ClaudeForAnything
claude plugin install claude-for-plugin-authoring@claudeforanything
```
