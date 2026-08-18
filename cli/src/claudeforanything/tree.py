# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Directory tree rendering.

This exists because `eza --tree` writes its listing to the Windows console
handle rather than to stdout, so the output vanishes the moment it is piped or
captured — which is exactly what an agent does. `tree` is not shipped with Git
for Windows either. Rather than add a third-party dependency that might have the
same problem, the capability lives here.

Two Windows details this has to survive, both of which bite any tool:

- Box-drawing characters cannot encode to cp1252, the default stdout encoding.
  Handled centrally by forcing UTF-8 on stdout; `--ascii` is the fallback.
- Ignored directories must not be descended into. `vendor_docs/` alone is 6,000
  files, so honouring .gitignore is a correctness matter, not a nicety.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

#: Never shown, at any depth, gitignored or not. Descending into .git produces
#: hundreds of entries that are never what anybody wanted to see.
ALWAYS_SKIP = {".git"}

CONNECTORS = {
    True: {"branch": "├── ", "last": "└── ", "pipe": "│   ", "gap": "    "},
    False: {"branch": "|-- ", "last": "`-- ", "pipe": "|   ", "gap": "    "},
}


def batch_ignored(root: Path, paths: list[Path]) -> set[Path]:
    """Return the subset of `paths` that git ignores, in one subprocess call.

    Returns an empty set when git is unavailable or `root` is not a work tree,
    so the tree still renders outside a repository.
    """
    if not paths:
        return set()

    by_rel = {p.relative_to(root).as_posix(): p for p in paths}

    # NUL-separated, in binary mode, deliberately. With text=True Python opens
    # the pipe in universal-newlines mode, so on Windows every "\n" separator is
    # written as "\r\n" and git sees paths ending in a stray "\r" that match
    # nothing. Only the final path, having no separator after it, survived —
    # which looks like "gitignore mostly works" rather than an outright failure.
    # -z also makes this correct for paths containing newlines.
    payload = b"\0".join(rel.encode("utf-8") for rel in by_rel) + b"\0"
    try:
        proc = subprocess.run(
            ["git", "check-ignore", "-z", "--stdin"],
            input=payload,
            capture_output=True,
            cwd=root,
            check=False,
        )
    except (OSError, ValueError):
        return set()

    # 0 = at least one ignored, 1 = none ignored. Anything else (128: not a
    # repository, git missing) means we cannot tell, so ignore nothing.
    if proc.returncode not in (0, 1):
        return set()

    reported = proc.stdout.decode("utf-8", "replace").split("\0")
    return {by_rel[rel] for rel in reported if rel in by_rel}


def build(
    root: Path,
    *,
    depth: int,
    show_hidden: bool = True,
    use_gitignore: bool = True,
    label: str = ".",
) -> dict[str, Any]:
    """Build the tree as a nested dict, breadth-first.

    Breadth-first so that gitignore checks batch one subprocess call per level
    rather than one per directory.
    """
    node: dict[str, Any] = {"name": label, "type": "directory", "children": []}
    frontier: list[tuple[Path, dict[str, Any]]] = [(root, node)]

    for _ in range(depth):
        listings: list[tuple[Path, dict[str, Any], list[Path]]] = []
        candidates: list[Path] = []

        for directory, parent in frontier:
            try:
                entries = sorted(directory.iterdir(), key=lambda e: e.name.lower())
            except OSError:
                continue
            entries = [
                e
                for e in entries
                if e.name not in ALWAYS_SKIP
                and (show_hidden or not e.name.startswith("."))
            ]
            listings.append((directory, parent, entries))
            candidates.extend(entries)

        ignored = batch_ignored(root, candidates) if use_gitignore else set()

        next_frontier: list[tuple[Path, dict[str, Any]]] = []
        for _, parent, entries in listings:
            for entry in entries:
                if entry in ignored:
                    continue
                is_dir = entry.is_dir()
                child: dict[str, Any] = {
                    "name": entry.name,
                    "type": "directory" if is_dir else "file",
                }
                if is_dir:
                    child["children"] = []
                    next_frontier.append((entry, child))
                parent["children"].append(child)

        frontier = next_frontier
        if not frontier:
            break

    return node


def render(node: dict[str, Any], *, ascii_only: bool = False) -> list[str]:
    """Render a built tree as display lines, root first."""
    glyphs = CONNECTORS[not ascii_only]
    lines = [node["name"]]

    def walk(current: dict[str, Any], prefix: str) -> None:
        children = current.get("children") or []
        for index, child in enumerate(children):
            last = index == len(children) - 1
            lines.append(f"{prefix}{glyphs['last'] if last else glyphs['branch']}{child['name']}")
            if child.get("children") is not None:
                walk(child, prefix + (glyphs["gap"] if last else glyphs["pipe"]))

    walk(node, "")
    return lines


def count(node: dict[str, Any]) -> dict[str, int]:
    """Count directories and files below the root, excluding the root itself."""
    totals = {"directories": 0, "files": 0}

    def walk(current: dict[str, Any]) -> None:
        for child in current.get("children") or []:
            if child["type"] == "directory":
                totals["directories"] += 1
                walk(child)
            else:
                totals["files"] += 1

    walk(node)
    return totals
