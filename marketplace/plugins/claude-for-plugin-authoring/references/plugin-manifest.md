# `plugin.json` schema

Distilled from `vendor_docs/claude_code/plugins-reference.md`. Read the vendor doc
when you need a field that is not here — do not guess field names.

Location: `<plugin-root>/.claude-plugin/plugin.json`. Only `plugin.json` lives in
`.claude-plugin/`. Every component directory sits at the plugin root.

The manifest is optional. Without it, components are auto-discovered from default
locations and the plugin name comes from the directory name. ClaudeForAnything
plugins always ship one, because we want explicit metadata.

## Required

| Field  | Type   | Notes                                                        |
| :----- | :----- | :----------------------------------------------------------- |
| `name` | string | kebab-case, no spaces. Namespaces components: `<name>:<skill>` |

## Metadata

| Field            | Type    | Notes                                                                                                              |
| :--------------- | :------ | :----------------------------------------------------------------------------------------------------------------- |
| `$schema`        | string  | `https://json.schemastore.org/claude-code-plugin-manifest.json`. Ignored at load time; enables editor autocomplete. |
| `displayName`    | string  | Human-readable, may contain spaces. Falls back to `name`. Requires Claude Code v2.1.143+.                          |
| `version`        | string  | Semver. **Setting it pins the plugin** — users only get updates when you bump it. Omit to version by git commit SHA. |
| `description`    | string  |                                                                                                                     |
| `author`         | object  | `{ name, email?, url? }`                                                                                            |
| `homepage`       | string  |                                                                                                                     |
| `repository`     | string  |                                                                                                                     |
| `license`        | string  | SPDX identifier                                                                                                     |
| `keywords`       | array   |                                                                                                                     |
| `defaultEnabled` | boolean | Default `true`. `false` installs the plugin disabled. Requires v2.1.154+.                                            |

## Component paths

All paths are relative to the plugin root and **must start with `./`**.

| Field                    | Type                  | Replaces or adds to the default?                       |
| :----------------------- | :-------------------- | :------------------------------------------------------ |
| `skills`                 | string\|array         | **Adds** to the default `skills/` scan                  |
| `commands`               | string\|array         | Replaces default `commands/`                            |
| `agents`                 | string\|array         | Replaces default `agents/`                              |
| `outputStyles`           | string\|array         | Replaces default `output-styles/`                       |
| `hooks`                  | string\|array\|object | Own merge rules                                         |
| `mcpServers`             | string\|array\|object | Own merge rules                                         |
| `lspServers`             | string\|array\|object | Own merge rules                                         |
| `experimental.themes`    | string\|array         | Replaces default `themes/`                              |
| `experimental.monitors`  | string\|array         | Replaces default `monitors/monitors.json`               |
| `userConfig`             | object                | Values prompted at enable time                          |
| `channels`               | array                 | Message channels bound to a bundled MCP server          |
| `dependencies`           | array                 | Other plugins required, optionally with semver ranges   |

Unrecognized top-level fields are ignored at load time and reported as warnings by
`claude plugin validate`. Wrong types are hard errors. Use `--strict` in CI.

## Default component locations

| Component     | Location                  |
| :------------ | :------------------------ |
| Manifest      | `.claude-plugin/plugin.json` |
| Skills        | `skills/<name>/SKILL.md`  |
| Commands      | `commands/*.md`           |
| Agents        | `agents/*.md`             |
| Output styles | `output-styles/`          |
| Themes        | `themes/`                 |
| Hooks         | `hooks/hooks.json`        |
| MCP servers   | `.mcp.json`               |
| LSP servers   | `.lsp.json`               |
| Monitors      | `monitors/monitors.json`  |
| Executables   | `bin/` (added to the Bash tool `PATH`) |
| Settings      | `settings.json` (only `agent` and `subagentStatusLine` keys) |

A `CLAUDE.md` at the plugin root is **not** loaded as context. Ship instructions
as a skill instead.

## Path variables

Substituted in skill and agent content, hook commands, monitor commands, and
MCP/LSP configs; also exported to subprocesses.

| Variable                 | Points to                                                              |
| :----------------------- | :---------------------------------------------------------------------- |
| `${CLAUDE_PLUGIN_ROOT}`  | The plugin's install directory. **Changes on every update — no state here.** |
| `${CLAUDE_PLUGIN_DATA}`  | Persistent directory that survives updates. Put `node_modules`, venvs, caches here. |
| `${CLAUDE_PROJECT_DIR}`  | The project root                                                        |

Quote them in shell-form commands: `"${CLAUDE_PLUGIN_ROOT}"/scripts/x.sh`.

## Versioning

The version is resolved from the first of these that is set:

1. `version` in `plugin.json`
2. `version` in the marketplace entry
3. The git commit SHA of the source
4. `unknown`

If you set `version`, **you must bump it for users to receive changes.** Pushing
commits alone does nothing. Leave it unset while iterating fast.

## Installed plugins cannot escape their directory

Marketplace plugins are copied into `~/.claude/plugins/cache`. Paths that traverse
outside the plugin root (`../shared`) break after install. To share files inside
one marketplace, use a symlink: links resolving elsewhere in the same marketplace
are dereferenced into the cache; links outside the marketplace are skipped.
