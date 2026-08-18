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

The capability lives in the [`claudeforanything` CLI](../../../cli/), per the
repository's CLI-first rule. This plugin's skills drive it; they do not carry a
bundled copy of the logic.

```bash
claudeforanything claude-for-plugin-authoring --help
claudeforanything claude-for-plugin-authoring new-plugin <name> --description "..." [--with skills agents hooks mcp]
claudeforanything claude-for-plugin-authoring new-skill <name> --description "..." [--plugin <plugin-name>]
claudeforanything claude-for-plugin-authoring check
```

Every command accepts `--json`, so results compose:

```bash
claudeforanything claude-for-plugin-authoring check --json | jq -r '.data.failures[].message'
```

`check` enforces what `claude plugin validate` does not: the ClaudeForAnything
naming conventions, plugins present on disk but missing from the catalog, and
`SKILL.md` frontmatter names matching their directories.

**Requires the CLI on your PATH.** From a clone: `uv tool install ./cli`.

## Install

```bash
claude plugin marketplace add ClaudeForAnything/ClaudeForAnything
claude plugin install claude-for-plugin-authoring@claudeforanything
```
