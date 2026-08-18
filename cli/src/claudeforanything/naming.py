# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ClaudeForAnything naming conventions, as code.

Two conventions, and picking the wrong one is the most common mistake:

    claude-for-<action>   Claude doing an action    claude-for-photo-editing
    <tool>-for-claude     a tool Claude uses        crm-for-claude

Name the action, never the product it replaces. This module can only check the
*shape*; that `claude-for-photoshop` names a product is a judgement call left to
the reviewer, and `review-plugin` says so.
"""

from __future__ import annotations

import re

# Agent Skills spec: 1-64 chars of a-z, 0-9 and hyphens, no leading or trailing
# hyphen, no consecutive hyphens.
NAME_RE = re.compile(r"^(?!-)(?!.*--)[a-z0-9-]{1,64}(?<!-)$")

ACTION_PREFIX = "claude-for-"
TOOL_SUFFIX = "-for-claude"


def check_skill_name(name: str) -> list[str]:
    """Return spec violations for a skill name. Empty list means it is clean."""
    if NAME_RE.match(name):
        return []
    return [
        f"{name!r}: must be 1-64 chars of a-z, 0-9 and hyphens, "
        "no leading/trailing hyphen, no consecutive hyphens"
    ]


def check_plugin_name(name: str) -> list[str]:
    """Return spec and convention violations for a plugin name."""
    problems = check_skill_name(name)

    is_action = name.startswith(ACTION_PREFIX)
    is_tool = name.endswith(TOOL_SUFFIX)

    if is_action and is_tool:
        problems.append(f"{name!r}: pick one convention, not both")
    elif not is_action and not is_tool:
        problems.append(
            f"{name!r}: plugin names are either 'claude-for-<action>' "
            "(Claude does the action) or '<tool>-for-claude' (a tool Claude uses)"
        )
    elif is_action and not name[len(ACTION_PREFIX) :]:
        problems.append(f"{name!r}: missing the action after {ACTION_PREFIX!r}")

    return problems


def plugin_kind(name: str) -> str:
    """Describe which convention a plugin name follows, for generated prose."""
    if name.startswith(ACTION_PREFIX):
        return "an action Claude performs"
    if name.endswith(TOOL_SUFFIX):
        return "a tool Claude uses"
    return "of unclear kind"
