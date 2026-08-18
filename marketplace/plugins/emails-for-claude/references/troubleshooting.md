# Troubleshooting

Every failure comes back as the standard envelope with a stable `code`:

```json
{"ok": false, "error": {"code": "login_failed", "message": "..."}}
```

Branch on the code, not on the message text.

## Diagnose in this order

```bash
claudeforanything emails-for-claude account show <name>     # is it configured, and is there a password?
claudeforanything emails-for-claude parameters <name> --probe  # can we reach the hosts at all?
claudeforanything emails-for-claude account test <name> --json # do both legs log in?
```

`account test` separates the three things that look identical from the outside:
wrong host, wrong credential, and provider policy.

## Setup and credentials

| Code | Cause | Fix |
| :--- | :---- | :-- |
| `no_accounts` | Nothing configured | `account add` — see `emails-for-claude:connect-account` |
| `account_not_found` | Typo in `--account` | `account list` |
| `ambiguous_account` | Several accounts, no default | Pass `--account`, or `account set-default` |
| `no_password` | Keyring has nothing for this account | `account set-password <name>` |
| `no_keyring_backend` | No OS credential store (headless Linux, CI) | Install SecretStorage or KWallet, or export `EMAILS_FOR_CLAUDE_PASSWORD_<ACCOUNT>` |
| `keyring_error` | The store refused | Usually a locked keyring — unlock the session and retry |
| `bad_store` / `store_version` | `accounts.json` is corrupt or from a newer CLI | Inspect the path from `account list --json`; it holds no secrets, so it is safe to delete and rebuild |

## Connection

| Code | Cause |
| :--- | :---- |
| `connection_failed` | Wrong host or port, DNS failure, firewall, or TLS handshake refused |
| `login_failed` | Host reached, credential rejected |
| `imap_error` / `pop3_error` / `smtp_error` | The server refused a specific command |
| `imap_aborted` | The connection dropped mid-command |

**`connection_failed`.** Check the host actually answers:

```bash
claudeforanything emails-for-claude parameters <account> --probe --json
```

A real IMAP server greets with `* OK`; POP3 with `+OK`; SMTP with `220`. Silence
or a timeout means wrong port or a blocked outbound connection. A TLS error
usually means the security mode is wrong — port 993/465 want `ssl`, port
143/587 want `starttls`.

**`login_failed`.** Almost always an app-specific password, not a typo. See
`providers.md`. Also check the *username*: some servers want the local part
only, not the full address (`--username` on `account add`).

**Certificate errors.** `certificate verify failed` on a self-hosted server
usually means the certificate is issued for a different hostname — connect to
the name on the certificate rather than reaching for `--insecure-tls`. Reserve
`--insecure-tls` for Proton Bridge and deliberately self-signed local servers.

## Reading

| Code | Cause |
| :--- | :---- |
| `folder_not_found` | Folder name wrong or not selectable | 
| `message_not_found` | UID gone, or from a different folder |
| `not_imap` | An IMAP-only command on a POP3 account |
| `invalid_date` | `--since` / `--before` is not `YYYY-MM-DD` |
| `invalid_format` | `--format` is not text, html, raw or headers |

Folder names are case-sensitive, provider-specific, and often non-English. Run
`folders` and copy the exact string. Container folders such as `[Gmail]` are
marked `"selectable": false` and cannot be opened.

UIDs are per-folder. A UID from `inbox --folder Archive` is meaningless against
`INBOX`, and that is what `message_not_found` usually means. UIDs are stable
within a folder, unlike sequence numbers, which is why every command uses them.

## Sending

| Code | Cause |
| :--- | :---- |
| `no_recipients` | No `--to`, `--cc` or `--bcc` |
| `invalid_address` | A recipient has no `@` |
| `conflicting_body` | More than one of `--body`, `--body-file`, `--body-stdin` |
| `invalid_header` | `--header` is not `Name: value` |
| `recipients_refused` | Every recipient rejected |
| `sender_refused` | The server refused the From address |
| `attachment_not_found` | No such file |

**`sender_refused`** means the envelope sender does not match the authenticated
account. Relays generally insist the two agree; check `--address` on the account
matches the mailbox actually being authenticated.

**Partial refusal is not an error.** If some recipients are accepted and others
rejected, the command succeeds and lists the rejects under `.data.refused`.
Report exactly which addresses did not get it.

**`save_error` is not a send failure.** Filing the copy in Sent happens after
delivery. If it fails, the message *was* sent; `.data.saved_to` is null and
`.data.save_error` explains why. Never report this as a failed send.

## POP3 limits

Not bugs — the protocol has no such feature:

- one mailbox, so `folders` and `--folder` do not apply;
- no flags, so `flag` is unavailable and everything reads as unseen;
- no server-side search, so `inbox` filters are ignored and it says so;
- no move;
- deletion is permanent and takes effect when the session ends, which is why
  `delete` on a POP3 account demands `--yes`;
- listing is one round trip per message, so keep `--limit` small;
- message identity depends on the optional UIDL command. Without it the message
  number is used, and it shifts after any deletion.

If the provider offers IMAP, re-adding the account without `--protocol pop3` is
the real fix.

## Nothing is cached

No mail is stored on disk. Every command is a fresh connection, so a listing can
be stale by the time you act on it — a UID that vanished between two commands
means another client moved or deleted the message.
