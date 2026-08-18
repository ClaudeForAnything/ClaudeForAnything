# emails-for-claude

Read, search, and send email over IMAP, POP3 and SMTP — with the password in the
OS keyring, never in a config file and never on stdout.

This plugin is a tool Claude uses.

## Install

```bash
claude plugin marketplace add ClaudeForAnything/ClaudeForAnything
claude plugin install emails-for-claude@claudeforanything
```

## CLI

Per the ClaudeForAnything rule, every capability is a `claudeforanything`
subcommand first:

```bash
claudeforanything emails-for-claude --help
```

| Command | What it does |
| :------ | :----------- |
| `parameters [address\|account]` | Report the server settings for an address; `--probe` connects and confirms them |
| `presets` | List providers with built-in settings |
| `account add\|list\|show\|set-password\|set-default\|remove\|test` | Manage accounts and their keyring entries |
| `folders` | List mailboxes, with special-use flags and optional counts |
| `inbox` | List messages, newest first, filtered server-side |
| `search` | The same filters, printing bare UIDs for piping |
| `read <uid>` | Headers, body, and attachment list for one message |
| `attachments <uid>` | List attachments, and write them to disk |
| `send` | Compose and send; `--dry-run` prints the exact bytes and sends nothing |
| `flag <uids...>` | Mark read, unread, starred, or set any server flag |
| `move <uids...> --to <folder>` | Move messages, creating the destination on request |
| `delete <uids...>` | Move to Trash; `--purge --yes` erases permanently |

Every command takes `--json` and returns the standard envelope, so output is
safe to pipe into `jq`:

```bash
claudeforanything emails-for-claude inbox --unseen --json | jq -r '.data.messages[].subject'
claudeforanything emails-for-claude search --from boss@corp.com --since 2026-08-01 \
  | xargs claudeforanything emails-for-claude flag --read
```

### Not implemented yet

`claudeforanything emails-for-claude mcp` — the same surface over MCP — is the
second half of the CLI-first rule and is not written. Everything below works
from a terminal today; nothing here is exposed as an MCP tool.

## Setting up an account

```bash
# 1. Find the servers. --probe connects and reads the greeting.
claudeforanything emails-for-claude parameters you@example.com --probe

# 2. Add the account. Settings come from the provider preset unless overridden.
claudeforanything emails-for-claude account add work --address you@example.com

# 3. Store the password in the OS keyring, read without echo.
claudeforanything emails-for-claude account set-password work

# 4. Confirm both legs log in. Sends nothing.
claudeforanything emails-for-claude account test work
```

Most large providers reject your normal account password over IMAP and SMTP and
require an app-specific password. `parameters` says so per provider, and
`account test` is what tells you which leg is failing and why.

## Where things are kept

| What | Where |
| :--- | :---- |
| Hosts, ports, addresses, TLS mode | `accounts.json` under the user config directory (`$EMAILS_FOR_CLAUDE_HOME` overrides) |
| Passwords | OS keyring, service `emails-for-claude:<account>` — Credential Manager, Keychain, Secret Service, KWallet |
| Headless fallback | `$EMAILS_FOR_CLAUDE_PASSWORD_<ACCOUNT>`, used only when the keyring has nothing |

`accounts.json` never contains a password, and no command prints one. `account
show` reports *where* the password comes from, not what it is.

## Skills

| Skill | What it does |
| :---- | :----------- |
| `connect-account` | Set an account up end to end: discover servers, handle app passwords, store the secret, verify both legs |
| `triage-inbox` | Read and act on a mailbox: search server-side, read without marking seen, flag, move, delete |
| `send-mail` | Compose, show the draft, confirm, send, and file a copy in Sent |

## Under the hood

Standard library only for the protocols — `imaplib`, `poplib`, `smtplib`,
`email` — plus [keyring](https://github.com/jaraco/keyring) for the credential
store. No mail is cached on disk.

IMAP is the supported path and everything works there. POP3 is available for
accounts that offer nothing better, but the protocol has one mailbox, no flags,
no server-side search, and deletion is permanent; the CLI reports those limits
rather than pretending otherwise.
