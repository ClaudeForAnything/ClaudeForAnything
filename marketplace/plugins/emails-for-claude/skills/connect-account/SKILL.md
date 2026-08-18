---
name: connect-account
description: Connect an email account to Claude over IMAP, POP3 or SMTP — find the right server settings, deal with app-specific passwords, store the credential in the OS keyring, and verify both legs log in. Use when the user wants Claude to access their email, when "emails-for-claude" commands fail with login_failed or no_password, when setting up Gmail, Outlook, iCloud, Fastmail, Proton or a self-hosted mail server, or when asked which host and port an address needs.
license: GPL-3.0-or-later
compatibility: Requires the claudeforanything CLI on PATH (uv tool install ./cli) and outbound network access to the mail servers. Storing a password needs an OS keyring backend, or the documented environment fallback on headless machines.
---

# Connect an email account

## When to use this

- The user asks Claude to read, search, or send their email and no account is set up.
- Any `emails-for-claude` command fails with `no_accounts`, `no_password`, or
  `login_failed`.
- The user asks what IMAP or SMTP settings an address needs.
- An existing account stopped working after a provider changed its auth rules.

## Before you start

The password is the user's, and it is a real secret. Three rules:

1. **Never ask the user to paste a password into the chat.** Have them type it
   into the prompt that `account set-password` opens, or pipe it from their own
   password manager.
2. **Never put a password in a command line.** It lands in shell history and in
   the process table. There is no `--password` flag for this reason.
3. **Never echo one back.** No command prints a password; do not defeat that by
   repeating one the user volunteered.

## Step 1 — Find the servers

```bash
claudeforanything emails-for-claude parameters <address> --json
```

Read `.data.source`:

- `preset` — published settings for a known provider. Use them.
- `guess` — no preset matched, so the hosts are the `imap.<domain>` convention
  and may be wrong. **Confirm before saving**:

```bash
claudeforanything emails-for-claude parameters <address> --probe --json
```

`--probe` opens a socket to each candidate and reports the greeting. A host that
answers with `* OK ... IMAP4rev1` is real. If it does not answer, ask the user
for the settings from their provider's documentation rather than guessing again.

Read `.data.preset.notes` out loud to the user. That field is where the
app-password requirement lives, and skipping it is the single most common cause
of a login failure two steps later.

## Step 2 — Get the right kind of password

Most large providers **reject the normal account password** over IMAP and SMTP.
See `${CLAUDE_PLUGIN_ROOT}/references/providers.md` for the per-provider walk-through.

The short version:

| Provider | What is needed |
| :------- | :------------- |
| Gmail / Workspace | 2-Step Verification on, then an App Password |
| iCloud | App-specific password from the Apple account page |
| Yahoo, AOL, Fastmail, Zoho, Yandex | App password from account security settings |
| Outlook.com, Microsoft 365 | Often OAuth-only; password auth may simply be off |
| Proton | Proton Mail Bridge must be running; use the password Bridge generates |

Tell the user which one applies **before** they go looking for their password.

## Step 3 — Add the account

```bash
claudeforanything emails-for-claude account add <name> --address <address>
```

`<name>` is a short label the user will type later: `work`, `perso`, `gmail`.

Settings come from the preset. Override only what the user actually told you:

```bash
claudeforanything emails-for-claude account add work \
  --address you@example.com \
  --display-name "Your Name" \
  --imap-host mail.example.com --imap-security starttls \
  --smtp-host mail.example.com --smtp-security starttls
```

Useful flags:

- `--protocol pop3` — only when the server offers no IMAP. Read the POP3 caveats
  in `${CLAUDE_PLUGIN_ROOT}/references/troubleshooting.md` first and tell the user.
- `--insecure-tls` — Proton Bridge and self-signed certificates only. It disables
  certificate verification, so say that plainly before using it.
- `--no-set-default` — when adding a second account that should not take over.

## Step 4 — Store the password

```bash
claudeforanything emails-for-claude account set-password <name>
```

This prompts without echo and writes to the OS keyring under service
`emails-for-claude:<name>`.

If the user keeps secrets in a password manager, pipe instead:

```bash
pass show mail/work | claudeforanything emails-for-claude account set-password work --stdin
```

On a headless machine with no keyring backend, the command fails with
`no_keyring_backend`. The documented fallback is an environment variable:

```bash
export EMAILS_FOR_CLAUDE_PASSWORD_WORK='...'
```

Say out loud that this is less safe than the keyring — environment variables are
visible to other processes — and that it is for servers and CI, not laptops.

## Step 5 — Verify

```bash
claudeforanything emails-for-claude account test <name> --json
```

This logs in to both legs and **sends nothing**. Check `.data.passed`.

When a leg fails, the `error` string names the cause. Map it with
`${CLAUDE_PLUGIN_ROOT}/references/troubleshooting.md`; the common ones are:

| Error code | Almost always means |
| :--------- | :------------------ |
| `connection_failed` | Wrong host or port, or the network blocks it |
| `login_failed` | Right host, wrong credential — usually a missing app password |
| `no_password` | Nothing in the keyring for this account yet |
| `no_keyring_backend` | No OS credential store; use the environment fallback |

Fix and re-run `account test` until it passes. Do not move on to reading mail
with a failing account — every later command will fail the same way, more
confusingly.

## Step 6 — Confirm the setup back

Show the user:

```bash
claudeforanything emails-for-claude account show <name>
claudeforanything emails-for-claude folders
```

`folders` proves the account can actually see mailboxes, and gives you the folder
names to use later. Then hand off to `emails-for-claude:triage-inbox` for reading
or `emails-for-claude:send-mail` for sending.

## Notes

- Provider-specific instructions: `${CLAUDE_PLUGIN_ROOT}/references/providers.md`
- Failure modes and error codes: `${CLAUDE_PLUGIN_ROOT}/references/troubleshooting.md`
