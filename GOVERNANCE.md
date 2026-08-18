# Governance

## Who decides

ClaudeForAnything is led by **Emerick** (`contact@claudeforanything.com`), who
has final say on direction, scope, what enters the marketplace, and what gets
merged.

This is a benevolent-dictator model, and it is written down because a project
that pretends to have a committee it does not have wastes everyone's time. If
that changes — if there are people here regularly enough to share the load —
this document changes with it.

## How decisions get made

Discussion happens in the open, in issues and pull requests. Anyone may argue
for or against a change, and a good argument from a first-time contributor
carries the same weight as one from anybody else. When discussion does not
converge, the project lead decides and says why.

Two things follow from that:

- **Disagreement is fine and expected.** Say so plainly in the thread. The
  worst outcome is a bad decision nobody pushed back on.
- **A decision is not permanent.** If it turns out wrong, reopen it with what
  you learned. Reversals are cheap; being stuck with a bad call is not.

## What gets into the marketplace

The catalog is curated, not open enrolment. A plugin is accepted when it:

1. Follows the naming convention — `claude-for-<action>` for something Claude
   does, `<tool>-for-claude` for something Claude uses — and names an action
   rather than a product it replaces.
2. Has a CLI surface under `claudeforanything`, or records the gap in its README
   as debt. The CLI-first rule is not decorative; a plugin reachable only
   through MCP is not finished.
3. Ships at least one skill compliant with the
   [Agent Skills specification](https://agentskills.io/specification).
4. Passes `claudeforanything claude-for-plugin-authoring check` and
   `claude plugin validate . --strict`.
5. Earns the context it costs. Every plugin adds always-on tokens to a user's
   session before it does anything. `claude plugin details <name>` prints that
   figure, and it is a real cost paid by everyone who installs it.

Point 5 is the one most likely to get a well-built plugin turned down. The
catalog is a shared budget, not a shelf.

Plugins can also be removed — if one is broken, unmaintained, or superseded.
Removal uses the `renames` field in the marketplace catalog so existing users
migrate automatically instead of silently breaking.

## Contributors and maintainers

Right now there is one maintainer. Everyone else contributes through pull
requests, which the project lead reviews and merges.

There is no formal path to commit access today, because inventing a promotion
ladder for a project with one person on it would be theatre. If you are
contributing often enough that review is the bottleneck, say so — that is the
signal to revisit this section, and it will be revisited honestly rather than
ignored.

## Licence and relicensing

The project is [GPL-3.0-or-later](LICENSE). Contributions come in under the same
terms, certified by a DCO sign-off — see [CONTRIBUTING.md](CONTRIBUTING.md).

There is **no CLA**. Contributors keep the copyright in their own work, and the
project lead holds no special licence to it beyond GPL-3.0-or-later.

The consequence is deliberate and worth stating plainly: **the project cannot be
relicensed without the agreement of every contributor.** Nobody, the project
lead included, can move contributed work to different terms — no proprietary
fork of this codebase, no quiet dual-licensing. The cost is that a future change
of licence, such as moving to AGPL for network copyleft, gets harder with every
contributor. That trade was made knowingly.

## Security

Report suspected vulnerabilities privately to `contact@claudeforanything.com`
rather than opening a public issue. You will get an acknowledgement, and credit
in the fix unless you would rather not have it.

Note that plugins run with real capability on a user's machine — hooks and MCP
servers execute code, and skills instruct an agent that has tools. Anything
accepted into the catalog is reviewed with that in mind.

## Changing this document

By pull request, like anything else. The project lead decides, in the open.
