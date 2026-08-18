# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""File bodies emitted when scaffolding a plugin or a skill."""

from __future__ import annotations

import json

from .naming import plugin_kind

AUTHOR = {
    "name": "Emerick @ ClaudeForAnything",
    "email": "emerick@claudeforanything.com",
}

PLUGIN_MANIFEST_SCHEMA = "https://json.schemastore.org/claude-code-plugin-manifest.json"


def skill_md(name: str, description: str) -> str:
    return f"""---
name: {name}
description: {description}
license: GPL-3.0-or-later
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
        "$schema": PLUGIN_MANIFEST_SCHEMA,
        "name": name,
        "version": "0.1.0",
        "description": description,
        "author": AUTHOR,
        "license": "GPL-3.0-or-later",
        "keywords": [],
    }
    return json.dumps(manifest, indent=2) + "\n"


def plugin_readme(name: str, description: str) -> str:
    return f"""# {name}

{description}

This plugin is {plugin_kind(name)}.

## CLI

Per the ClaudeForAnything rule, the capability lives in the CLI first:

```bash
claudeforanything {name} --help
claudeforanything {name} <verb> --json
```

**Status:** the CLI surface for this plugin is not implemented yet.

## Skills

| Skill | What it does |
| :---- | :----------- |
|       |              |

## Install

```bash
claude plugin marketplace add ClaudeForAnything/ClaudeForAnything
claude plugin install {name}@claudeforanything
```
"""
