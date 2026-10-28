---
name: hand-test-fix
description: Fix one bug from cabledrawer's hand test by its F-number - find the evidence and his decision, prove the bug with a failing test, fix it, and write how cabledrawer can see it's fixed. Use for every F-number a PR fixes.
---

# Fix a hand-test finding (F-number)

For each F-number in the PR, in this order.

1. **Evidence, that F only.** `grep -n -A6 '\bF<n>\b' <sync>/<milestone-hand-test>.md` (see CLAUDE.local.md: Where things are) (the file named in `docs/dev/progress.md`). Never read the hand-test file whole. Note the device (PC, iPhone, iPad), the screen and the exact words cabledrawer saw.
2. **The decision.** `grep -n 'F<n>' docs/spec.md docs/dev/progress.md`. cabledrawer's decision wins over the finding's own suggestion. No decision, or the spec doesn't cover it: stop and ask the lead (the lead asks cabledrawer).
3. **Reproduce first.** Write the test that shows the bug (backend unit test, frontend unit test, or a browser test when it's about what's on screen) and see it fail for the reason in the evidence. If it doesn't fail, say so: the bug may be device-only (WebKit, a phone width, the service worker, a reverse proxy); try that before changing code.
4. **Fix the cause,** not the symptom. Keep the fix to this F; anything else you notice goes in the report as a follow-up.
5. **On screen?** Screenshots in both themes (and phone width when it's a phone finding) before and after, in the PR's screenshot folder. Words come from `docs/dev/words.md`; new words are marked "proposed, for cabledrawer".
6. **Commit** one F per commit where possible: `F<n>: <what's fixed, in plain words>`.
7. **How to see it:** one line for the PR body's "What cabledrawer needs to check" and for the milestone's hand-test checklist: `F<n> (<device>): <what to do> → <what you should now see>.` The lead collects these into `<sync>/<version>-checklist-for-cabledrawer.md` at release.

If the cause is outside Mealwright (a reverse proxy, the server, the phone's browser), stop with the evidence and tell the lead; don't work around it in the app.
