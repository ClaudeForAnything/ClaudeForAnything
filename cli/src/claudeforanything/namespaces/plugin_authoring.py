"""`claudeforanything claude-for-plugin-authoring` — author and check marketplace content."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Annotated

import typer

from ..naming import check_plugin_name, check_skill_name
from ..output import CliError, JsonOption, emit, fail
from ..paths import (
    CONTENT_DIR,
    catalog_path,
    find_root,
    plugin_source,
    plugins_dir,
    skills_dir,
)
from ..templates import plugin_json, plugin_readme, skill_md

app = typer.Typer(
    no_args_is_help=True,
    help="Author, scaffold, and check ClaudeForAnything plugins and Agent Skills.",
)

RootOption = Annotated[
    Path | None,
    typer.Option(
        "--root",
        help="Marketplace root. Defaults to the nearest ancestor holding "
        ".claude-plugin/marketplace.json.",
    ),
]

ForceOption = Annotated[
    bool, typer.Option("--force", help="Overwrite files that already exist.")
]


def _write(path: Path, content: str, *, force: bool, written: list[str]) -> None:
    if path.exists() and not force:
        raise CliError(f"{path} already exists (pass --force to overwrite)", code="exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    written.append(str(path))


@app.command("new-plugin")
def new_plugin(
    name: Annotated[str, typer.Argument(help="Plugin name, e.g. crm-for-claude.")],
    description: Annotated[
        str, typer.Option("--description", help="What it does and when to use it.")
    ],
    with_: Annotated[
        list[str] | None,
        typer.Option(
            "--with",
            help="Extra component folders: skills, agents, hooks, mcp.",
        ),
    ] = None,
    root: RootOption = None,
    force: ForceOption = False,
    as_json: JsonOption = False,
) -> None:
    """Scaffold a new plugin under marketplace/plugins/."""
    try:
        problems = check_plugin_name(name)
        if problems:
            raise CliError("; ".join(problems), code="invalid_name")

        valid = {"skills", "agents", "hooks", "mcp"}
        components = with_ or []
        if unknown := sorted(set(components) - valid):
            raise CliError(
                f"unknown --with value(s): {', '.join(unknown)}. "
                f"Valid: {', '.join(sorted(valid))}",
                code="invalid_component",
            )

        resolved = find_root(root)
        plugin_dir = plugins_dir(resolved) / name
        written: list[str] = []

        _write(
            plugin_dir / ".claude-plugin" / "plugin.json",
            plugin_json(name, description),
            force=force,
            written=written,
        )
        _write(
            plugin_dir / "README.md",
            plugin_readme(name, description),
            force=force,
            written=written,
        )
        if "skills" in components or not components:
            _write(
                plugin_dir / "skills" / "example" / "SKILL.md",
                skill_md("example", f"Placeholder skill for {name}. Replace it."),
                force=force,
                written=written,
            )
        if "agents" in components:
            (plugin_dir / "agents").mkdir(parents=True, exist_ok=True)
        if "hooks" in components:
            _write(
                plugin_dir / "hooks" / "hooks.json",
                json.dumps({"hooks": {}}, indent=2) + "\n",
                force=force,
                written=written,
            )
        if "mcp" in components:
            _write(
                plugin_dir / ".mcp.json",
                json.dumps({"mcpServers": {}}, indent=2) + "\n",
                force=force,
                written=written,
            )

        source = plugin_source(name)
        entry = {"name": name, "source": source}
        emit(
            {
                "plugin": name,
                "directory": str(plugin_dir),
                "written": written,
                "catalog": {"path": str(catalog_path(resolved)), "entry": entry},
            },
            [
                *(f"wrote {p}" for p in written),
                "",
                f"Next: register {name} in {catalog_path(resolved)}",
                f'  {json.dumps(entry)}',
                "Then: claude plugin validate . --strict",
            ],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@app.command("new-skill")
def new_skill(
    name: Annotated[str, typer.Argument(help="Skill name, matching its directory.")],
    description: Annotated[
        str, typer.Option("--description", help="What it does and when to use it.")
    ],
    plugin: Annotated[
        str | None,
        typer.Option("--plugin", help="Owning plugin. Omit for a standalone skill."),
    ] = None,
    root: RootOption = None,
    force: ForceOption = False,
    as_json: JsonOption = False,
) -> None:
    """Scaffold an Agent Skill, inside a plugin or standalone."""
    try:
        problems = check_skill_name(name)
        if problems:
            raise CliError("; ".join(problems), code="invalid_name")

        resolved = find_root(root)
        if plugin:
            base = plugins_dir(resolved) / plugin
            if not base.is_dir():
                raise CliError(f"no such plugin: {base}", code="plugin_not_found")
            target = base / "skills" / name
        else:
            target = skills_dir(resolved) / name

        written: list[str] = []
        _write(target / "SKILL.md", skill_md(name, description), force=force, written=written)

        emit(
            {"skill": name, "plugin": plugin, "directory": str(target), "written": written},
            [f"wrote {p}" for p in written],
            as_json=as_json,
        )
    except CliError as error:
        fail(error, as_json=as_json)


@app.command("check")
def check(root: RootOption = None, as_json: JsonOption = False) -> None:
    """Check the marketplace against the naming and structure conventions."""
    try:
        resolved = find_root(root)
        catalog = json.loads(catalog_path(resolved).read_text(encoding="utf-8"))
        listed = {entry["name"] for entry in catalog.get("plugins", [])}

        plugins = plugins_dir(resolved)
        on_disk = {p.name for p in plugins.iterdir() if p.is_dir()} if plugins.is_dir() else set()

        failures: list[dict[str, str]] = []
        warnings: list[dict[str, str]] = []

        for name in sorted(on_disk):
            for problem in check_plugin_name(name):
                failures.append({"kind": "naming", "target": name, "message": problem})
            if not (plugins / name / ".claude-plugin" / "plugin.json").is_file():
                failures.append(
                    {
                        "kind": "manifest",
                        "target": name,
                        "message": "missing .claude-plugin/plugin.json",
                    }
                )

        for name in sorted(on_disk - listed):
            failures.append(
                {
                    "kind": "catalog",
                    "target": name,
                    "message": "on disk but not listed in marketplace.json",
                }
            )
        for name in sorted(listed - on_disk):
            warnings.append(
                {
                    "kind": "catalog",
                    "target": name,
                    "message": f"listed in marketplace.json but not under {CONTENT_DIR}/plugins/",
                }
            )

        # Scoped to CONTENT_DIR on purpose: the marketplace root is the repository
        # root, and an unscoped glob would walk vendor/ and vendor_docs/.
        for path in sorted((resolved / CONTENT_DIR).glob("**/SKILL.md")):
            text = path.read_text(encoding="utf-8")
            target = str(path)
            match = re.search(r"^name:\s*(\S+)\s*$", text, re.MULTILINE)
            if not match:
                failures.append(
                    {"kind": "skill", "target": target, "message": "no `name:` in frontmatter"}
                )
                continue
            if match.group(1) != path.parent.name:
                failures.append(
                    {
                        "kind": "skill",
                        "target": target,
                        "message": f"frontmatter name {match.group(1)!r} does not match "
                        f"directory {path.parent.name!r}",
                    }
                )
            if not re.search(r"^description:\s*\S", text, re.MULTILINE):
                failures.append(
                    {
                        "kind": "skill",
                        "target": target,
                        "message": "no `description:` in frontmatter",
                    }
                )

        lines = [f"FAIL {f['kind']:<9}{f['target']}: {f['message']}" for f in failures]
        lines += [f"WARN {w['kind']:<9}{w['target']}: {w['message']}" for w in warnings]
        lines.append(f"\n{len(failures)} problem(s)" if failures else "all checks passed")

        emit(
            {
                # Distinct from the envelope's `ok`, which reports only that the
                # command ran. This reports whether the marketplace is clean.
                "passed": not failures,
                "root": str(resolved),
                "failures": failures,
                "warnings": warnings,
            },
            lines,
            as_json=as_json,
        )
        if failures:
            raise typer.Exit(1)
    except CliError as error:
        fail(error, as_json=as_json)
