# IMAP search, beyond the built-in flags

`inbox` and `search` cover the common filters. `--query` appends a raw IMAP
SEARCH expression (RFC 3501 §6.4.4) for everything else, and combines with the
built-in flags — all terms are ANDed.

```bash
claudeforanything emails-for-claude search --query 'HEADER List-Id "python-dev"'
claudeforanything emails-for-claude inbox --unseen --query 'NOT HEADER Precedence "bulk"'
```

## Terms worth knowing

| Expression | Matches |
| :--------- | :------ |
| `ALL` | Everything |
| `NEW` | Recent and unseen |
| `OLD` | Not recent |
| `DRAFT`, `DELETED`, `UNDELETED` | The corresponding flag |
| `KEYWORD <flag>` / `UNKEYWORD <flag>` | A custom server flag |
| `HEADER <field> <string>` | Any header, substring match |
| `ON <DD-Mon-YYYY>` | Sent on that exact date |
| `SENTSINCE` / `SENTBEFORE` / `SENTON` | The `Date:` header rather than arrival time |
| `SMALLER <n>` / `LARGER <n>` | Size in bytes |
| `UID <set>` | An explicit UID set, e.g. `UID 100:200` |

Note the date distinction: `SINCE` and `BEFORE` filter on the server's *internal*
date (when it arrived); `SENTSINCE` and `SENTBEFORE` filter on the `Date:` header
(when the sender claims they wrote it). For "what arrived while I was away",
`SINCE` is the honest one.

## Boolean logic

- Terms side by side are **AND**: `UNSEEN FROM "boss"`.
- `OR <a> <b>` is prefix and takes exactly two terms. Three alternatives nest:
  `OR FROM "a@x" OR FROM "b@x" FROM "c@x"`.
- `NOT <term>` negates the next term only.

```bash
# Unread, from either of two people
claudeforanything emails-for-claude search \
  --unseen --query 'OR FROM "alice@example.com" FROM "bob@example.com"'

# Everything this month that is not a newsletter
claudeforanything emails-for-claude search \
  --since 2026-08-01 --query 'NOT HEADER List-Unsubscribe ""'
```

## Dates

IMAP wants `DD-Mon-YYYY` with an English month abbreviation — `05-Jan-2026`. The
`--since` and `--before` flags accept `YYYY-MM-DD` and convert for you. Inside
`--query` you must write the IMAP form yourself.

## Non-ASCII

`--from`, `--subject` and friends detect non-ASCII values and send
`CHARSET UTF-8`, retrying without it if the server rejects the prefix. Inside
`--query` the string is passed through as UTF-8, which older servers may refuse;
if a query with accents returns nothing, fall back to an ASCII substring.

## What IMAP cannot do

- **"Has an attachment"** is not a search term. `--has-attachment` approximates
  it with `HEADER Content-Type "multipart/mixed"`, which misses attachments in
  `multipart/related` and matches some inline-image messages. When precision
  matters, over-select and then check `.data.attachments` from `read`.
- **Relevance ranking.** Results come back in UID order; `inbox` reverses them
  for newest-first. There is no "best match".
- **Cross-folder search.** SEARCH is scoped to the selected mailbox. Loop over
  `folders` output to cover several, or use Gmail's `[Gmail]/All Mail`.
- **Regular expressions.** Substring matching only.

## Server variation

`SEARCH` support is uneven. If a query returns an `imap_error`, the server has
most likely rejected an extension term. Simplify to the core terms above and
filter the rest client-side from `--json` output.
