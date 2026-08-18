---
name: triage-inbox
description: Read and act on a mailbox with the emails-for-claude CLI — list and search messages server-side, read one without marking it seen, save attachments, and flag, move or delete in bulk. Use when asked to check email, summarise an inbox, find messages from someone or about something, catch up on unread mail, clean up or archive a mailbox, or pull a file out of an attachment.
license: GPL-3.0-or-later
compatibility: Requires the claudeforanything CLI on PATH and an account already connected (see emails-for-claude:connect-account). Full functionality needs IMAP; POP3 accounts have no folders, flags, or server-side search.
---

# Triage a mailbox

## When to use this

- "Check my email", "what's new", "anything from Marie?"
- "Summarise my unread mail from this week."
- "Find the invoice from the accountant and save the PDF."
- "Archive everything from that newsletter."

For sending or replying, use `emails-for-claude:send-mail`. For a mailbox that is
not connected yet, use `emails-for-claude:connect-account`.

## The shape of the work

Always the same four moves, in this order:

1. **Narrow on the server** with `inbox` or `search` filters.
2. **Read** only the messages that matter.
3. **Report** to the user in prose, not raw JSON.
4. **Act** — flag, move, delete — and only after the user has agreed.

Never fetch a whole mailbox to filter it locally. Every filter below maps onto
IMAP SEARCH and runs on the server, so `--from` across 50,000 messages costs one
round trip.

## Step 1 — Narrow

```bash
claudeforanything emails-for-claude inbox --json
```

Filters, all combinable:

| Flag | Matches |
| :--- | :------ |
| `--unseen` / `--seen` | Unread / read |
| `--flagged` / `--answered` | Starred / replied to |
| `--from <x>` / `--to <x>` | The From / To header |
| `--subject <x>` | The Subject |
| `--search <x>` | Headers **and** body |
| `--body <x>` | Body only |
| `--since <YYYY-MM-DD>` / `--before <YYYY-MM-DD>` | Date window |
| `--larger <bytes>` | Size |
| `--has-attachment` | Approximate — matches `multipart/mixed` only |
| `--query '<raw>'` | A raw IMAP expression, appended as-is |

Plus `--folder`, `--limit` (default 25), `--offset`, and `--oldest`.

```bash
# What arrived today that I have not read
claudeforanything emails-for-claude inbox --unseen --since 2026-08-18 --json

# Everything from one sender in a specific folder
claudeforanything emails-for-claude inbox --folder Archive --from marie@example.com -n 50 --json
```

Folder names are case-sensitive and provider-specific — `[Gmail]/All Mail`,
`Éléments envoyés`, `INBOX.Sent`. Run `folders` once and use the exact names it
prints rather than assuming.

For anything IMAP can express but these flags cannot, use `--query`. The cookbook
is in `${CLAUDE_PLUGIN_ROOT}/references/imap-search.md`.

## Step 2 — Read

```bash
claudeforanything emails-for-claude read <uid> --json
```

Reading does **not** mark the message seen. That is deliberate: looking at
someone's inbox on their behalf must not change what they see in their own
client. Pass `--mark-seen` only when the user asked for it.

- `--max-chars N` bounds the body. The default is 20000; lower it when scanning
  many messages, raise it when the user needs the whole thing.
- HTML-only messages are stripped to readable text automatically;
  `.data.body_source` tells you which body you got.
- `--format raw` prints the original RFC 5322 bytes, for header forensics.

Batch reading is a shell loop, not a special command:

```bash
for uid in $(claudeforanything emails-for-claude search --unseen -n 10); do
  claudeforanything emails-for-claude read "$uid" --max-chars 2000 --json
done
```

`search` prints bare UIDs precisely so this works.

## Step 3 — Attachments

```bash
claudeforanything emails-for-claude attachments <uid> --json
claudeforanything emails-for-claude attachments <uid> --save ./downloads --json
claudeforanything emails-for-claude attachments <uid> --save ./downloads --only 2
```

`--only` takes the index from the listing or the exact filename. Filenames are
attacker-controlled, so only the basename is ever used — an attachment named
`../../.bashrc` lands in the target directory as `.bashrc`. Still choose a
scratch directory rather than a directory that matters.

## Step 4 — Report

Summarise in prose. Lead with what the user cares about: who wrote, what they
want, whether it needs an answer. Give UIDs so the next command is obvious, but
do not paste raw JSON at the user.

## Step 5 — Act, after agreeing

```bash
# Mark read / unread, star / unstar, or set any server flag
claudeforanything emails-for-claude flag 101 102 --read
claudeforanything emails-for-claude flag 101 --star
claudeforanything emails-for-claude flag 101 --add '\Answered'

# Move, creating the destination if needed
claudeforanything emails-for-claude move 101 102 --to Archive --create

# Delete: goes to Trash, recoverable
claudeforanything emails-for-claude delete 101

# Erase for good: irreversible, so it demands --yes
claudeforanything emails-for-claude delete 101 --purge --yes
```

Bulk operations compose:

```bash
claudeforanything emails-for-claude search --from newsletter@example.com \
  | xargs claudeforanything emails-for-claude move --to Archive
```

**Confirm before destroying anything.** `delete` without `--purge` is recoverable
from Trash and is a reasonable default. `--purge --yes` is not recoverable — say
how many messages and from where, and get an explicit yes. The same goes for a
bulk `move` over a search that matched more than the user expected: report the
match count first, act second.

## POP3 accounts

If `.data.protocol` is `pop3`, tell the user what is missing rather than working
around it silently: one mailbox, no flags, no server-side search (filters are
ignored), no move, and deletion is immediate and permanent. Listing is also slow,
because every summary is a separate round trip. Suggest switching the account to
IMAP if the provider offers it.

## Notes

- Raw IMAP search cookbook: `${CLAUDE_PLUGIN_ROOT}/references/imap-search.md`
- When something fails: `${CLAUDE_PLUGIN_ROOT}/references/troubleshooting.md`
