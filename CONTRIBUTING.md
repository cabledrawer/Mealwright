# Contributing to Mealwright

Thanks for helping. Mealwright is a spare-time project, so replies may take a week or so.

Until 1.0.0, development happens in a private repository and outside contributions aren't open yet. This guide already applies to every change, including the maintainer's own.

## Before you start

- Anything bigger than a small fix starts as an issue first, so we can agree on it before you write code.
- Bugs go in issues. Feature ideas go in Discussions, so issues stay bugs only.
- Security problems are never reported in public. See [SECURITY.md](SECURITY.md).

## The ethos (never broken)

Every change is checked against these rules:

- **No data collection.** No telemetry, analytics, usage stats or crash reporting, not even opt-in. Logs stay on the server.
- **No location access, ever.** Units and country come from the browser or OS language, or the user's own choice.
- **No new outbound connection unless it sits behind a Privacy switch.** Every outgoing request goes through the outbound gate (`mealwright.outbound`), which blocks it unless its switch is on. While the app runs, any other connection or DNS lookup is refused. Never call `httpx`, `requests`, `urllib` or sockets directly. The test suite fails if you do.
- **No third-party assets at runtime.** Fonts, icons and scripts are bundled. No CDNs. The Content Security Policy stays strict.
- **Recipe images are stored locally**, never hotlinked.

## UX rules

- **Phone and desktop are both first-class, and phone breaks ties.** Where a trade-off has to be made, phone wins, but never at the cost of a worse desktop experience.
- Plain words: "cupboard", "use soon", "tubs left", never database words.
- Undo, not "Are you sure?". Updates are instant (optimistic).
- One switch component for every on/off.
- Vertical scrolling only.
- WCAG AA in light and dark themes; touch targets at least 44 px.

## Sign your commits (DCO)

Mealwright uses the [Developer Certificate of Origin](https://developercertificate.org/), not a CLA. Add a sign-off line to every commit to confirm the work is yours to give under AGPL-3.0:

```bash
git commit -s
```

This adds `Signed-off-by: Your Name <you@example.com>`, using the name and email in your git config. Pull requests with unsigned commits can't be merged.

## Say when you used AI

If any part of your change was written with AI help, say so in the pull request description. You can also add an `Assisted-by:` trailer to the commit, for example:

```bash
git commit -s --trailer "Assisted-by: <tool name>"
```

You are still responsible for the change: you must understand it, test it and be able to sign it off.

## Dependencies

Every dependency must have a licence that works with AGPL-3.0: MIT, BSD, Apache-2.0, ISC, LGPL, GPL-3.0, AGPL, PSF-2.0 or MPL-2.0. MPL-2.0 packages marked "Incompatible With Secondary Licenses" are not allowed, because MPL-2.0 only works with AGPL through that secondary-licence clause. OFL-1.1 is allowed for fonts only. GPL-2.0-only is not allowed. `./check` checks this automatically.

Ask in an issue before adding a new dependency, and check that it doesn't phone home.

## Pull requests

- Keep commits small. Each commit must build and pass the tests.
- Add tests for every feature or fix.
- Every schema change is an Alembic migration, and every table carries `household_id`.
- The web app uses only the public `/api/v1` API. No private endpoints.
- `./check` must pass: lint, type checks, tests, the outbound-gate test, the licence check and the security scanners. Paste its summary into the pull request description.

## Development setup

You need:

- Python 3.14 and [uv](https://docs.astral.sh/uv/)
- Node.js 24 LTS
- Docker, to build and run the image

Setup steps will be added here as the backend and frontend land during 0.1.
