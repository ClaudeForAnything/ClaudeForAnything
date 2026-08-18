# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""The registry of plugin namespaces exposed by the CLI.

Every plugin in the marketplace gets one namespace here, named exactly as the
plugin is named, so that `claudeforanything <plugin-name> --help` lists what that
plugin can do. Registration is explicit rather than discovered by import magic:
the list is the inventory, and it is greppable.
"""

from __future__ import annotations

import typer

from . import emails_for_claude, plugin_authoring

#: Namespace name -> (Typer app, one-line help). The name must match the plugin
#: name in the marketplace catalog.
NAMESPACES: dict[str, tuple[typer.Typer, str]] = {
    "claude-for-plugin-authoring": (
        plugin_authoring.app,
        "Author, scaffold, and check plugins and Agent Skills.",
    ),
    "emails-for-claude": (
        emails_for_claude.app,
        "Read, search, and send email over IMAP, POP3 and SMTP.",
    ),
}
