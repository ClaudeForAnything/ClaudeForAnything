---
name: send-mail
description: Compose and send email through the emails-for-claude CLI — draft it, show the user the exact message with --dry-run, get approval, send over SMTP, and file a copy in Sent. Use when asked to send, reply to, or forward an email, to write to someone, to send a file by email, or to draft a message for review before it goes out.
license: GPL-3.0-or-later
compatibility: Requires the claudeforanything CLI on PATH and a connected account with a stored password (see emails-for-claude:connect-account). Filing a copy in Sent needs IMAP.
---

# Send email

## When to use this

- "Email Marie the report."
- "Reply to that message and say I'll be there."
- "Draft a message to the client, let me read it first."
- "Send this file to accounting."

## The one rule

**Mail cannot be unsent.** Sending is outward-facing and irreversible: the
recipient's copy exists the moment the SMTP server accepts it, and no later
command can retract it.

So the sequence is always:

1. Compose with `--dry-run`.
2. Show the user the draft.
3. Wait for an explicit yes.
4. Re-run the identical command without `--dry-run`.

Do not skip step 2 because the message seems trivial or because the user said
"just send it" earlier in the conversation about a different message. A single
confirmation covers a single message.

## Step 1 — Compose the draft

```bash
claudeforanything emails-for-claude send \
  --to marie@example.com \
  --subject "Q3 report" \
  --body "Hi Marie,

The report is attached.

Emerick" \
  --attach ./q3.pdf \
  --dry-run --json
```

`--dry-run` **opens no socket** and does not need the password. What it prints
under `.data.message` is the serialized payload — `Bcc` already stripped, CRLF
line endings — flattened exactly as `smtplib` will flatten it.

Check `.data.exact`:

- `true` — the preview is the transmitted payload, byte for byte.
- `false` — an address carries non-ASCII, and `.data.smtputf8` is set. If the
  server advertises SMTPUTF8, it reflattens with a UTF-8 policy, so the real
  bytes may differ. Only the live server knows, so the preview says so instead
  of pretending.

Either way the headers, recipients, body and attachments shown are what would
be sent. `.data.exact` is about byte-level fidelity, not about whether the
preview is trustworthy for review.

Body sources — pass exactly one:

| Flag | Use for |
| :--- | :------ |
| `--body "..."` | Short messages |
| `--body-file <path>` | Anything long, or text you already wrote to disk |
| `--body-stdin` | Piping from another command |

Long bodies are much easier to get right through a file:

```bash
cat > /tmp/draft.txt <<'EOF'
Hi Marie,

...
EOF
claudeforanything emails-for-claude send --to marie@example.com \
  --subject "Q3 report" --body-file /tmp/draft.txt --dry-run --json
```

Recipients: `--to`, `--cc` and `--bcc` are each repeatable and each accept
comma-separated lists, so `--to a@x --to "b@x, c@x"` works. `Bcc` is stripped
from the transmitted headers but still receives — that is the point of it.

One option value that would expand into several recipients **without a comma**
is refused with `ambiguous_address`, because `--to 'a@x.com <b@evil.com>'`
parses as two addresses and only one of them is visible to the person
approving the draft. Semicolons get the same treatment — Outlook users write
`a@x.com;b@y.com`, and it is refused rather than guessed. Use commas, or repeat
the option.

Other options: `--attach` (repeatable), `--html-file` to add an HTML alternative
alongside the plain text, `--reply-to`, and `--header 'Name: value'` for anything
else.

## Step 2 — Show the draft

Show the user, in readable form:

- **From** (the account it will leave from — check it is the one they meant)
- **To**, **Cc**, **Bcc**
- **Subject**
- The **body**, in full
- Each **attachment**, with its filename and size

Then ask whether to send. If they want changes, edit and re-run `--dry-run`; do
not send a version they have not seen.

## Step 3 — Send

Re-run the same command with `--dry-run` removed:

```bash
claudeforanything emails-for-claude send \
  --to marie@example.com --subject "Q3 report" \
  --body-file /tmp/draft.txt --attach ./q3.pdf --json
```

Check the result:

- `.data.accepted` — recipients the server took.
- `.data.refused` — recipients it rejected. Non-empty means **some** copies were
  not delivered; report exactly which, and do not describe the send as clean.
- `.data.saved_to` — the Sent mailbox the copy was filed in.
- `.data.save_error` — filing failed. The message **was still sent**; say so
  plainly rather than implying it failed.

`--no-save-to-sent` skips the filing step.

## Replying

Replying properly means threading, which needs the parent's `Message-ID`:

```bash
# 1. Get it from the message being replied to
claudeforanything emails-for-claude read <uid> --json   # .data.message_id

# 2. Quote it back
claudeforanything emails-for-claude send \
  --to alice@example.com \
  --subject "Re: Quarterly report" \
  --in-reply-to '<abc@example.com>' \
  --body-file /tmp/reply.txt --dry-run --json
```

`--in-reply-to` sets both `In-Reply-To` and `References`, which is what mail
clients actually thread on. Without it the reply arrives as a new conversation.

Reply conventions worth honouring: prefix the subject with `Re: ` unless it is
already there, and reply to the address in `Reply-To` when the message has one —
`read` reports it as `.data.reply_to`.

## Forwarding

There is no `forward` verb. Forward by reading the original and composing a new
message:

```bash
claudeforanything emails-for-claude attachments <uid> --save /tmp/fwd --json
claudeforanything emails-for-claude read <uid> --json > /tmp/original.json
# then compose a body quoting it, and re-attach from /tmp/fwd
```

Say what you are doing — a reconstructed forward is not byte-identical to the
original, and that occasionally matters.

## What not to do

- Do not invent recipients. If the user says "email Marie" and several Maries
  appear in the mailbox, ask which one.
- Do not send to a list the user has not seen. Read every address back first.
- Do not put a password anywhere near these commands. `send` reads it from the
  keyring on its own.
- Do not retry a failed send blindly. `sender_refused` and `login_failed` mean
  the account is misconfigured, not that the network hiccuped — see
  `${CLAUDE_PLUGIN_ROOT}/references/troubleshooting.md`.

## Notes

- Failure modes and error codes: `${CLAUDE_PLUGIN_ROOT}/references/troubleshooting.md`
- Provider quirks that break sending: `${CLAUDE_PLUGIN_ROOT}/references/providers.md`
