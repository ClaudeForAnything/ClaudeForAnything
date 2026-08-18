"""Output handling shared by every command.

Every command in this CLI accepts `--json`, because Claude composes shell
pipelines far more reliably than it parses prose. Human output is for people;
JSON output is a stable envelope for machines:

    {"ok": true,  "data": {...}}
    {"ok": false, "error": {"code": "...", "message": "..."}}

Errors keep the same shape as successes so a caller can branch on `.ok` without
knowing which command produced the document.
"""

from __future__ import annotations

import json
import sys
from typing import Annotated, Any

import typer

JsonOption = Annotated[
    bool,
    typer.Option(
        "--json",
        help="Emit a JSON document on stdout instead of human-readable text.",
    ),
]


class CliError(Exception):
    """A failure that should be reported in the caller's chosen format.

    Raised by commands instead of calling `typer.Exit` directly, so the top-level
    handler can render it as prose or as the JSON error envelope.
    """

    def __init__(self, message: str, *, code: str = "error", exit_code: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.exit_code = exit_code


def emit(data: Any, lines: list[str], *, as_json: bool) -> None:
    """Write a result as either the JSON envelope or human-readable lines."""
    if as_json:
        json.dump({"ok": True, "data": data}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for line in lines:
            print(line)


def fail(error: CliError, *, as_json: bool) -> None:
    """Write a failure to the appropriate stream and exit non-zero."""
    if as_json:
        payload = {"ok": False, "error": {"code": error.code, "message": error.message}}
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"error: {error.message}", file=sys.stderr)
    raise typer.Exit(error.exit_code)
