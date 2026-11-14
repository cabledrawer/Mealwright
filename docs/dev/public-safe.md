# Keeping the repo safe to make public

No tracked file may name the owner's machines, accounts, folders or private addresses (cabledrawer 13 Nov).
Those live in two git-ignored files at the repo root. `./check` fails on any that slip into a tracked file.

## The two private files

| File | What it holds | Example (tracked) |
|---|---|---|
| `CLAUDE.local.md` | Notes: where `<code server>`, `<main checkout>` and `<sync>` really are. Claude Code loads it by itself. | `CLAUDE.local.md.example` |
| `.private-words` | The word list `./check` searches for: one word or regular expression per line, case-insensitive, `#` starts a comment line. | `.private-words.example` |

To make them: copy each example to the name without `.example` and put your own values in. Neither is ever
committed. A fresh clone or a copy made with `git worktree add` has no list of its own; `./check` then looks
in the main checkout, or at the file named by `CHECK_PRIVATE_WORDS`.

Tracked files use neutral wording and placeholders instead (`<code server>`, `<main checkout>`, `<sync>`,
`git.example.org`, documentation addresses such as `192.0.2.x`), and say "see `CLAUDE.local.md`" where a
real value is needed.

## The two `./check` steps (also in `./check --fast`; each takes about a second)

- **repo: home paths and addresses** always runs. It fails on a home-folder path, a drive mount (`/mnt/<letter>/`),
  a Windows drive path and a private IPv4 address or `fd00::/8` address in any tracked text file. True
  examples are listed, one whole value per line, in `scripts/public-safe-allow.txt`.
- **repo: private words** reads `.private-words` and fails on any word in a tracked file's text or file name.
  Where there is no list, it is skipped, with the note "no private word list here", never failed.

Both print `file:line: what matched` for each hit, and nothing else. The log stays local. Binary files are not read
(their names are still checked). Run one by hand from `e2e/`: `node scripts/private-words.mjs --builtin`, or
`node scripts/private-words.mjs --words ../.private-words`.
Only files are searched, not the commit history.
