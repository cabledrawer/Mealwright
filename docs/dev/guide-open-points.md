# Open points from the user guides (for cabledrawer)

The guides (`README.md`, `SECURITY.md`, `docs/*.md`) carry no "proposed" or TODO notes (beta.3, D1). Everything that was marked there is settled by the safest reading, and listed here to confirm or change. Proposed, for cabledrawer.

- `docs/backups.md`: the copy before Delete everything always has its photos folder, whatever Include photos says; a photo saved and deleted within the few milliseconds of a backup can be missing from that backup's folder; the photo folders are hard links (and copies where a link can't be made). Same facts in `docs/restore.md`.
- `docs/restore.md`: the single sign-on client secret opens only with `data/secret.key`; an admin who has only ever signed in with single sign-on needs `reset-admin` first; a restore ends every sign-in, API token and sign-in link made after the copy (B7 R5).
- `docs/backups.md`: there is no screen or command that loads an export back into Mealwright (the code has none); the guide now says so and points to restore.
- `docs/api.md`: no example of a call that changes something (the request body would have to be guessed from the code). Say which call to show if you want one.
- `docs/sso.md`: the notes for Authentik, Keycloak and Authelia are general, not from a test run (the guide now says so). The Keycloak refusal and the `groups` scope are in `backend/src/mealwright/sso.py`. Also: setup changes that can lock out the last single-sign-on-only admin are not refused.
- `docs/export-format.md`: the encrypted file's format (cipher, key derivation, costs) is the builder's choice within cabledrawer's 13 Nov decision.
- `README.md`: until 1.0.0 the release list's address is a placeholder (`PLACEHOLDER_OWNER` in `backend/src/mealwright/updates.py`), so no update check connects in test versions; change the sentence when the real address goes in.
- `docs/upgrade.md`: the last paragraph of "Going back" is current: an upgrade is all or nothing since beta.2, so the old TODO about a half-upgraded database is gone.
