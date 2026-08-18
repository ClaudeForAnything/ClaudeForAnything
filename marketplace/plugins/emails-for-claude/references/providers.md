# Provider quirks

The built-in settings live in the CLI — `emails-for-claude presets` lists them
and `emails-for-claude parameters <address>` prints the ones for a given domain.
This page covers the part the CLI cannot do for the user: getting a credential
that IMAP and SMTP will actually accept.

## Why the normal password usually fails

Nearly every large provider now refuses the account password on IMAP and SMTP,
because those protocols cannot carry a second factor. They offer one of two
alternatives:

- an **app-specific password** — a long generated string, one per application,
  revocable on its own;
- **OAuth2 only** — no password will ever work, and this plugin cannot help.

`login_failed` on a host that `--probe` reached is nearly always this.

## Gmail and Google Workspace

1. 2-Step Verification must be on: <https://myaccount.google.com/security>.
2. Create an App Password: <https://myaccount.google.com/apppasswords>.
3. Store that, not the account password.
4. IMAP must also be enabled: Gmail → Settings → Forwarding and POP/IMAP.

Workspace administrators can disable app passwords tenant-wide. If the page is
missing, the answer is the admin, not another attempt.

Folder names are unusual: `[Gmail]/All Mail`, `[Gmail]/Sent Mail`,
`[Gmail]/Trash`. Run `folders` and use exactly what it prints. Gmail labels
appear as folders, and a message carrying several labels appears in several of
them — the same UID does not move, it is listed more than once.

## Outlook.com, Hotmail, Live

Microsoft has been turning off basic authentication for personal accounts. The
settings are correct but the login can still be refused because the account
simply no longer accepts a password over IMAP.

If `parameters` reaches the host and `account test` still fails on login, tell
the user this is a provider policy, not a configuration mistake, and that the
options are an OAuth-capable client or a different account.

## Microsoft 365 (business)

Same story, tenant-controlled. `SMTP AUTH` is disabled by default on new
tenants; an administrator can re-enable it per mailbox. Expect
`SMTPAuthenticationError` mentioning that the tenant does not allow it.

## iCloud

App-specific password from <https://account.apple.com> → Sign-In and Security.
The username is the full iCloud address. Custom domains hosted on iCloud Mail
still authenticate with the `@icloud.com` address.

## Yahoo, AOL

App password in Account Security. The regular password has not worked on IMAP
for years.

## Fastmail

App password under Settings → Privacy & Security → Integrations. Fastmail lets
you scope it to mail only, which is worth suggesting.

## Zoho, Yandex

App password in account security settings. Zoho additionally requires IMAP
access to be enabled per mailbox, and the host differs by data centre
(`imap.zoho.eu`, `imap.zoho.in`); if the `.com` host is refused, ask which
region the account is in and override with `--imap-host`.

## Proton Mail

Proton has no public IMAP. Everything goes through **Proton Mail Bridge**, a
desktop app that must be running and signed in.

- The Bridge listens on localhost and shows the exact ports (commonly 1143 for
  IMAP and 1025 for SMTP, both STARTTLS).
- It generates its own password per account. That generated string is what goes
  in the keyring — never the Proton account password.
- The Bridge serves a self-signed certificate, so the account needs
  `--insecure-tls`. Say plainly that this disables certificate verification, and
  that it is acceptable here only because the connection never leaves localhost.

```bash
claudeforanything emails-for-claude account add proton \
  --address you@proton.me --preset proton-bridge --insecure-tls
```

## Self-hosted and small ISPs

No preset will match, so `parameters` returns a labelled guess. Confirm it:

```bash
claudeforanything emails-for-claude parameters you@example.com --probe --json
```

Common shapes when the convention does not hold:

- one host for everything: `mail.example.com`, IMAP 993 SSL, SMTP 587 STARTTLS;
- a cPanel server: `mail.<domain>`, often with a certificate for the *server*
  hostname rather than the mail domain, which fails verification — the fix is
  the correct hostname, not `--insecure-tls`;
- submission on 465 (implicit TLS) instead of 587 (STARTTLS). Try both.

## Two-factor and the environment fallback

An app password bypasses 2FA by design; that is what makes it work here. It also
means the string is as sensitive as the account password. Keep it in the OS
keyring. Use `$EMAILS_FOR_CLAUDE_PASSWORD_<ACCOUNT>` only on machines with no
credential store, and tell the user it is the weaker option.
