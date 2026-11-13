# Speed baseline (0.9.5, step 2)

Status: **skeleton, not measured yet.** This file is filled in when the measuring runs. It records
what the app takes today; it recommends no change (speed fixes are their own PR, after cabledrawer sets
the targets: 0.9.5 plan, Q3).

## How to re-run

```
cd e2e
npm ci                                  # once; installs the test tools (nothing new)
./perf/run.sh                           # builds the image, runs it as a Pi 4 class box, seeds, measures, stops
```

Pieces, each usable alone: `perf/seed.ts` (fills one household through `/api/v1`), `perf/measure.ts`
(`--profile phone|desktop`, `--runs 5`), `perf/table.ts` (makes the tables below from the results).
None of it is part of `./check`, and the normal test run only reads `e2e/tests/`.

## Machine and settings

(to fill in)

## Numbers

(to fill in)

## What looks slow

(to fill in)
