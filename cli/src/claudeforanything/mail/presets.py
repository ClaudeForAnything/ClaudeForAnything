# Copyright (C) 2026 Emerick @ ClaudeForAnything
# SPDX-License-Identifier: GPL-3.0-or-later
"""Server settings for the mail providers people actually have accounts on.

`parameters` uses this to answer "what do I type for host and port?" without a
round trip to a support page. Every entry here is a published setting; when a
domain is unknown the resolver falls back to the `imap.<domain>` / `smtp.<domain>`
convention and labels that answer a *guess*, because a wrong host reported as
fact is worse than an honest "probe it".
"""

from __future__ import annotations

from dataclasses import dataclass, field

SSL = "ssl"
STARTTLS = "starttls"
PLAIN = "none"

SECURITY_CHOICES = (SSL, STARTTLS, PLAIN)


@dataclass(frozen=True, slots=True)
class Preset:
    """Published IMAP/POP3/SMTP settings for one provider."""

    key: str
    label: str
    domains: tuple[str, ...]
    imap_host: str
    imap_port: int
    imap_security: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    pop3_host: str | None = None
    pop3_port: int = 995
    pop3_security: str = SSL
    notes: tuple[str, ...] = field(default_factory=tuple)


APP_PASSWORD_NOTE = (
    "This provider rejects your normal account password over IMAP/SMTP. Create "
    "an app-specific password and store that instead."
)

PRESETS: tuple[Preset, ...] = (
    Preset(
        key="gmail",
        label="Gmail / Google Workspace",
        domains=("gmail.com", "googlemail.com"),
        imap_host="imap.gmail.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_security=STARTTLS,
        pop3_host="pop.gmail.com",
        notes=(
            APP_PASSWORD_NOTE,
            "Turn on 2-Step Verification, then create an App Password at "
            "https://myaccount.google.com/apppasswords.",
            "IMAP must also be enabled in Gmail settings, under Forwarding and POP/IMAP.",
        ),
    ),
    Preset(
        key="outlook",
        label="Outlook.com / Hotmail / Live",
        domains=("outlook.com", "hotmail.com", "live.com", "msn.com", "hotmail.fr", "live.fr"),
        imap_host="outlook.office365.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp-mail.outlook.com",
        smtp_port=587,
        smtp_security=STARTTLS,
        pop3_host="outlook.office365.com",
        notes=(
            "Microsoft has been switching personal accounts from password "
            "authentication to OAuth2. If LOGIN fails with a password you know "
            "is right, basic auth is off for that account and this plugin "
            "cannot reach it.",
        ),
    ),
    Preset(
        key="office365",
        label="Microsoft 365 (business)",
        domains=(),
        imap_host="outlook.office365.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.office365.com",
        smtp_port=587,
        smtp_security=STARTTLS,
        notes=(
            "Basic authentication is disabled by default on modern tenants. An "
            "administrator has to re-enable it, or you need an OAuth client.",
        ),
    ),
    Preset(
        key="yahoo",
        label="Yahoo Mail",
        domains=("yahoo.com", "yahoo.fr", "yahoo.co.uk", "ymail.com", "rocketmail.com"),
        imap_host="imap.mail.yahoo.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.mail.yahoo.com",
        smtp_port=465,
        smtp_security=SSL,
        pop3_host="pop.mail.yahoo.com",
        notes=(APP_PASSWORD_NOTE,),
    ),
    Preset(
        key="aol",
        label="AOL Mail",
        domains=("aol.com",),
        imap_host="imap.aol.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.aol.com",
        smtp_port=465,
        smtp_security=SSL,
        pop3_host="pop.aol.com",
        notes=(APP_PASSWORD_NOTE,),
    ),
    Preset(
        key="icloud",
        label="iCloud Mail",
        domains=("icloud.com", "me.com", "mac.com"),
        imap_host="imap.mail.me.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.mail.me.com",
        smtp_port=587,
        smtp_security=STARTTLS,
        notes=(
            APP_PASSWORD_NOTE,
            "Generate one at https://account.apple.com, under Sign-In and Security.",
        ),
    ),
    Preset(
        key="fastmail",
        label="Fastmail",
        domains=("fastmail.com", "fastmail.fm"),
        imap_host="imap.fastmail.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.fastmail.com",
        smtp_port=465,
        smtp_security=SSL,
        pop3_host="pop.fastmail.com",
        notes=(APP_PASSWORD_NOTE,),
    ),
    Preset(
        key="zoho",
        label="Zoho Mail",
        domains=("zoho.com", "zohomail.com"),
        imap_host="imap.zoho.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.zoho.com",
        smtp_port=465,
        smtp_security=SSL,
        pop3_host="pop.zoho.com",
        notes=(APP_PASSWORD_NOTE,),
    ),
    Preset(
        key="yandex",
        label="Yandex Mail",
        domains=("yandex.com", "yandex.ru"),
        imap_host="imap.yandex.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="smtp.yandex.com",
        smtp_port=465,
        smtp_security=SSL,
        pop3_host="pop.yandex.com",
        notes=(APP_PASSWORD_NOTE,),
    ),
    Preset(
        key="gmx",
        label="GMX",
        domains=("gmx.com", "gmx.net", "gmx.de", "gmx.fr"),
        imap_host="imap.gmx.com",
        imap_port=993,
        imap_security=SSL,
        smtp_host="mail.gmx.com",
        smtp_port=587,
        smtp_security=STARTTLS,
        pop3_host="pop.gmx.com",
        notes=("IMAP has to be switched on in the GMX web settings first.",),
    ),
    Preset(
        key="proton-bridge",
        label="Proton Mail (through Proton Mail Bridge)",
        domains=("proton.me", "protonmail.com", "pm.me"),
        imap_host="127.0.0.1",
        imap_port=1143,
        imap_security=STARTTLS,
        smtp_host="127.0.0.1",
        smtp_port=1025,
        smtp_security=STARTTLS,
        notes=(
            "Proton exposes no public IMAP. The Bridge desktop app must be "
            "running and signed in; it shows the real ports and generates its "
            "own password, and that generated password is what you store here.",
            "The Bridge serves a self-signed certificate, so the account needs "
            "--insecure-tls.",
        ),
    ),
)

PRESETS_BY_KEY = {preset.key: preset for preset in PRESETS}

DOMAIN_INDEX = {domain: preset for preset in PRESETS for domain in preset.domains}


def domain_of(address: str) -> str:
    """Return the lowercased domain part of an address, or '' if there is none."""
    _, at, domain = address.strip().rpartition("@")
    return domain.strip().lower() if at else ""


def lookup(address_or_domain: str) -> Preset | None:
    """Return the preset serving this address or domain, if one is known."""
    candidate = address_or_domain.strip().lower()
    if "@" in candidate:
        candidate = domain_of(candidate)
    return DOMAIN_INDEX.get(candidate)


def guess(domain: str) -> Preset:
    """Build the conventional `imap.<domain>` / `smtp.<domain>` answer.

    Returned only when no preset matches, and always reported as a guess by the
    caller. `parameters --probe` is what turns it into a fact.
    """
    domain = domain.strip().lower()
    return Preset(
        key="generic",
        label=f"Convention-based guess for {domain}",
        domains=(domain,),
        imap_host=f"imap.{domain}",
        imap_port=993,
        imap_security=SSL,
        smtp_host=f"smtp.{domain}",
        smtp_port=587,
        smtp_security=STARTTLS,
        pop3_host=f"pop.{domain}",
        notes=(
            "No preset matched this domain, so these are the conventional "
            "names rather than published settings. Confirm with --probe before "
            "saving an account.",
        ),
    )


def resolve(address_or_domain: str) -> tuple[Preset, bool]:
    """Return (preset, known). `known` is False when the answer is a guess."""
    found = lookup(address_or_domain)
    if found is not None:
        return found, True
    domain = domain_of(address_or_domain) or address_or_domain.strip().lower()
    return guess(domain), False
