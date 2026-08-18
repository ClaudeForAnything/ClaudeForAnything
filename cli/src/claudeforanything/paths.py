# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Locating the marketplace the CLI is operating on.

The CLI is installed globally, so unlike the script it replaces it cannot find
the marketplace by walking up from its own file. It walks up from the working
directory instead, which is overridable by flag and by environment variable.
"""

from __future__ import annotations

import os
from pathlib import Path

from .output import CliError

# The marketplace root is the repository root, because Claude Code looks for
# .claude-plugin/marketplace.json there when a marketplace is added by
# owner/repo. Plugins and standalone skills live one level down, under this.
CONTENT_DIR = "marketplace"

ROOT_ENV_VAR = "CLAUDEFORANYTHING_ROOT"

CATALOG_RELATIVE = Path(".claude-plugin") / "marketplace.json"


def find_root(start: Path | None = None) -> Path:
    """Return the marketplace root: the nearest ancestor holding the catalog.

    Resolution order: the explicit `start`, then $CLAUDEFORANYTHING_ROOT, then a
    walk up from the working directory.
    """
    if start is not None:
        candidate = start.resolve()
        if not (candidate / CATALOG_RELATIVE).is_file():
            raise CliError(
                f"no {CATALOG_RELATIVE.as_posix()} under {candidate}",
                code="root_not_found",
            )
        return candidate

    env_root = os.environ.get(ROOT_ENV_VAR)
    if env_root:
        return find_root(Path(env_root))

    cwd = Path.cwd().resolve()
    for directory in (cwd, *cwd.parents):
        if (directory / CATALOG_RELATIVE).is_file():
            return directory

    raise CliError(
        f"not inside a ClaudeForAnything marketplace: no {CATALOG_RELATIVE.as_posix()} "
        f"found from {cwd} upward. Pass --root, or set ${ROOT_ENV_VAR}.",
        code="root_not_found",
    )


def catalog_path(root: Path) -> Path:
    return root / CATALOG_RELATIVE


def plugins_dir(root: Path) -> Path:
    return root / CONTENT_DIR / "plugins"


def skills_dir(root: Path) -> Path:
    return root / CONTENT_DIR / "skills"


def plugin_source(name: str) -> str:
    """The catalog `source` value for a plugin, written from the marketplace root."""
    return f"./{CONTENT_DIR}/plugins/{name}"


def skill_source(name: str) -> str:
    """The catalog `source` value for a standalone skill."""
    return f"./{CONTENT_DIR}/skills/{name}"
