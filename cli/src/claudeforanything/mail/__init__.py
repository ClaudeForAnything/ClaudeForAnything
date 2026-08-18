# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""The mail engine behind `claudeforanything emails-for-claude`.

Stdlib all the way down — `imaplib`, `poplib`, `smtplib`, `email` — with
`keyring` holding the only secret. Nothing in this package imports Typer, so the
engine stays testable without going through the CLI.
"""
