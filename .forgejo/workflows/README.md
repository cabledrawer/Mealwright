# Intentionally empty

Forgejo runs the workflows in `.forgejo/workflows/` and, only when this folder does not exist, falls back
to `.github/workflows/`. This folder exists so the GitHub workflows never run on Forgejo.
See `docs/dev/move-to-github.md`.
