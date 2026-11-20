# Speed baseline (0.9.5, step 2)

What the app takes today on a Pi 4 class server and an older phone. **Measure only: nothing in the
app was changed, and this file recommends no change.** Speed fixes are their own PR, after cabledrawer
sets the targets (0.9.5 plan, Q3).

Measured on 13 Nov 2026 on the 0.9.5 docs tip (dd77aaa9); this PR changes no app code.

## How to re-run

```
cd e2e
npm ci                 # once: installs the test tools (nothing new)
./perf/run.sh          # builds the image, runs it as a Pi 4 class box, seeds it, measures phone and desktop, prints the tables, stops
```

The pieces, each usable alone (the server must already run, and `.state.json` comes from the seed):

```
node perf/seed.ts --base http://127.0.0.1:7795 --setup-code <the code in docker logs mw-perf>
node perf/measure.ts --profile phone   --runs 5 --out perf/results-phone.json
node perf/measure.ts --profile desktop --runs 5 --out perf/results-desktop.json
node perf/table.ts perf/results-phone.json perf/results-desktop.json
```

`--only "Plan (month),Pantry"` re-runs a few steps. Settings come from the environment
(`PERF_PORT`, `PERF_IMAGE`, `PERF_NAME`, `PERF_CPUS`, `PERF_RUNS`). None of this is part of
`./check`; the normal test run only reads `e2e/tests/`. Nothing leaves the machine: the container
has none of the app's outbound switches on, and the results stay in this file.

## Machine and settings

- **PC:** a 6-core desktop processor (12 threads), 24 GB. Docker container from the app's own image
  (`docker build` of the repo, as `./check` does), data on a fresh volume, plain http on loopback.
- **Server held to a Pi 4 class box:** `--cpu-period 10000 --cpu-quota 5000` (half of one of this
  PC's cores, in 10 ms slices) and `--memory 4g --memory-swap 4g`. Memory use during the runs: about 260 MB.
- **Why 0.5 cores (estimate, proposed, for cabledrawer):** a Pi 4 has 4 cores of about 1.5 GHz. I
  estimated one of this PC's cores at about 8 to 10 times a Pi 4 core (from memory of published
  single-core scores; not measured here), so four Pi cores come to about half of one of ours.
  **This is a rough guess and the check below says it is on the kind side:** a quota can only slow
  the container down by taking turns, and the same small Python loop (below) took 0.76 s in the
  container against 0.24 s on the PC, about 3 times slower, not 8 to 10. So the server numbers here are
  probably **better than a real Pi 4 would give**. To tune it, run the loop on the real Pi, and
  set `PERF_CPUS` (0.25 gives about 6 times slower) until the container's time matches.
- **Both settings measured (cabledrawer 13 Nov):** the tables below are at 0.5 core (`PERF_CPUS=0.5`, the
  first run) and at 0.25 core (`PERF_CPUS=0.25`, the second run, same data and script). At 0.25 the loop
  took 1.54 s in the container against 0.24 s on the PC, about 6.4 times slower, closer to the 8 to 10
  estimated for a Pi 4. Which one matches a real Pi 4 is still the open question above.

  ```
  python3 -c "
  import time
  t=time.perf_counter(); n=0
  for i in range(3_000_000): n+=i*i%7
  print(round(time.perf_counter()-t,2),'s')"
  ```
  (Run it on the PC, in the container with `docker exec mw-perf python -c ...`, and on the Pi.)
- **Phone:** Chromium (Playwright's) at 428 x 926, touch, device scale 2; CDP CPU throttling rate 4;
  network as used here (proposed, for cabledrawer; not checked against Chrome's current preset): latency 562.5 ms, download 1.6 Mbit/s x 0.9 (180000 bytes/s), upload
  750 kbit/s x 0.9 (84375 bytes/s). These are the numbers I put in for "slow 4G"; I did not check them
  against the current Chrome preset. (The older `slow-phone.spec.ts` test uses 300 ms and 400 kbit/s.)
- **Desktop:** Chromium at 1440 x 900, no throttling, against the same slowed server over loopback.
- **Data (through `/api/v1`, `perf/seed.ts`):** 180 ingredients, 150 of them in the pantry; 200 recipes
  with a 640x480 photo each (synthetic grainy PNGs, so real phone photos may be larger); breakfast, lunch and
  dinner planned on each of 31 days (93 meals); 60 shopping lines.
- **How a time is taken:** from asking for the page (or tapping) until the page's own ready signal is drawn:
  a heading plus a list, a count, a recipe or planned-meal name. Never `networkidle`. First load = a
  new browser profile each run (nothing cached), already signed in (Sign in includes typing the name and password).
  Repeat load = the same page asked for again with what the browser kept, after one visit and a short wait for the service worker.
  5 runs each; the tables show **median / slowest** in ms.
- **API times:** the server does not report its own times (no Server-Timing header, no per-request
  log), and the app was not changed to add them. The tables give (a) the browser's own wait from sending a
  request to the first byte of its answer, the slowest seen during the page's first load (under the phone
  slowing this is mostly the 562 ms added delay, so read it on the desktop table), and (b) a direct pass of 5 calls on
  loopback with no slowing (the first call of each is a warm-up, not counted).

## Numbers

Tables from `node perf/table.ts` (times in ms, median / slowest of 5 runs).

### phone at 0.5 core: median / slowest, in ms, of 5 runs

| What | First load | Repeat load | Slowest API wait seen (first load) |
|---|---|---|---|
| Sign in | 8196 / 8199 | n/a | 806 (/session) |
| Today | 7369 / 7807 | 955 / 987 | 581 (/setup) |
| Recipe list | 8191 / 8591 | 1778 / 1817 | 614 (/household/fill-from-browser) |
| One recipe | 8329 / 8412 | 1483 / 1511 | 609 (/recipes/8/stock) |
| Plan (week) | 9620 / 10078 | 2753 / 2774 | 611 (/recipes) |
| Shopping list | 9133 / 9150 | 974 / 1072 | 607 (/household/fill-from-browser) |
| Pantry | 8598 / 8632 | 2263 / 2296 | 608 (/pantry) |
| Plan (month) | 10682 / 11723 | 3820 / 3862 | 611 (/recipes/tags) |

| Action | Time to show | Slowest API wait |
|---|---|---|
| Tick a shopping line | 53 / 72 | none |
| Search recipes | 1307 / 1319 | 601 (/recipes/photos/159/list) |
| Add a recipe to the plan | 1299 / 1878 | 590 (/plan) |
| Pantry stocktake save | 1953 / 1959 | 582 (/stocktake/places/1/finish) |

| API call (no slowing, on the container) | ms |
|---|---|
| GET /today | 208 / 220 |
| GET /recipes (first 50) | 59 / 60 |
| GET /recipes?q=garlic | 61 / 67 |
| GET /recipes/{id} | 12 / 21 |
| GET /plan (7 days) | 28 / 30 |
| GET /plan (42 days) | 31 / 40 |
| GET /shopping/lists/{id} | 120 / 120 |
| GET /pantry | 271 / 280 |
| GET /stocktake | 11 / 20 |

### desktop at 0.5 core: median / slowest, in ms, of 5 runs

| What | First load | Repeat load | Slowest API wait seen (first load) |
|---|---|---|---|
| Sign in | 2788 / 2840 | n/a | 676 (/session) |
| Today | 2006 / 2042 | 136 / 232 | 202 (/household/fill-from-browser) |
| Recipe list | 903 / 2818 | 263 / 297 | 388 (/recipes) |
| One recipe | 1458 / 1995 | 336 / 350 | 518 (/recipes) |
| Plan (week) | 985 / 1068 | 294 / 319 | 278 (/recipes) |
| Shopping list | 2713 / 2763 | 236 / 244 | 1758 (/shopping/changes) |
| Pantry | 2714 / 3697 | 895 / 915 | 2451 (/pantry) |
| Plan (month) | 1073 / 1178 | 330 / 339 | 239 (/recipes) |

| Action | Time to show | Slowest API wait |
|---|---|---|
| Tick a shopping line | 32 / 41 | 119 (/shopping/lists/2df8ba55-830d-4a8a-87e1-8a2504ba7c46) |
| Search recipes | 283 / 786 | 216 (/recipes) |
| Add a recipe to the plan | 190 / 580 | 337 (/plan/items) |
| Pantry stocktake save | 323 / 830 | 606 (/stocktake/places/1/finish) |

| API call (no slowing, on the container) | ms |
|---|---|
| GET /today | 210 / 220 |
| GET /recipes (first 50) | 59 / 61 |
| GET /recipes?q=garlic | 63 / 69 |
| GET /recipes/{id} | 14 / 18 |
| GET /plan (7 days) | 24 / 28 |
| GET /plan (42 days) | 39 / 42 |
| GET /shopping/lists/{id} | 119 / 120 |
| GET /pantry | 288 / 391 |
| GET /stocktake | 13 / 18 |

### At 0.25 core (second run, 13 Nov)

Same script, data and phone and desktop settings; only the server's share of the CPU is halved.

#### phone at 0.25 core: median / slowest, in ms, of 5 runs

| What | First load | Repeat load | Slowest API wait seen (first load) |
|---|---|---|---|
| Sign in | 10699 / 10829 | n/a | 1448 (/session) |
| Today | 10861 / 10892 | 988 / 1030 | 579 (/setup) |
| Recipe list | 11210 / 11300 | 1816 / 1918 | 588 (/recipes/drafts) |
| One recipe | 11852 / 12333 | 1479 / 1518 | 592 (/recipes/8) |
| Plan (week) | 12216 / 12758 | 2765 / 2816 | 600 (/recipes) |
| Shopping list | 13734 / 14158 | 1021 / 1085 | 2552 (/shopping/changes) |
| Pantry | 12726 / 13213 | 2273 / 2345 | 1942 (/pantry) |
| Plan (month) | 12768 / 12785 | 3828 / 3844 | 602 (/recipes) |

| Action | Time to show | Slowest API wait |
|---|---|---|
| Tick a shopping line | 107 / 160 | none |
| Search recipes | 835 / 1333 | 583 (/recipes/photos/30/list) |
| Add a recipe to the plan | 1742 / 2100 | 593 (/plan) |
| Pantry stocktake save | 1961 / 1999 | 585 (/stocktake/places/1/finish) |

| API call (no slowing, on the container) | ms |
|---|---|
| GET /today | 359 / 361 |
| GET /recipes (first 50) | 129 / 149 |
| GET /recipes?q=garlic | 149 / 241 |
| GET /recipes/{id} | 30 / 39 |
| GET /plan (7 days) | 50 / 60 |
| GET /plan (42 days) | 79 / 80 |
| GET /shopping/lists/{id} | 241 / 800 |
| GET /pantry | 500 / 510 |
| GET /stocktake | 31 / 41 |

#### desktop at 0.25 core: median / slowest, in ms, of 5 runs

| What | First load | Repeat load | Slowest API wait seen (first load) |
|---|---|---|---|
| Sign in | 4519 / 5205 | n/a | 1632 (/session) |
| Today | 3192 / 3420 | 308 / 819 | 293 (/household) |
| Recipe list | 2255 / 3536 | 424 / 915 | 479 (/recipes) |
| One recipe | 3645 / 3779 | 879 / 1336 | 799 (/recipes) |
| Plan (week) | 2245 / 2780 | 901 / 922 | 968 (/recipes) |
| Shopping list | 4393 / 4957 | 346 / 831 | 3016 (/shopping/changes) |
| Pantry | 4833 / 5040 | 1408 / 1444 | 3147 (/pantry) |
| Plan (month) | 2252 / 2267 | 1099 / 1170 | 433 (/recipes) |

| Action | Time to show | Slowest API wait |
|---|---|---|
| Tick a shopping line | 32 / 32 | 188 (/shopping/changes) |
| Search recipes | 786 / 786 | 403 (/recipes) |
| Add a recipe to the plan | 912 / 1198 | 703 (/recipes) |
| Pantry stocktake save | 828 / 1338 | 954 (/stocktake/places/1/finish) |

| API call (no slowing, on the container) | ms |
|---|---|
| GET /today | 369 / 370 |
| GET /recipes (first 50) | 130 / 140 |
| GET /recipes?q=garlic | 150 / 150 |
| GET /recipes/{id} | 30 / 40 |
| GET /plan (7 days) | 51 / 59 |
| GET /plan (42 days) | 70 / 79 |
| GET /shopping/lists/{id} | 239 / 249 |
| GET /pantry | 490 / 492 |
| GET /stocktake | 31 / 42 |

**0.5 against 0.25 core, in short:** phone first loads go from 7.4 to 10.7 s up to 10.7 to 13.7 s
(shopping list 13.7 s is the slowest); phone repeat loads hardly change (1.0 to 3.8 s: they are
mostly the phone's own CPU and cache); desktop first loads go from 0.9 to 2.8 s up to 2.2 to 4.8 s
(pantry 4.8 s, sign in 4.5 s). The server's own call times roughly double (`/pantry` 270 to 500 ms,
`/today` 210 to 360 ms, `/shopping/lists/{id}` 120 to 240 ms).

Notes on the actions (both settings):
- *Tick a shopping line*: the time to show the line ticked. Its answer from the server comes later (the phone's
  `/shopping/actions` call waited 585 ms for its first byte) and does not hold the screen up.
- *Add a recipe to the plan*: from typing in the Add box to the dialog closing with the recipe in its meal. The
  first run on each profile is the slowest (it loads the recipe search).
- *Pantry stocktake save*: from tapping Next on the first place to the next place showing; each run starts a new stocktake.

## What looks slow

Facts from the tables above, not a to-do list.

1. **First load on the phone is 7 to 11 s on every page** (sign in 8.2 s, Today 7.4 s, plan week 9.6 s,
   plan month 10.7 s), against 1 to 3 s on the desktop. The built web app is 2.7 MB. The slowed
   network and CPU explain most of it; the table does not split that between the download and running the scripts.
2. **Repeat load on the phone is 1 to 4 s** (Today 1.0 s, shopping 1.0 s, pantry 2.3 s, plan week 2.8 s, plan
   month 3.8 s), so the plan screens are the slowest to come back.
3. **Pantry** is the slowest list on the desktop (first load 2.7 s; its `/pantry` call waited up to 2.5 s in the
   browser while other calls ran; the direct call takes 270 to 290 ms). **Today's** `/today` call is the next
   slowest alone (about 200 ms), then the shopping list (120 ms).
4. **Shopping list first load is 2.7 s on the desktop** with the slowest wait on `/shopping/changes` (1.7 s).
5. **Sign in takes 2.8 s on the desktop (median; slowest 2.8 s)** (8.2 s on the phone); the `/session` call waited up to 0.9 s.
6. **A plan page makes many calls on its first load** (at least `/setup`, `/me`, `/household`, `/recipes/drafts`,
   `/recipes/tags`, `/recipes`, `/meal-slots`, `/plan` ...); on the phone each waits at least the 562 ms delay.
7. **Recipe search on the phone shows its result in 1.3 s** (desktop 0.28 s); adding to the plan 1.3 s; saving a stocktake place 2.0 s.
8. **Quick:** ticking a line shows at once (32 ms desktop, 53 ms phone) and the server calls on the other pages
   are 10 to 40 ms (`/recipes/{id}`, `/plan`, `/stocktake`).

9. **At 0.25 core** the same order holds and the server-bound steps grow most: phone shopping list first load
   13.7 s, phone pantry 12.7 s, desktop pantry 4.8 s, desktop sign in 4.5 s; the `/shopping/changes` and
   `/pantry` waits reach 2.5 to 3.1 s in the browser.

Limits of this baseline: one PC; the server slowing is an estimate (see above); the photos are synthetic; the
tick, add and stocktake steps were tuned against the current screens, so a change to those screens means
checking the script's selectors.
