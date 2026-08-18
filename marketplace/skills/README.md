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
`../.claude-plugin/marketplace.json` pointing at the marketplace root:

```json
{
  "name": "claude-for-<action>",
  "source": "./",
  "skills": ["./skills/<skill-name>"],
  "strict": false
}
```

Use the `claude-for-plugin-authoring:new-skill` skill to write one.
