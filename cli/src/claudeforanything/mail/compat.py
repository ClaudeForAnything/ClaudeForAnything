# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Address parsing that behaves the same on every Python this package supports.

`email.utils.getaddresses()` and `parseaddr()` grew a `strict` keyword in
**3.12.6** (the CVE-2023-27043 fix), not in 3.12.0. `pyproject.toml` declares
`requires-python = ">=3.12"`, so passing `strict=` unguarded raises `TypeError`
on 3.12.0 through 3.12.5 — and because `message.addresses()` catches broad
exceptions to survive malformed mail, that `TypeError` would be swallowed and
every From/To/Cc line would silently come back empty.

The shim resolves it in the honest direction: lenient parsing is what this
package wants everywhere, and lenient is exactly what the pre-3.12.6 functions
do with no keyword at all. So the fallback is not an approximation, it is the
same behaviour reached by a different call.

Lenient is the right default here because inbound mail is malformed constantly
and a header this package cannot parse is a header the user cannot read. It is
*not* sufficient on its own for outbound recipients — `strict=False` happily
turns `a@x.com <b@evil.com>` into two addresses — so `smtp.py` validates every
parsed addr-spec separately rather than trusting the parse.
"""

from __future__ import annotations

from email.utils import getaddresses as _getaddresses
from email.utils import parseaddr as _parseaddr
from typing import Sequence


def _detect_strict_support() -> bool:
    try:
        _getaddresses([""], strict=False)
    except TypeError:
        return False
    return True


#: True on Python >= 3.12.6, where `strict` exists. Computed once at import.
SUPPORTS_STRICT = _detect_strict_support()


def get_addresses(fieldvalues: Sequence[str]) -> list[tuple[str, str]]:
    """`getaddresses()` in lenient mode, on any supported Python."""
    if SUPPORTS_STRICT:
        return _getaddresses(list(fieldvalues), strict=False)
    return _getaddresses(list(fieldvalues))


def parse_address(value: str) -> tuple[str, str]:
    """`parseaddr()` in lenient mode, on any supported Python."""
    if SUPPORTS_STRICT:
        return _parseaddr(value, strict=False)
    return _parseaddr(value)
