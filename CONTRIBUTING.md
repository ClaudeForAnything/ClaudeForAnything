# Contributing to ClaudeForAnything

Thanks for wanting to help. This document covers what belongs here, the three
rules everything follows, and the checks a change has to pass.

## What belongs here

| Contribution | Where it goes |
| :----------- | :------------ |
| A plugin — Claude gains a capability | `marketplace/plugins/<name>/` |
| A skill for a general task, needing no plugin | `marketplace/skills/<name>/` |
| A CLI command backing a plugin | `cli/src/claudeforanything/namespaces/` |

Before building something large, open an issue describing it. Direction is
decided by the project lead (see [GOVERNANCE.md](GOVERNANCE.md)), and it is
kinder to find out early than after a weekend of work.

## The three rules

Everything in this repository follows these. A change that breaks one will be
sent back, so it is worth reading them before you start.

### 1. Name the action, not the product

| The plugin is... | Pattern | Example |
| :--------------- | :------ | :------ |
| Claude **doing an action** | `claude-for-{action}` | `claude-for-photo-editing` |
| **A tool Claude uses** | `{tool}-for-claude` | `crm-for-claude` |

`claude-for-photoshop` is wrong. Photoshop is a product; the action is photo
editing. This one is easy to get wrong and expensive to fix later, because the
name is public the moment someone installs the plugin.

### 2. CLI first, tool second

Every capability ships as a `claudeforanything` subcommand **before** it is
exposed to Claude as an MCP tool:

```bash
claudeforanything <plugin-name> --help
claudeforanything <plugin-name> <verb> --json
```

Claude composes shell commands far better than it composes tool calls. A CLI
gives pipes, loops, and `--help` discovery for free; an MCP tool gives none of
that.

Every command must accept `--json` and emit the standard envelope:

```json
{"ok": true,  "data": {}}
{"ok": false, "error": {"code": "", "message": ""}}
```

Successes and failures share the shape so a caller can branch on `.ok` without
knowing which command produced the document. Without `--json`, errors go to
stderr and stdout stays empty, so piping is safe either way.

### 3. Everything as a skill

Every plugin, tool, and MCP server ships at least one skill compliant with the
[Agent Skills specification](https://agentskills.io/specification). The CLI
carries the *what*; the skill carries the *how*.

Keep `SKILL.md` to the procedure and push schemas, long tables, and worked
examples into `references/`. The `description` field is the highest-leverage
line you will write: it is the only part loaded into every session, and it
decides whether the skill fires at all.

## Setting up

```bash
git clone https://github.com/ClaudeForAnything/ClaudeForAnything
cd ClaudeForAnything/cli
uv sync
uv run pytest
```

Put the CLI on your PATH so the authoring commands work from the repo root:

```bash
uv tool install ./cli
```

## Making a change

Use the tooling — it encodes the conventions so you do not have to memorise them:

```bash
claudeforanything claude-for-plugin-authoring new-plugin <name> --description "..."
claudeforanything claude-for-plugin-authoring new-skill <name> --plugin <name> --description "..."
```

Then register the plugin in `.claude-plugin/marketplace.json` at the repository
root. Note that the marketplace root is the repository root, not `marketplace/`,
so sources read `./marketplace/plugins/<name>`.

If you have Claude Code, installing `claude-for-plugin-authoring` gives you the
`new-plugin`, `new-skill`, and `review-plugin` skills, which walk the whole
procedure.

## Checks your change must pass

```bash
claudeforanything claude-for-plugin-authoring check   # conventions and structure
claude plugin validate . --strict                     # schemas and manifests
cd cli && uv run pytest                               # the CLI test suite
```

The first two cover different ground and you need both. `check` catches the
ClaudeForAnything rules — naming, plugins on disk missing from the catalog,
`SKILL.md` frontmatter names not matching their directories. `claude plugin
validate --strict` catches schema errors and manifest fields that are a
character off from a real one, which would otherwise be ignored silently at
load time.

Machine-readable, if you are scripting it:

```bash
claudeforanything claude-for-plugin-authoring check --json | jq -e '.data.passed'
```

### Bump the version when you change a plugin

A plugin with a pinned `version` only reaches users when that version changes.
Pushing commits alone does nothing — Claude Code sees the same version string
and keeps its cached copy. If you change a plugin, bump `version` in **both**
its `plugin.json` and its catalog entry.

## Sign your commits: the DCO

This project uses the Developer Certificate of Origin. There is no CLA and no
paperwork — you keep the copyright in what you write. You just certify that you
have the right to submit it, by adding a `Signed-off-by` line:

```bash
git commit -s -m "Your message"
```

which appends:

```
Signed-off-by: Your Name <your.email@example.com>
```

Use your real name and an address you can be reached at. By signing off you
certify the following:

```
Developer Certificate of Origin
Version 1.1

Copyright (C) 2004, 2006 The Linux Foundation and its contributors.

Everyone is permitted to copy and distribute verbatim copies of this
license document, but changing it is not allowed.


Developer's Certificate of Origin 1.1

By making a contribution to this project, I certify that:

(a) The contribution was created in whole or in part by me and I
    have the right to submit it under the open source license
    indicated in the file; or

(b) The contribution is based upon previous work that, to the best
    of my knowledge, is covered under an appropriate open source
    license and I have the right under that license to submit that
    work with modifications, whether created in whole or in part
    by me, under the same open source license (unless I am
    permitted to submit under a different license), as indicated
    in the file; or

(c) The contribution was provided directly to me by some other
    person who certified (a), (b) or (c) and I have not modified
    it.

(d) I understand and agree that this project and the contribution
    are public and that a record of the contribution (including all
    personal information I submit with it, including my sign-off) is
    maintained indefinitely and may be redistributed consistent with
    this project or the open source license(s) involved.
```

## Licence

Contributions are licensed under
[GPL-3.0-or-later](LICENSE), the same terms as the project. You retain your
copyright; the DCO records that you had the right to submit the work under
those terms.

Because there is no CLA, the project cannot be relicensed without the agreement
of everyone who has contributed. That is deliberate: it means no one, including
the project lead, can quietly move your work to different terms.

## Pull requests

- One logical change per pull request.
- Explain **why** in the description, not just what — the diff already says what.
- Say what you verified, and paste the output if a check is involved.
- Update the docs your change makes wrong. A stale `SKILL.md` teaches the next
  contributor the wrong thing.
- Do not commit anything under `vendor/` or `vendor_docs/`; both are gitignored
  local caches.

## Reporting problems

Open an issue with what you ran, what you expected, and what happened. For the
CLI, include the `--json` output — it names the error code, which is faster to
act on than prose.
