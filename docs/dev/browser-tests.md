# Browser tests: keeping them fast and tidy

Notes for whoever writes or fixes a browser test (the Playwright tests in `e2e/`). Written in plain words on purpose. The product rules are in `docs/spec.md`; this page is only about the tests.

## Why a test can pass alone and time out in `./check`

Two things differ in a full run.

1. **The machine is busy.** A full `./check` builds images and runs scanners, and other work may be running too. A browser test that takes 7 seconds on a quiet machine can take 20 seconds or more. Every test has 30 seconds in all, and most waits inside a test have 5 seconds (10 where a test says so).
2. **The app holds more data.** All the tests in one run share one app and one database. By the time a late test runs, the Shopping list, Pantry and Ingredients hold everything the earlier tests added. A page with 500 or more elements takes noticeably longer to scan than the same page in a fresh app.

So when a test only fails in a full run, look for work that grows with load or with data, and cut it.

## What to do

- **Wait for the thing you need, never for a number of milliseconds.** Wait for the heading, the list or the dialog to be there (`await expect(...).toBeVisible()`), then act. A fixed `waitForTimeout` is too short on a busy machine and too long on a quiet one.
- **Wait for what replaces what you clicked.** When typing in a search box swaps the list for a list of results, wait for the results before clicking a row, or the click lands on a row that is about to be thrown away (`openRow` in `pantry.spec.ts`).
- **Find a row by searching, not by its place in the list.** On desktop a place shows only its first 8 rows, and by the time a late test runs, earlier tests have filled the Fridge. Use `openRow` in `pantry.spec.ts`, which searches for the row and waits for the results.
- **Before you cut the connection, let the page go quiet.** An answer that reaches the app after the connection is cut counts as "connected" and cancels the offline bar before it shows. `open()` in `live.spec.ts` waits for the network to be idle for this reason; don't swap that for a fixed pause.
- **Scan each state once.** `checkPage` (in `e2e/tests/a11y.ts`) already scans both themes. Don't loop over the themes around it, which scans every state four times. A scan costs about a second on a page of a few hundred elements, and more as the page grows.
- **Scan what the test is about.** If a test is about one dialog, the rest of the page can be left to the page's own accessibility test. If you do scan less, keep the same rules and both themes, and say why in a comment.
- **Let a fade or slide finish before you scan.** The scan helpers do this for you (`waitForAnimations` in `a11y.ts`). A page caught half-way through a fade has the wrong colours.
- **Give a long test the time it really needs, and say so.** A test with many scans can ask for more time with `test.slow()` (three times the usual). Put the numbers in a comment next to it: how many scans, and how long they take. Don't raise a timeout to hide a test that is slow for no good reason.
- **Find where the time goes before you change anything.** Run the test with `--trace on`, open the trace (`npx playwright show-trace <folder>/trace.zip`), and look at the long steps. Or run the file's whole project (for example `--project="desktop 0.3"`), so the app holds the same data as in a full run.

## Tidying up after a run

A test run must leave nothing in `/tmp` (cabledrawer, 22 Oct). On that day 2,256 leftover browser-test folders (4.1 GB) and 2.8 GB of pytest folders filled `/tmp`. On the development machine `/tmp` is memory-backed (a tmpfs), so leftovers also use memory, which can slow other tests down.

- The browser tests make one folder, `/tmp/mealwright-e2e-<random>`, with a data folder per test server inside it. `e2e/serve.mjs` removes it when the servers stop. Playwright is told to stop `serve.mjs` politely (`gracefulShutdown` in `playwright.config.ts`); its default is to kill it, which skips the clean-up.
- pytest removes each test's folder as soon as the test ends (`tmp_path_retention_policy = "none"` in `backend/pyproject.toml`), and with them its own run folder.
- `./check` runs the backend and browser tests in a private temp folder of its own, removes it when it ends (even if you stop it), and has a step, "tests: nothing left", that fails if the browser or pytest folders are still there. `backend/tests/test_tmp_cleanup.py` proves the pytest part on its own.
- If you stop a run by hand, stop only your own run, by its process ID, with an ordinary `kill <pid>` (not `kill -9`). `./check` then stops the step it is running and everything that step started within a few seconds (it asks them to stop, and forces it after about 5 s), removes its private temp folder and ends. Delete only folders your own run made.
