# Standalone skills

Skills for general tasks that need no plugin behind them.

Plain Agent Skills, compliant with <https://agentskills.io/specification>. They are
publishable on their own and portable to any agent that implements the spec, so
keep Claude-Code-only constructs out of them and declare any environment
requirements in the `compatibility:` frontmatter field.

```
skills/<skill-name>/
├── SKILL.md      # required
├── references/   # optional
├── scripts/      # optional
└── assets/       # optional
```

To make one installable from this marketplace, add a catalog entry in
`../../.claude-plugin/marketplace.json` — at the repository root — pointing
straight at the skill directory:

```json
{
  "name": "<skill-name>",
  "source": "./marketplace/skills/<skill-name>"
}
```

A directory with a `SKILL.md` at its root, no `skills/` subdirectory, and no
`skills` manifest field is loaded as a single-skill plugin, so no `plugin.json` is
needed. The invocation name comes from the frontmatter `name`, not the install
directory, which is why that field is required to match the directory name.

Pointing an entry at the marketplace root instead (`"source": "./"`) would also
work, but it copies the entire repository into every user's plugin cache. Use the
per-skill source above.

Use the `claude-for-plugin-authoring:new-skill` skill to write one.
