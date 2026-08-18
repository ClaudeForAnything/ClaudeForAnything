# `marketplace.json` schema

Distilled from `vendor_docs/claude_code/plugin-marketplaces.md`.

Location: `.claude-plugin/marketplace.json` at the **repository root**.
The **marketplace root** is the directory containing `.claude-plugin/`. Claude Code
looks for it at the root of the cloned repository when a marketplace is added by
`owner/repo`, so it cannot live in a subdirectory. Every relative plugin `source`
resolves from there, which is why plugin sources here read
`./marketplace/plugins/<name>`.

## Top level

| Field                                 | Required | Notes                                                                          |
| :------------------------------------ | :------- | :------------------------------------------------------------------------------ |
| `name`                                | Yes      | kebab-case. Public: users type `<plugin>@<name>`. One marketplace per name per user. |
| `owner`                               | Yes      | `{ name (required), email?, url? }`                                             |
| `plugins`                             | Yes      | Array of plugin entries                                                         |
| `description`                         | No       |                                                                                 |
| `version`                             | No       | Manifest version                                                                |
| `metadata.pluginRoot`                 | No       | Base directory prepended to relative sources. We do not use it — write full paths. |
| `allowCrossMarketplaceDependenciesOn` | No       | Marketplaces our plugins may depend on                                          |
| `renames`                             | No       | Old plugin name → new name, or `null` if removed. Migrates existing users. v2.1.193+. |

Reserved marketplace names (blocked for third parties): `claude-code-marketplace`,
`claude-code-plugins`, `claude-plugins-official`, `claude-plugins-community`,
`claude-community`, `anthropic-marketplace`, `anthropic-plugins`, `agent-skills`,
`anthropic-agent-skills`, `knowledge-work-plugins`, `life-sciences`,
`claude-for-legal`, `claude-for-financial-services`, `financial-services-plugins`,
`first-party-plugins`, `healthcare`. Names impersonating official sources are also
blocked. `claudeforanything` is clear.

## Plugin entry

Required: `name` and `source`. Any field from the plugin manifest schema is also
accepted, plus the marketplace-only fields `source`, `category`, `tags`, `strict`,
`relevance`, and `defaultEnabled`.

| Field            | Notes                                                                                     |
| :--------------- | :---------------------------------------------------------------------------------------- |
| `source`         | string or object — see below                                                              |
| `category`       | Organizational grouping                                                                   |
| `tags`           | Searchability                                                                             |
| `strict`         | Default `true`: `plugin.json` is the authority and the entry supplements it. `false`: the entry is the entire definition, and a `plugin.json` declaring components is a load error. |
| `defaultEnabled` | Takes precedence over the same field in `plugin.json`                                     |
| `metadata`       | Free-form; Claude Code does not read it                                                   |

## Sources

| Source        | Shape                              | Fields                             |
| :------------ | :--------------------------------- | :--------------------------------- |
| Relative path | `"./marketplace/plugins/my-plugin"` | —                                 |
| `github`      | object                             | `repo`, `ref?`, `sha?`             |
| `url`         | object                             | `url`, `ref?`, `sha?`              |
| `git-subdir`  | object                             | `url`, `path`, `ref?`, `sha?`      |
| `npm`         | object                             | `package`, `version?`, `registry?` |
| `archive`     | object                             | `url`, `sha256?` — v2.1.224+       |
| `command`     | object                             | `command`, `timeout?`, `mode?` — v2.1.229+ |

When both `ref` and `sha` are set, `sha` wins.

Relative paths must start with `./` and must not use `../`. They resolve against a
local copy of the marketplace, so they work for git-source and local-directory
installs — but **not** when a user adds the marketplace by direct URL to
`marketplace.json`, because only that one file is downloaded.

## Standalone skills from `marketplace/skills/`

To publish a skill that has no plugin behind it, point the entry straight at the
skill directory:

```json
{
  "name": "<skill-name>",
  "source": "./marketplace/skills/<skill-name>"
}
```

A directory with a `SKILL.md` at its root, no `skills/` subdirectory, and no
`skills` manifest field is loaded as a single-skill plugin, so no `plugin.json` is
needed. The invocation name comes from the frontmatter `name` rather than the
install directory — which for a marketplace install is a version string that
changes on every update.

There is a second form, pointing the entry at the marketplace root and listing
subdirectories:

```json
{ "source": "./", "skills": ["./marketplace/skills/<skill-name>"], "strict": false }
```

With a marketplace-root `source` the listed paths are the complete set for that
entry, and `strict: false` lets the entry stand in for a `plugin.json` that does
not exist. **Do not use it here.** Because the marketplace root is the repository
root, it would copy the entire repository into every user's plugin cache.

## Validate

```bash
claude plugin validate . --strict
```
