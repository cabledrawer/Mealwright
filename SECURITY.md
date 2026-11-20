# Security policy

## Reporting a problem

Please don't report security problems in public issues, discussions or pull requests.

From 1.0.0, report them privately through GitHub's private vulnerability reporting: on the Mealwright repository, open **Security → Report a vulnerability**. Only the maintainer can see the report.

Please include:

- what the problem is and what an attacker could do with it
- the steps to reproduce it
- the Mealwright version, and how it was installed

Mealwright is a spare-time project. You can expect a first reply within about a week. Please give us a reasonable time to release a fix before you share details publicly.

Before 1.0.0, Mealwright is not published, so there is nothing public to report against yet.

## Supported versions

Only the latest release gets security fixes. They ship as patch versions (for example 1.0.0 → 1.0.1).

## What Mealwright does to keep you safe

- Nothing leaves your server unless you switch it on. Every outgoing request goes through one outbound gate, and a test fails if any other code makes a network call.
- A strict Content Security Policy: pages only load files from your own server.
- Passwords are hashed with Argon2, and repeated wrong guesses slow down.
- There is no default admin password. The first person to set up creates the admin account.
- Recipe imports can't reach private or internal addresses unless the admin allows them.

## What Mealwright does not do yet

- **The database and its backups are not encrypted in 0.7.** Anyone who can read the server's data folder can read everything in it. Whether to encrypt the server's disk is the owner's choice: if you want that protection, switch on disk encryption on the server (for example full-disk encryption on the machine or volume that holds `/data`).
- **Export everything can be encrypted with a password (0.9.5), but nothing else is.** The optional password on Settings › Backups & your data › Export everything encrypts that file only (Argon2id for the key, AES-256-GCM; the format is in `docs/export-format.md`). Mealwright keeps the password nowhere and can't recover it: a file whose password is lost can't be opened. Without a password the export is a plain zip, so keep it somewhere safe. Backups are not encrypted by it.
- Notification links and the single sign-on client secret do not exist yet (they come in 0.8). When they do, they will be stored encrypted.
