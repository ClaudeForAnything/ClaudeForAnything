#!/usr/bin/env python3
"""Scaffold a ClaudeForAnything plugin, a plugin skill, or a standalone skill.

Stdlib only, Python 3.12. Written CLI-first so it lifts into `cli/` unchanged as
`claudeforanything claude-for-plugin-authoring scaffold ...`.

  scaffold.py plugin <name> --description TEXT [--with skills agents hooks mcp]
  scaffold.py skill <name> --description TEXT [--plugin PLUGIN_NAME]
  scaffold.py check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SUMMARY = "Scaffold a ClaudeForAnything plugin, a plugin skill, or a standalone skill."

SKILL_NAME_RE = re.compile(r"^(?!-)(?!.*--)[a-z0-9-]{1,64}(?<!-)$")

ACTION_PREFIX = "claude-for-"
TOOL_SUFFIX = "-for-claude"

# The marketplace root is the repository root, because Claude Code looks for
# .claude-plugin/marketplace.json there when a marketplace is added by owner/repo.
# Plugins and standalone skills live one level down, under CONTENT_DIR.
CONTENT_DIR = "marketplace"


def marketplace_root() -> Path:
    """Walk up from this file to the directory holding .claude-plugin/marketplace.json."""
    for parent in Path(__file__).resolve().parents:
        if (parent / ".claude-plugin" / "marketplace.json").is_file():
            return parent
    raise SystemExit("error: could not locate the marketplace root from this script")


def plugins_dir(root: Path) -> Path:
    return root / CONTENT_DIR / "plugins"


def skills_dir(root: Path) -> Path:
    return root / CONTENT_DIR / "skills"


def check_name(name: str, *, kind: str) -> list[str]:
    """Return naming-convention problems for `name`. Empty list means it is clean."""
    problems: list[str] = []
    if not SKILL_NAME_RE.match(name):
        problems.append(
            f"{name!r}: must be 1-64 chars of a-z, 0-9 and hyphens, "
            "no leading/trailing hyphen, no consecutive hyphens"
        )
    if kind == "plugin":
        is_action = name.startswith(ACTION_PREFIX)
        is_tool = name.endswith(TOOL_SUFFIX)
        if is_action and is_tool:
            problems.append(f"{name!r}: pick one convention, not both")
        elif not is_action and not is_tool:
            problems.append(
                f"{name!r}: plugin names are either 'claude-for-<action>' "
                "(Claude does the action) or '<tool>-for-claude' (a tool Claude uses)"
            )
        elif is_action and not name[len(ACTION_PREFIX):]:
            problems.append(f"{name!r}: missing the action after '{ACTION_PREFIX}'")
    return problems


def write(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force:
        raise SystemExit(f"error: {path} already exists (pass --force to overwrite)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"wrote {path}")


def skill_md(name: str, description: str) -> str:
    return f"""---
name: {name}
description: {description}
license: MIT
---

# {name}

## When to use this

Describe the situations that should trigger this skill. Be concrete.

## Procedure

1. First step.
2. Second step.
3. Third step.

## Notes

Push schemas, long tables, and worked examples into `references/` and link them
here, so they load only when they are needed.
"""


def plugin_json(name: str, description: str) -> str:
    manifest: dict[str, object] = {
        "$schema": "https://json.schemastore.org/claude-code-plugin-manifest.json",
        "name": name,
        "version": "0.1.0",
        "description": description,
        "author": {
            "name": "Emerick @ ClaudeForAnything",
            "email": "emerick@claudeforanything.com",
        },
        "license": "MIT",
        "keywords": [],
    }
    return json.dumps(manifest, indent=2) + "\n"


def plugin_readme(name: str, description: str) -> str:
    kind = (
        "an action Claude performs"
        if name.startswith(ACTION_PREFIX)
        else "a tool Claude uses"
    )
    return f"""# {name}

{description}

This plugin is {kind}.

## CLI

Per the ClaudeForAnything rule, the capability lives in the CLI first:

```bash
claudeforanything {name} --help
claudeforanything {name} mcp     # same surface, over MCP
```

**Status:** the CLI surface for this plugin is not implemented yet.

## Skills

| Skill | What it does |
| :---- | :----------- |
|       |              |

## Install

```bash
claude plugin marketplace add ./marketplace
claude plugin install {name}@claudeforanything
```
"""


def cmd_plugin(args: argparse.Namespace) -> int:
    problems = check_name(args.name, kind="plugin")
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1

    root = marketplace_root()
    plugin_dir = plugins_dir(root) / args.name
    components = args.with_ or []

    write(
        plugin_dir / ".claude-plugin" / "plugin.json",
        plugin_json(args.name, args.description),
        force=args.force,
    )
    write(
        plugin_dir / "README.md",
        plugin_readme(args.name, args.description),
        force=args.force,
    )

    if "skills" in components or not components:
        write(
            plugin_dir / "skills" / "example" / "SKILL.md",
            skill_md("example", f"Placeholder skill for {args.name}. Replace it."),
            force=args.force,
        )
    if "agents" in components:
        (plugin_dir / "agents").mkdir(parents=True, exist_ok=True)
        print(f"created {plugin_dir / 'agents'}")
    if "hooks" in components:
        write(
            plugin_dir / "hooks" / "hooks.json",
            json.dumps({"hooks": {}}, indent=2) + "\n",
            force=args.force,
        )
    if "mcp" in components:
        write(
            plugin_dir / ".mcp.json",
            json.dumps({"mcpServers": {}}, indent=2) + "\n",
            force=args.force,
        )

    catalog = root / ".claude-plugin" / "marketplace.json"
    source = f"./{CONTENT_DIR}/plugins/{args.name}"
    print()
    print(f"Next: register {args.name} in {catalog}")
    print(f'  {{ "name": "{args.name}", "source": "{source}" }}')
    print(f"Then: claude plugin validate {root} --strict")
    return 0


def cmd_skill(args: argparse.Namespace) -> int:
    problems = check_name(args.name, kind="skill")
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1

    root = marketplace_root()
    if args.plugin:
        base = plugins_dir(root) / args.plugin
        if not base.is_dir():
            raise SystemExit(f"error: no such plugin: {base}")
        target = base / "skills" / args.name
    else:
        target = skills_dir(root) / args.name

    write(target / "SKILL.md", skill_md(args.name, args.description), force=args.force)
    return 0


def cmd_check(_args: argparse.Namespace) -> int:
    """Check every plugin and skill against the naming and structure conventions."""
    root = marketplace_root()
    catalog = json.loads((root / ".claude-plugin" / "marketplace.json").read_text("utf-8"))
    listed = {entry["name"] for entry in catalog.get("plugins", [])}
    failures = 0

    plugins = plugins_dir(root)
    on_disk = {p.name for p in plugins.iterdir() if p.is_dir()} if plugins.is_dir() else set()

    for name in sorted(on_disk):
        for problem in check_name(name, kind="plugin"):
            print(f"FAIL naming   {problem}")
            failures += 1
        if not (plugins / name / ".claude-plugin" / "plugin.json").is_file():
            print(f"FAIL manifest {name}: missing .claude-plugin/plugin.json")
            failures += 1

    for name in sorted(on_disk - listed):
        print(f"FAIL catalog  {name}: on disk but not listed in marketplace.json")
        failures += 1
    for name in sorted(listed - on_disk):
        print(
            f"WARN catalog  {name}: listed in marketplace.json "
            f"but not under {CONTENT_DIR}/plugins/"
        )

    # Scoped to CONTENT_DIR on purpose: the marketplace root is the repository
    # root, and globbing it would walk vendor/ and vendor_docs/.
    for path in sorted((root / CONTENT_DIR).glob("**/SKILL.md")):
        text = path.read_text("utf-8")
        dir_name = path.parent.name
        match = re.search(r"^name:\s*(\S+)\s*$", text, re.MULTILINE)
        if not match:
            print(f"FAIL skill    {path}: no `name:` in frontmatter")
            failures += 1
            continue
        if match.group(1) != dir_name:
            print(
                f"FAIL skill    {path}: frontmatter name {match.group(1)!r} "
                f"does not match directory {dir_name!r}"
            )
            failures += 1
        if not re.search(r"^description:\s*\S", text, re.MULTILINE):
            print(f"FAIL skill    {path}: no `description:` in frontmatter")
            failures += 1

    if failures:
        print(f"\n{failures} problem(s)")
        return 1
    print("all checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scaffold", description=SUMMARY)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    sub = parser.add_subparsers(dest="command", required=True)

    p_plugin = sub.add_parser("plugin", help="scaffold a new plugin")
    p_plugin.add_argument("name")
    p_plugin.add_argument("--description", required=True)
    p_plugin.add_argument(
        "--with",
        dest="with_",
        nargs="+",
        choices=["skills", "agents", "hooks", "mcp"],
        help="extra component folders to scaffold",
    )
    p_plugin.set_defaults(func=cmd_plugin)

    p_skill = sub.add_parser("skill", help="scaffold a skill")
    p_skill.add_argument("name")
    p_skill.add_argument("--description", required=True)
    p_skill.add_argument("--plugin", help="owning plugin; omit for a standalone skill")
    p_skill.set_defaults(func=cmd_skill)

    p_check = sub.add_parser("check", help="check the marketplace against the conventions")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
