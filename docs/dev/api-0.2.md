# API and data for 0.2 (foods, pantry, history and undo)

Written 17 Oct 2026 as the contract between the backend and the web app for milestone 0.2. It covers both backend pull requests: **foods-and-units** (foods, sizes, other names, stand-ins, merge, places, shops, conversions) and **stock-history-undo** (stock, Use soon, Recent changes, Undo, thinning). The spec (`docs/spec.md`) wins wherever this file disagrees with it. Generated OpenAPI (`/api/v1/openapi.json`) is the exact reference once built; this file is the plan.


## On one page (read this, then grep)

Added 25 Oct (cabledrawer 25 Oct), so nobody reads the whole file: read this page, then only the sections your pull request needs (`grep -n '^##' docs/dev/api-0.2.md`). This page only repeats what is below; where they differ, the section wins.

- **Rules for every endpoint (§1):** everything under `/api/v1`, signed in, same-origin for browser writes, `snake_case`; scoped to the household (another household's id is a 404); errors are `{detail, code}` with a plain sentence the screen shows as it is (§1.1).
- **Retries (§1.2):** writes may carry an `Idempotency-Key`; the same key again changes nothing and returns the original change. From 0.3 the sync queue sends the same IDs in the body.
- **Amounts (§2, §4):** stored as whole thousandths of the base unit (g, ml or count) in `amount_milli`; JSON carries plain numbers with at most 3 decimals, and finer is refused, not rounded. People's amounts come in as `AmountIn` (§4.3); a missing conversion is asked once (§4.4).
- **Display (§5):** the server sends the as-sold wording ready made (`display`, "1½ packets · about 750 g"), with no-break spaces; screens never rebuild it.
- **Tables (§3):** household settings, places and shops, foods (ingredients on screen) with sizes and other names, stock (lots), and the change log behind Undo; migrations in order in §3.7.
- **Endpoints (§6):** every food or stock write answers with the `change` it recorded (§6.1), so the screen can offer Undo at once. Foods §6.2, places and shops §6.3, stock §6.4, Recent changes and Undo §6.5.
- **Words:** the API says "food"; screens say "ingredient" (`docs/dev/words.md`).

| § | What |
|---|---|
| 1 | conventions, errors, retries |
| 2 | storing amounts |
| 3 | data model and migrations |
| 4 | units, conversions, `AmountIn`, "ask once" |
| 5 | as-sold display and rounding |
| 6 | endpoints |
| 7 | the lead's decisions on the open points (17 Oct) |

## 1. Conventions

- Everything is under `/api/v1`, needs a signed-in session (cookie), and follows the existing rules: writes from a browser must pass the same-origin check; JSON field names are `snake_case`.
- Everything is scoped to the signed-in login's household. An id from another household is a 404.
- Anyone in the household may read and change foods and stock. Only admins may change household settings.
- **Dates and times.** Use-by dates are plain local dates (`"2026-10-20"`). Moments are UTC ISO 8601 (`"2026-10-17T18:04:11Z"`). Wherever "today" matters the server also returns the derived value (`days_left`, `use_soon`, `today`) worked out in the household's time zone, so clients never need time-zone maths.
- **Amounts in JSON** are plain numbers in the food's base unit (g, ml or count), at most 3 decimal places (`750`, `1.5`, `0.25`). Anything finer is refused (422, or `bad_action` in a queued change), not rounded. An amount sent as text instead (`"1.5"`) is at most 20 characters; longer text is refused like any other text that isn't a number (422, `Input should be a valid decimal`, or `bad_action` in a queued change). This holds for every amount the API reads: amounts, sizes, weights, what's left, How much?, queued changes and nutrition. Padded text such as `"1.50000000000000000000"` is refused too (cabledrawer 21 Oct: "yes, padded text amounts are refused").
- **Amounts people type** use an `AmountIn` object (section 4.3): `{"amount": 2, "unit": "packet"}`, `{"amount": 250, "unit": "g"}`, or `{"amount": 1, "size_id": 12}`.

### 1.1 Errors

Same shape as 0.1, plus a machine-readable `code` where the client must react:

```json
{ "detail": "There's already an ingredient called Toor dal.", "code": "name_taken", "food_id": 7 }
```

| Status | `code` | When |
|---|---|---|
| 401 | — | not signed in ("Please sign in.") |
| 403 | `admins_only` | a member tries an admin-only change |
| 404 | `not_found` | no such thing in this household |
| 409 | `name_taken` | food name already used (`food_id` says which) |
| 409 | `ask_once` | the server needs a conversion it doesn't know (section 4.4; carries `ask`) |
| 409 | `already_undone` | Undo pressed twice |
| 409 | `cannot_undo` | Undo pressed on an Undo (no redo in 0.2); from 0.4 also on a `food_back` line, or on a removal line that isn't the ingredient's newest or whose ingredient is back (cabledrawer 21 Oct) |
| 422 | `too_big` | an amount over 1,000,000 g, ml or items (typed, or worked out by a conversion); cup weights are at most 2 kg and item weights at most 50 kg |
| 422 | `bad_number` | an ID, cursor or version bigger than the database can hold (over 2^63 − 1, or under −2^63; security audit, 0.4), in the path, the query or the body. Each is refused where the request is read; any other number overflow is a server error (500). In a sync action, IDs and `seen` over 2^53 − 1 are refused `bad_action` instead |
| 422 | `one_field` | a food PATCH with more or less than one field |
| 422 | `bad_key` | an `Idempotency-Key` that isn't 1 to 64 letters, digits, `.`, `-`, `_` or `:` |
| 409 | `key_reused` | an `Idempotency-Key` was reused for a different request |
| 410 | `too_old` | Undo after the undo window |
| 413 | `body_too_big` | a request body over 4 MiB, on any endpoint, signed in or not (security audit, 0.4) |
| 422 | — | validation: a list of `{type, loc, msg}` (FastAPI's list form without `input` and `ctx`, so a mistake never repeats what was sent, and a lone surrogate such as `"\ud800"` is a 422, not a 500; 0.5). The web app's `detailOf` reads `msg` only |

`detail` is always a plain-English sentence the web app can show as is. On screen it's always "ingredient", never "food" (cabledrawer 17 Oct): every `detail`, change summary, undo message, ask-once question and display text says "ingredient". "Food" stays the word in field names, codes and paths (`food_id`, `/foods`). A test scans the code for sentences that say "food".

### 1.2 Optimistic changes and retries

- Every request that changes something may carry an **`Idempotency-Key`** header: a UUID the client makes before it shows the change on screen. The web app always sends one.
- The server stores the key on the change it records (unique per household, kept as long as the change). If the same key arrives again with the same method and path, nothing is applied twice: the server answers `200` with the original `change` and the **current** state of what it touched, plus the header `Idempotent-Replayed: true`. Same key, different method or path → `409 key_reused`.
- A request that failed (4xx) stores nothing, so the client may retry with the same key (this is how "ask once" answers are sent, section 4.4).
- From 0.3 the sync queue sends the same IDs in the request body instead; the server accepts either.
- Writes are applied in the order the server receives them. No version numbers or conflict checks in 0.2: per-field saves make "last one wins" acceptable. The full offline queue (action IDs in the body, server counter, replay) is 0.3 and will reuse the same keys.
- Every write that changes foods or stock answers with the **change** it recorded (section 6.1), so the client can show the Undo toast with `change.id` straight away.

## 2. Storing amounts

**Decision: every amount is an integer number of thousandths of the base unit** (`amount_milli`): milligrams, microlitres or thousandths of an item. 750 g → `750000`; 1½ onions → `1500`; ¼ tub (0.6) → `250`.

Why:
- Exact. Quarters, halves and whole grams are exact; adding and taking away never drifts (floats do: 0.1 + 0.2).
- SQLite has no true decimal type (SQLAlchemy's `Numeric` is stored as a float there), so integers are the only exact type that behaves the same on SQLite and the later Postgres option.
- 1 mg resolution is far finer than any kitchen needs; a 64-bit integer holds 9 billion tonnes.
- Thirds (⅓ of a 500 g packet) round to the nearest milligram, which is invisible.

Other stored numbers use the same idea:
- **Weight per millilitre** (`mg_per_ml`, integer): 0.8 g/ml → `800`. "Weight of 1 cup" is this × the household's cup size; shown to the nearest gram, so a 240 ml cup round-trips within 0.25 g.
- **Weight of one item** (`item_weight_milli`, mg): an onion ≈ 150 g → `150000`.
- Fractions people pick (¼ ½ ¾ Full) are never stored as fractions; they become an amount straight away.

The API converts at the edge: JSON numbers in base units in and out (section 1); the integer form never leaves the server.

## 3. Data model

All tables have `household_id` (FK to `household.id`, `ON DELETE CASCADE`, indexed), `created_at`, and where useful `updated_at`. Each group below is one Alembic migration. Names are database names; the UI never shows them.

### 3.1 Household settings (new columns on `household`)

| Column | Type | Default | Notes |
|---|---|---|---|
| `time_zone` | str(64), null | null | IANA name (`Europe/London`). Null until the admin's browser sends it (stored once, never changed silently); until then the server uses UTC. Validated with `zoneinfo` (the image has the zone data; no new dependency). |
| `cup_ml` | int, null | null | 240 or 250. Null = not chosen yet → 250 is used. |
| `pints` | str(2) | `uk` | `uk` (568 ml) or `us` (473 ml): which pint a recipe's "pint" is when it is imported (0.6 PR 7; migration `c5f1b8d2a763`). |
| `cook_per_step` | bool | false | Cook mode's per-step ingredients (Experimental): off by default; once switched on it stays on for the household (0.7 K4, cabledrawer 1 Nov; migration `d2e6a4b81c37`). |
| `undo_days` | int | 7 | undo window |
| `history_months` | int | 12 | full history kept, then thinned |
| `use_soon_days` | int | 2 | use-by today … today + 2 |

Kept as columns on `household` (its `id` is the household_id), not a separate table: one row per household either way. Plan settings (0.6): `tub_fridge_days` 3, `tub_freezer_months` 3, `plan_ahead_days` 7 (how far ahead the shopping list looks, never asked each time), `week_starts_on` 1 (1 Monday ... 7 Sunday). The "Who's this?" picker in 0.8.

### 3.2 Places and shops

**`place`**: `id`, `household_id`, `name` str(40), `kind` (`fridge` · `freezer` · `cupboard`), `position` int. Unique (household, lower(name)).
- Four defaults made when the household is created (and by the migration for existing households): Fridge (fridge), Freezer (freezer), Cupboard (cupboard), Spice rack (cupboard).
- `kind` drives the rules, so renaming in 0.8 doesn't break them: "To freezer" goes to the first `freezer` place; "use freezer last" skips `freezer` places. Spice rack counts as a cupboard.

**`shop`**: `id`, `household_id`, `name` str(60), `position` int, `aisle_order` JSON null (null = the default aisle order; used from 0.3). Unique (household, lower(name)). No default shops.

### 3.3 Foods

**`food`**

| Column | Type | Notes |
|---|---|---|
| `id`, `household_id` | | |
| `name` | str(100) | Unique per household ignoring case, among foods that aren't merged away. |
| `counted_as` | `weight` · `volume` · `count` | Base unit: g, ml or items. |
| `staple` | bool | **Separate switch, not a fourth `counted_as`.** A staple still needs a base unit for recipes (turmeric in g). Lists show "Staple" in the "Counted as" column when it's on. |
| `count_word`, `count_word_plural` | str(30), null | Count foods only: "slice"/"slices", "piece"/"pieces", "bunch"/"bunches". Null → shown as "9 left". |
| `place_id` | FK place, null | "Lives in". Null → Cupboard when stock is added. |
| `shop_id` | FK shop, null | "Usual shop". |
| `running_low_milli` | int, null | "Running low at", base amount. |
| `table_key` | str(80), null | The bundled conversion table row this food matched when created (by name or other name). Re-matched when renamed. |
| `merged_into_id` | FK food, null | Set when merged away. Such foods are hidden everywhere but kept so old links still resolve. |
| `removed_at` | datetime, null | Soft delete (section 7, point 1). |

**`food_name`** (other names): `id`, `household_id`, `food_id`, `name` str(100). Unique per food ignoring case (checked by the server). Split finds out whether a name came from a merge through `food_merge` (the merged-away food keeps its name).

**`food_size`** (how it's sold): `id`, `household_id`, `food_id`, `name` str(40) ("packet", "dozen", "loaf", "bag"), `plural` str(40) (server-made: packet→packets, loaf→loaves, dozen→dozen, bunch→bunches; small irregulars list), `amount_milli` int > 0 (base amount: packet = 500 000 mg), `usual` bool (exactly one size is usual when a food has any; the first size added is usual), `added_when_shopping` bool (shows "added when shopping"; set from 0.3), `position`. Unique (food, lower(name), amount).

**`food_stand_in`** ("Can use instead"): `household_id`, `food_id`, `stand_in_id`. PK (food_id, stand_in_id). One way: "red onion can stand in for onion" is (onion, red onion). "Both ways" is simply two rows. No self-links.

**`food_conversion`** (the household's ask-once answers): `id`, `household_id`, `food_id`, `kind` (`weight_per_ml` · `item_weight`), `value_milli` int (mg per ml, or mg per item), `answered_by` FK login, `answered_at`. Unique (food, kind). These always win over the bundled table and app updates never touch them.

**`food_not_same`** ("Not the same" for Maybe the same): `household_id`, `food_a_id`, `food_b_id` (a < b). PK (a, b).

**`food_merge`** (merge history): `id`, `household_id`, `from_food_id`, `into_food_id`, `change_id` FK change, `merged_at`, `split_at` null. Old recipe links (0.4) to `from_food_id` resolve by following `food.merged_into_id`.

### 3.4 Bundled conversion table (not a database table)

`backend/src/mealwright/data/food-conversions.csv`, about 200 rows, columns `key, names, mg_per_ml, item_weight_mg, fdc_id`, built from USDA FoodData Central SR Legacy (April 2018, CC0 1.0) by `backend/scripts/build_conversions.py`. Credit in `docs/` and later Settings → About. Read once at start-up. Never copied into the database, so a new app version can correct a value; household answers in `food_conversion` always win.

### 3.5 Stock

**`stock_lot`** (one packet, one bag of spinach, one carton of 12 eggs):

| Column | Type | Notes |
|---|---|---|
| `id`, `household_id`, `food_id`, `place_id` | | |
| `amount_milli` | int ≥ 0 | Never below zero (database check). |
| `size_id` | FK food_size, null | What it was bought as, for display ("bought as a dozen"). Null = typed grams. |
| `use_by` | date, null | Local date. |
| `added_at` | datetime | |
| `frozen_on` | date, null | Set by To freezer ("frozen 3 Oct"). |
| `emptied_at` | datetime, null | Set when it reaches 0 (used, binned). Empty lots stay hidden for the undo window so Undo can bring them back, then the daily job deletes them. |

Adding "2 packets" makes **two lots of one packet each**, so each can be used, binned or frozen on its own and "2 packs · tap for dates" works. "1½ packets" makes a full lot and a ½ lot. A typed amount ("200 g") makes one lot with no size.

**Taking from a food** (used by group-level "used" here, and by cooking in 0.7): soonest use-by first; lots with no use-by after dated ones, oldest added first; `fridge`/`cupboard` places before `freezer`, and freezer only when the request names a freezer place. Never below zero: if there isn't enough, everything is taken and the response says how much was missing (`short_by`).

### 3.6 Change log and monthly totals

**`change`**: one row per thing a person did (one Undo button).

| Column | Notes |
|---|---|
| `id`, `household_id` | |
| `idempotency_key` | str(64), null; unique (household, key) |
| `kind` | `added` · `used` · `binned` · `set_left` · `moved` · `to_freezer` · `use_by` · `food_created` · `food_edited` · `food_removed` · `food_back` · `merged` · `split` · `undo`. `food_back` (0.4) is "Lemon is back in Ingredients": a removed ingredient brought back by a Pantry Undo or an offline add. It has no Undo, and it makes the older removal line lose its Undo; only the newest removal of an ingredient can be undone, and only while it is still removed, worked out when the list is read (cabledrawer 20 and 21 Oct; no change to the database's layout). When the change that brought it back is undone and the ingredient is removed again, its `undone` is set, and that Undo is listed under `area=ingredients` too (cabledrawer 21 Oct). Later: `shopped` (0.3), `cooked` (0.7), `found` (0.8: "Found Ghee at home: 1 jar → Cupboard", from the shopping action `found_at_home`, docs/dev/sync-protocol.md 7.6; listed under `area=pantry`, with its own Undo). |
| `login_id`, `login_name` | Who. The name is copied so the history still reads right if the login is renamed or removed. |
| `at` | when |
| `summary` | Server-made plain sentence, e.g. "Used 200 g Spinach" (section 5). Ingredient names always appear exactly as the household typed them ("MDH sambar masala"), in every summary and message. |
| `undo_data` | JSON. For food changes: each part of the foods that changed (one field, one other name, one size, one stand-in link, one remembered answer) as `[before, after]`. Undo puts a part back only if it still has its `after` value. |
| `undone_by_change_id` | FK change, null; set when undone |
| `undoes_change_id` | FK change, null; on `undo` rows |

**`change_line`**: one row per stock lot touched: `id`, `household_id`, `change_id`, `food_id`, `lot_id` (null after the lot is deleted), `amount_before_milli`, `amount_after_milli`, `place_before_id`, `place_after_id`, `use_by_before`, `use_by_after`.

**`change_month`** (thinned history; an Undo's lines count with the change it undid: under its kind and in its month (in the household's time zone, even when the Undo was the next day), as the opposite amount. A full Undo also takes that change out of the count; a partial one leaves it counted ("added 350 g, 1 change"). Rows that end up with nothing (an undone move) are dropped. So "added 500 g, then undone" leaves nothing, and there's no separate "undo" row): `household_id`, `month` ("2025-10"), `food_id`, `kind`, `amount_milli` (sum of before → after differences), `changes` (count). PK (household, month, food, kind).

**History job** (APScheduler, `mealwright/jobs.py`; it runs in the background straight after start-up, so a big backlog never holds start-up up, and then every hour at :30, with no lateness limit; it's cheap and safe to repeat, so a server that's off at night still gets it. It works in chunks of 1,000 changes, each its own short transaction, with the totals added up by the database): sum changes older than `history_months` into `change_month`, then delete them (and their lines); delete empty lots older than the undo window. `idempotency_key`s go with their change.

### 3.7 Migrations, in order

Foods-and-units PR:

1. Household settings columns.
2. `place` (+ the four defaults for each existing household) and `shop`. Setup (`POST /api/v1/setup`) also creates the four places.
3. `food`, `food_name`, `food_size`, `food_stand_in`, `food_conversion`, `food_not_same`.
4. `change` and `food_merge` (the change log comes with foods, because food edits and merges can be undone).

Stock-history-undo PR:

5. `stock_lot`, `change_line`, `change_month`.

Food, other-name and size ids are never reused (`sqlite_autoincrement`), so Undo can put a deleted row back under its old id.

## 4. Units, conversions and "ask once"

### 4.1 Units the server understands

| `unit` | Means | For |
|---|---|---|
| `g`, `kg`, `mg`, `oz`, `lb` | weight | 1 oz = 28.3495 g, 1 lb = 453.592 g |
| `ml`, `l`, `tsp`, `tbsp`, `cup` | volume | tsp 5 ml, tbsp 15 ml, cup = household `cup_ml` |
| `count` | items | |
| a size name (`packet`, `dozen`, singular or plural) | that food's size | |

`GET /api/v1/units` returns this list with the household's cup size, so clients don't hard-code it.

### 4.2 How a conversion is found

Same unit family → fixed maths. Volume ↔ weight → the food's weight per ml. Count ↔ weight → weight of one item. Count ↔ volume → item weight and weight per ml. For each value: the household's answer (`food_conversion`), else the bundled table (`food.table_key`), else **ask once**.

### 4.3 `AmountIn`

```json
{ "amount": 1.5, "unit": "packet" }
{ "amount": 250, "unit": "g" }
{ "amount": 1, "size_id": 12 }
{ "amount": 1, "unit": "cup", "answers": [ { "kind": "weight_per_ml", "food_id": 7, "grams": 200, "remember": true } ] }
```

`amount` > 0, sent as a number (as text, at most 20 characters: see section 1). `unit` or `size_id`, not both. `answers` carries ask-once replies (4.4).

### 4.4 How the server signals "ask once"

Any write that needs an unknown conversion fails, changes nothing, and answers:

```json
HTTP 409
{
  "detail": "About how much does 1 cup of Toor dal weigh?",
  "code": "ask_once",
  "ask": {
    "food_id": 7, "food_name": "Toor dal",
    "kind": "weight_per_ml",
    "question": "About how much does 1 cup of Toor dal weigh?",
    "unit": "g", "per": "cup", "cup_ml": 250,
    "suggested": 200
  }
}
```

`kind: "item_weight"` asks "Onion: about how much does one weigh?" ("About how much does 1 slice of Bread weigh?" when the ingredient has a count word) (`per: "item"`; suggested 110 g from the table). Suggestions: the bundled table's value for a close name if there is one, otherwise 0.8 g/ml × the cup (200 g for a 250 ml cup), rounded to 2 significant figures. An item weight has no suggestion unless the table knows a close food (`suggested: null`): any fixed number would be a guess.

The client shows the question with the "Remember for next time" switch (on by default) and **retries the same request with the same `Idempotency-Key`**, adding `"answers": [...]` to the `AmountIn`. With `remember: true` the server saves the answer in `food_conversion` (in the same transaction); with `false` it's used for that request only. For `weight_per_ml` and `item_weight`, `grams` is the weight of one household cup or one item. Merge (6.2) takes `answers` at the top level of its body.

"Slices in a loaf" isn't a conversion: it's a size. Adding stock as "1 loaf" for bread with no loaf size is a 409 `ask_once` with `kind: "size"`, `question: "About how many slices in a loaf of Bread?"`, `suggested: 20`; the answer is `{ "kind": "size", "food_id": 9, "name": "loaf", "amount": 20 }`, which adds the size (always remembered).

### 4.5 Lookups

`GET /api/v1/foods/{id}/convert?amount=1&unit=cup`

```json
{ "amount": 200, "unit": "g", "from": "you", "display": "200 g", "ask": null }
```
`from`: `you` (household answer) · `table` · `fixed` (same family). When unknown: `200` with `{ "amount": null, "ask": { …as above… } }` (a lookup isn't an error).

`GET /api/v1/conversions` lists the household's remembered answers (for Settings → Amounts in 0.8): `[{ "id": 3, "food": {"id": 7, "name": "Toor dal"}, "kind": "weight_per_ml", "display": "1 cup = 200 g", "answered_by": "Tess", "answered_at": "…" }]`. `DELETE /api/v1/conversions/{id}` forgets one (falls back to the table or asks again).

## 5. As-sold display

**Decision: the server returns structured numbers and a ready `display` string.** Phone apps then get the same wording and rounding, and the rules live in one place (`mealwright/amounts.py`, unit-tested). Clients may mirror the rules for optimistic updates; the server's string replaces theirs when the response arrives. Display strings never contain UI hints ("tap for dates"): the client adds those from structured fields.

**No-break spaces:** every server-made text (`display`, `short`, `totals`, summaries, messages) puts a no-break space (U+00A0) between a number and its unit or count word ("750 g", "1½ packets", "5 Onion", "1 cup"), so a narrow column never wraps "750 / g". The spaces around " · " stay normal, so text wraps there. (This file shows them as ordinary spaces.)

### 5.1 Rounding (spec, "Decided for 0.2")

- **As sold** (in a size): nearest ¼, shown with ¼ ½ ¾ ("1½ packets", "¾ packet"). Singular up to and including 1, plural above. A non-zero amount that rounds to 0 shows "under ¼ packet".
- **Count foods**: nearest ½ ("1½ onions" → with no count word, "1½ left").
- **"About" figures**: 2 significant figures ("about 750 g", "about 1.5 L"). Used whenever the as-sold figure isn't a whole number of sizes.
- **Exact figures** (typed amounts, whole sizes): whole grams/ml from 10 up, one decimal below 10, kg/L from 1000 with trailing zeros dropped ("1 kg", "1.25 kg").
- Halfway rounds up. Units: g, kg, ml, L (capital L, as in the mockups).

### 5.2 Which size is used

- A **group** (one food in one place) uses the food's **Usual** size.
- A **lot** uses the size it was bought as, else the Usual size.
- Weight/volume foods with no size: just the amount ("200 g", "450 g").
- Count foods are always shown as a count, never in sizes; a size other than 1 adds "bought as a dozen".

### 5.3 Examples

| Situation | `display` |
|---|---|
| Toor dal, 750 g, usual packet 500 g | `1½ packets · about 750 g` |
| Chickpeas, 2 lots of 500 g | `2 packets · 1 kg` |
| Paneer, 2 lots of 200 g (size "pack") | `2 packs · 400 g` |
| Milk, 1.5 L, usual bottle 1 L | `1½ bottles · about 1.5 L` |
| Eggs (count), 9, usual dozen | `9 left · bought as a dozen` |
| Bread (count word slice), 14, usual loaf 20 | `14 slices · bought as a loaf` |
| Drumsticks (count word piece), 6 | `6 pieces` |
| Spinach, 200 g, no size | `200 g` |
| Toor dal, 40 g, packet 500 g | `under ¼ packet · about 40 g` |
| Yoghurt lot, 250 g of a 500 g tub | `½ tub · about 250 g` (the web app adds "· open") |
| Yoghurt lot, 500 g of a 500 g tub | `1 tub · 500 g` |

### 5.4 Shape

```json
"stock": {
  "amount": 750, "unit": "g",
  "as_sold": { "count": 1.5, "size": { "id": 12, "name": "packet", "plural": "packets", "amount": 500 } },
  "about": true,
  "short": "1½ packets",
  "display": "1½ packets · about 750 g"
}
```

`as_sold` is null when no size applies. `short` is just the first part, for inputs such as "Running low at ½ packet". The same object (`AmountOut`) is used for running-low levels, change lines and conversions.

## 6. Endpoints

### 6.1 The change object (returned by every food or stock write)

```json
"change": {
  "id": 812, "kind": "used",
  "at": "2026-10-17T18:04:11Z",
  "who": { "login_id": 2, "name": "Wren" },
  "summary": "Used 200 g Spinach",
  "can_undo": true, "undo_until": "2026-10-24T18:04:11Z",
  "undone": null
}
```

`undone` becomes `{ "at": "…", "who": {…} }` after an Undo.

### 6.2 Foods (the Ingredients screen)

**`GET /api/v1/foods?q=dal&filter=all&limit=50&after=<cursor>`**

- `q` matches the name or any other name, ignoring case and accents; names starting with `q` come first, then names containing it, then alphabetical. Results say which name matched.
- `filter`: `all` · `staples` · `maybe_same`. ("Not in any recipe" arrives with recipes in 0.4; the parameter value will be `unused`.)
- Merged-away and removed foods never appear.

```json
{
  "total": 142,
  "counts": { "all": 142, "staples": 31, "maybe_same": 2, "maybe_same_pairs": 1 },
  "foods": [
    {
      "id": 7, "name": "Toor dal",
      "other_names": ["thuvaram paruppu", "arhar dal"],
      "matched_name": "arhar dal",
      "counted_as": "weight", "staple": false,
      "counted_as_display": "Packets · 500 g",
      "place": { "id": 3, "name": "Cupboard" },
      "stand_ins": [],
      "maybe_same": []
    },
    { "id": 8, "name": "Onion", "counted_as": "count", "counted_as_display": "Count",
      "stand_ins": [{ "id": 31, "name": "Red onion" }], "…": "…" },
    { "id": 40, "name": "Drumsticks (moringa)", "counted_as_display": "Count",
      "maybe_same": [{ "id": 12, "name": "Drumsticks", "merge_into": 12, "merge_this": true }], "…": "…" }
  ],
  "next": null
}
```

`counted_as_display`: "Staple" when staple, else the usual size ("Packets · 500 g"), else the count word plural ("Slices"), else "Count" / "Weight" / "Volume". `counts.maybe_same` counts foods with at least one match; `counts.maybe_same_pairs` counts pairs (what the chip shows). Each `maybe_same` entry says which way a merge would go, so every app does the same: `merge_into` is the food that stays, and `merge_this` is true when the food whose list it is would be merged away. The rule: a food without stock goes before one with stock; otherwise the longer name goes ("Drumsticks (moringa)" into "Drumsticks"), and on a tie the newer food goes. The same entries appear in the editor's `maybe_same`. Recipe counts are left out until 0.4.

**`GET /api/v1/foods/{id}`** — the editor:

```jsonc
{
  "id": 7, "name": "Toor dal",
  "other_names": [ { "id": 21, "name": "thuvaram paruppu" }, { "id": 22, "name": "arhar dal" } ],
  "counted_as": "weight", "staple": false,
  "count_word": null, "count_word_plural": null,
  "place": { "id": 3, "name": "Cupboard" },
  "shop": { "id": 1, "name": "Spice Bazaar" },
  "date_kind": "best_before", "date_kind_locked": false,   // 0.8: "use_by" | "best_before"; locked = always Use by
  "sizes": [
    { "id": 12, "name": "packet", "plural": "packets", "amount": 500, "display": "Packet = 500 g", "usual": true, "added_when_shopping": false },
    { "id": 13, "name": "bag", "plural": "bags", "amount": 1000, "display": "Bag = 1 kg", "usual": false, "added_when_shopping": true }
  ],
  "cup_weight": { "grams": 200, "from": "you", "cup_ml": 250 },
  "item_weight": null,
  "running_low_at": { "amount": 250, "unit": "g", "display": "½ packet", "…": "…" },
  "stand_ins": [ { "id": 15, "name": "Moong dal", "both_ways": false } ],
  "stands_in_for": [],
  "maybe_same": [],
  "stock": { "amount": 750, "display": "1½ packets · about 750 g", "…": "…" },   // null until the stock PR
  "last_change": { "id": 790, "summary": "Changed weight of 1 cup to 200 g", "can_undo": true }
}
```

`cup_weight` / `item_weight`: `from` is `you` or `table`; null when neither knows. `last_change` feeds "Undo last change" in the editor (the household's latest undoable change to this food).

A merged-away id returns the food it was merged into (different `id`, plus `"merged_from": {"id": 40, "name": "Drumsticks (moringa)"}`), so old links keep working.

`restocked_at` (0.7 K1, on the list and the editor; writable from 0.7 K5, see PATCH below): when a staple was last restocked (its shopping-list line ticked, and still ticked); null when it isn't a staple or hasn't been restocked yet. A merge keeps the newer of the two stored dates on the ingredient that stays (a ticked line moves across with its tick, so unticking it still puts the date back). With a typed date on either (0.7 K5), the ingredient that stays shows the newer of the two dates shown: it keeps the later typed moment, and a tick that counted but was made before that moment is folded into the kept date, so unticking that one no longer moves the date (a tick made after the moment still does). An Undo of a typed date or a merge never shows a date older than a purchase the tidy-up has deleted since.

**`POST /api/v1/foods`** → `201`

```json
{ "name": "Toor dal", "counted_as": "weight", "place_id": 3, "staple": false }
```
Only `name` is required. `counted_as` defaults from the bundled table match, else `weight`; a table match also makes `cup_weight`/`item_weight` show `from: "table"`. A name already used → `409 name_taken` with `food_id` (the client offers to open that food). Answer: `{ "food": {…editor shape…}, "change": {…} }`.

**`PATCH /api/v1/foods/{id}`** — saves as you go: the client sends **one field per request** as each field is left or switched. Any of:

```jsonc
{ "name": "Toor dal" }
{ "counted_as": "count" }
{ "staple": true }
{ "count_word": "slice" }            // plural made by the server; null clears
{ "place_id": 3 }                     // null clears
{ "shop_id": 1 }                      // null clears
{ "date_kind": "use_by" }              // 0.8: "use_by" or "best_before" (see below); null is refused
{ "running_low_at": { "amount": 0.5, "unit": "packet" } }   // null clears
{ "cup_weight": 200 }                 // grams per household cup; null forgets the household answer
{ "item_weight": 150 }                // grams per item; null forgets
{ "restocked_at": "2026-10-12T09:00:00Z" }   // a staple's restock date (0.7 K5); null is refused
{ "restocked_on": "2026-10-12" }               // the same, as the household's own day
```
`restocked_at` (0.7 K5, additive; one database column, `food.restock_typed_at`, migration `5fbd6d33c434`, keeps the moment a date was typed): only a staple has one (`422 not_a_staple`); never before 2000 (`422 restock_too_old`) and never in the future (`422 restock_in_future`; a clock up to 5 minutes ahead is taken as now); a date before the newest standing "Restocked" tick on Shopping is taken and shown: the date typed wins until a tick made after it (cabledrawer 2 Nov; the earlier `422 restock_before_tick` is gone); null → `422 restock_date_needed`. A foreign or missing food → `404`. The change reads "Rock salt restocked" and is undoable.

The staple's "Restocked" tap is this PATCH with `restocked_on` set to the household's today (the server then stores now).

Each PATCH records one `food_edited` change ("Weight of 1 cup of Toor dal is now 200 g"), undoable. Answer: `{ "food": {…}, "change": {…} }`. If the field already had that value, nothing is recorded and `change` is null. More or fewer than one field → `422 one_field`.

- Changing `counted_as` when the food has stock or sizes converts them; if a conversion is missing → `409 ask_once` (send `answers` alongside the field).
- Turning `staple` on keeps any stock lots but the pantry shows the food as a staple chip only; turning it off shows them again.

**Other names**
- `POST /api/v1/foods/{id}/other-names` `{ "name": "arhar dal" }` → `201 { "other_name": {"id": 22, "name": "arhar dal"}, "food": …, "change": … }`. Same as the food's own name or an existing other name → `422`. Same as **another** food's name is allowed (it then shows under Maybe the same).
- `DELETE /api/v1/foods/{id}/other-names/{name_id}` → `200 { "food", "change" }`.

**Sizes ("How it's sold")**
- `POST /api/v1/foods/{id}/sizes` `{ "name": "bag", "amount": 1000 }` (`amount` in base units; or `{ "name": "bag", "amount": {"amount": 1, "unit": "kg"} }`). First size becomes Usual. With `"usual": true` it becomes the Usual size at once (a tapped pack suggestion, 0.8).
- `PATCH /api/v1/foods/{id}/sizes/{size_id}` `{ "usual": true }` (the others lose it) · `{ "name": "pack" }` · `{ "amount": 400 }` (existing lots keep their base amount; only the display changes).
- `DELETE /api/v1/foods/{id}/sizes/{size_id}`: lots bought in it keep their amount and fall back to the Usual size for display. Deleting the Usual size makes the next one Usual.
- All answer `{ "food", "change" }`.

**Can use instead**
- `POST /api/v1/foods/{id}/stand-ins` `{ "food_id": 15, "both_ways": false }` → Moong dal can stand in for Toor dal. `both_ways: true` adds the reverse too.
- `DELETE /api/v1/foods/{id}/stand-ins/{stand_in_id}` (removes one direction only).

**Maybe the same**
- Matching (offline, no library): two foods match when their normalised names are equal, or one's normalised name equals one of the other's normalised other names. Normalising: lower case, remove accents, remove anything in brackets, collapse spaces, drop a final "es"/"s" from each word (so "Drumsticks (moringa)" ↔ "Drumsticks", "Tomatoes" ↔ "tomato").
- `POST /api/v1/foods/{id}/not-the-same` `{ "food_id": 12 }` → `204`. The pair never shows again. Not logged and not undoable (it only hides a hint).

**Merge, undo merge, split**
- `POST /api/v1/foods/{id}/merge` `{ "into_id": 12, "answers": [] }` → merges food `id` into food `into_id`:
  - its name and other names become other names of `into_id`;
  - its stock lots, sizes and stand-in links move across (same-name-and-amount sizes collapse; self-links dropped); between `weight`/`volume`/`count` the amounts are converted, or `409 ask_once`;
  - `food.merged_into_id` is set and a `food_merge` row recorded; the change's `undo_data` holds a full snapshot.
  - Answer: `{ "food": {…the surviving food…}, "change": { "kind": "merged", "summary": "Merged Drumsticks (moringa) into Drumsticks", … } }`.
- **Undo merge** is the normal Undo of that change (6.5), within the undo window: restores both foods exactly as they were (names, sizes, links, lots with their amounts as they are now, place and dates). If stock was used after the merge, the lots that moved come back with what's left in them, and the result is `partly`.
- `POST /api/v1/foods/{id}/split` `{ "other_name_id": 41 }` → the other name becomes its own food again. If the name came from a merge, the old food is revived (same id, so old links point to it again) with its original settings but no stock (we can't know which stock was its). Otherwise a new food is made with the same settings as the one it's split from, minus sizes and stock. Answer: `201 { "food": {…the new or revived food…}, "change": { "kind": "split", … } }`.

**Remove a food** (section 7, point 1; the summary reads "Removed Toor dal from Ingredients"; what blocks a removal is checked in one place, `cannot_remove`, where shopping lists (0.3) and recipes (0.4) will be added): `DELETE /api/v1/foods/{id}` only when it has no stock (and, from 0.4, no recipe uses it); otherwise `409 in_use`. Soft delete, undoable (`food_removed`). Answer: `{ "food": null, "change": {…} }`. After the undo window (7 days, plus an hour so it can't vanish while Undo is still offered) the ingredient is deleted for good by an hourly job (`mealwright/jobs.py`, also run just after start-up): its other names, sizes, "can use instead" links, remembered answers, "not the same" pairs, emptied packets, per-packet history lines and monthly totals go with it, and so do ingredients that were merged into it (they only existed to lead to it) with their merge history. Every change in the history keeps its sentence ("Used 500 g Toor dal", "Removed Toor dal from Ingredients") and who made it; only its link to the ingredient (`food_id`) is cleared, so it shows with no `lines` or `totals`. If an Undo puts stock back into an ingredient that has since been removed (undo "Used 100 g Ghee" after removing Ghee), the ingredient comes back to the list, and the Undo's `message` says so: "Ghee is back in Ingredients, with 100 g in the Cupboard." The Undo records it (`brought_back`), and the answer lists them as `brought_back: [{id, name}]` so the web app can say "Undone: Used about ½ tub Yogurt. Yogurt is back in Ingredients, with ½ tub in the Fridge." As a safety net, the purge never deletes a packet that still holds something: it brings that ingredient back instead and logs a warning, without names.

**Pack sizes and where to buy (0.8, F120, F121; cabledrawer 7 Nov).** The bundled table `data/pack-sizes.csv` (Mealwright's own, 369 ingredients) gives common sizes and where each is bought.

- `FoodOut.pack_suggestions` (the editor, and every food write): `[{ "pack": "jar" | null, "name": "jar", "amount": 500, "display": "jar · 500 g" }]`, `amount` in base units. Matched by the name or any other name; no match gives the generic sizes by kind (100 · 250 · 500 · 1000 g, 250 · 500 · 1000 ml, 1 · 2 · 6 · 12); `name` is the table's word, else "pack". Sizes in another kind are converted when the density is known, else skipped. A size the food already has is left out; a staple has none. A tap makes one the Usual size: `POST /foods/{id}/sizes` with `name`, `amount` and `"usual": true`.
- `GET /foods` rows add the Pack column: `pack` (the Usual size, a `SizeOut`, else the first), `more_sizes` (the others, for "+1" and its hover or tap) and, only when the food has no size at all, `pack_suggestions`.
- `POST /foods` with no `shop_id` pre-fills the Usual shop from the table's "where": specialist → the first shop whose name mentions a kind of grocer (Indian, Chinese, Japanese, Asian, Middle Eastern, Arabic, Turkish…), else the first shop that isn't a supermarket, else none; supermarket and world aisle → the first shop in Settings order; no table row → none. A `shop_id` in the request (even null) is never replaced. Another household's shop is a 404.

**Starter ingredient packs (0.8 R4; cabledrawer 7 Nov).** Bundled and read-only: `data/starter-packs.csv` (key, name, packs) says which rows of the pack-size table are in which pack. Nothing is downloaded; ingredients only, never stock or list items.

- `GET /starter-packs` → `{ "packs": [{ "id": "indian", "name": "Indian", "already_have": 3, "items": [{ "key": "toor_dal", "name": "toor dal", "already_have": true, "have_as": "Thuvaram paruppu" | null, "staple": false }] }] }`. Seven packs, in this order: `everyday-basics`, `indian`, `chinese`, `japanese`, `middle-eastern`, `household`, `baking`. An item is `already_have` when the household has an ingredient with its name or any of its other names (ignoring case and accents); `have_as` says what the household calls it when that isn't the item's name. `staple` is true for Household items.
- `POST /starter-packs/{id}/add` `{ "keys": ["toor_dal", "ghee"] }` → `201 { "added": 41, "skipped": 2, "change": {…} }`. Each key must be one of the pack's, else `422 not_in_pack`; an unknown pack is a 404. Items the household already has are skipped (`skipped`), not an error; if none are left, `422 nothing_to_add`. Each new ingredient gets how it is counted (the conversion table's, else the kind of its first pack size), its aisle (the pack-size table's `aisle` column, cabledrawer 7 Nov; Household-pack items too, never the Household aisle), its Usual shop (as for `POST /foods` with no `shop_id`), its other names from the pack-size table, and `staple: true` for Household items. Its usual pack sizes are the suggestions of 6.2 (matched by name). One `food_created` change, "Added the Indian starter pack: 41 ingredients", so one Undo (6.5) takes the whole addition away; it carries `Idempotency-Key` like any write (the same key again gives `200` and the original answer).

### 6.3 Places, shops, household

- `GET /api/v1/places` → `[{ "id": 1, "name": "Fridge", "kind": "fridge" }, …]` in order.
- `PATCH /api/v1/places/{place_id}` `{ "name": "Spices" }` → the place (`{ id, name, kind }`). Renames only: the `kind` (and so the rules) stays. Tidied, 1 to 40 characters; a name another place has (ignoring case) → `409 place_exists` with `place`. Anyone in the household can (Settings → Shops & places, 0.8, cabledrawer 7 Nov). Not logged as a change.
- `PUT /api/v1/places/order` `{ "ids": [3, 1, 2, 4] }` → the places in their new order. `ids` must be every one of the household's places, once each (else `422 not_all_places`). Not logged.
- `DELETE /api/v1/places/{place_id}?move_to=<place id>` → `{ "change": … }` (kind `place_removed`, which carries the Undo). A place with packets or tubs that have something left in them → `409 place_not_empty` with `things` (how many) and the words "Cupboard has 14 things in it. Move them to…"; send `move_to` (another place of the household; itself → `422 same_place`) and the packets and tubs go there, as do the places ingredients are usually kept in; then the place goes. The last place of the `fridge` kind and the last of the `freezer` kind can't go: `409 last_of_kind`. What else pointed at the place (empty packets kept for Undo, the log lines of earlier changes) goes to `move_to`, or with none to another place of the same kind. Undo makes the place again with its old id and puts back what it moved, each row only if it still points where the removal put it; if a newer place has taken the id, `409 cannot_undo`. Anyone in the household can; Idempotency-Key supported.
- `POST /api/v1/places` `{ "name": "Garage fridge", "kind": "fridge" }` → `201` with the new place (`{ id, name, kind }`), put last in the order (cabledrawer 31 Oct, F101 "+ Place": type a new place wherever a place is picked). `kind` is `fridge`, `freezer` or `cupboard` and drives the rules ("freezer last"); anything else is `422`. The name is tidied and 1 to 40 characters. A name the household already has (ignoring case) → `409 place_exists` with `place` (that place), so the screen just picks it. Only the household's own places are looked at. Members may add one. A household has at most 50 places: past that, `409 too_many_places` with a plain reason (cabledrawer 1 Nov: "at most 50 places per household"). Not logged as a change, like "+ Shop"; there is no Undo.
- `GET /api/v1/shops` → `[{ "id": 1, "name": "Tesco" }, …]`.
- `PATCH /api/v1/shops/{shop_id}` `{ "name": "Lidl" }` → the shop (`{ id, name }`). A name another shop has (ignoring case) → `409 shop_exists` with `shop`. Anyone in the household can. Not logged.
- `PUT /api/v1/shops/order` `{ "ids": […] }` → the shops in the order you visit them (every shop once, else `422 not_all_shops`). Not logged.
- `DELETE /api/v1/shops/{shop_id}` → `{ "change": … }` (kind `shop_removed`). The ingredients that had it as their usual shop go to "Any shop", and so do the lines to buy in it (the same Undo steps as changing an ingredient's usual shop). Undo makes the shop again with its old id and aisle order and puts everything back; if a newer shop has taken the id, `409 cannot_undo`. Anyone in the household can; Idempotency-Key supported.
- `POST /api/v1/shops` `{ "name": "Lidl" }` → `201` with the new shop, or `200` with the existing one if the name is already used (ignoring case), so "+ Shop" never makes duplicates. Not logged as a change.
- `GET /api/v1/household` → `{ "name": "Home", "time_zone": null, "cup_ml": null, "cup_ml_used": 250, "undo_days": 7, "history_months": 12, "use_soon_days": 2, "tub_fridge_days": 3, "tub_freezer_months": 3, "plan_ahead_days": 7, "week_starts_on": 1, "today": "2026-10-17" }`.
- `GET /api/v1/household` also has `"pints": "uk"` (0.6 PR 7). `PATCH /api/v1/household` `{ "pints": "us" }` (admins only, else `403 admins_only`; only what is sent changes; anything but `uk` or `us` is `422`) changes it and answers with the settings as stored. `{ "cook_per_step": true }` (0.7 K4) turns Cook mode's per-step ingredients on or off; any signed-in person of the household may send it (a member too; cabledrawer 1 Nov: "anyone in the household can flip the per-step switch"), while `pints` stays admins only; anything but true or false is `422`. A request carrying both is refused with `403` for a member and changes nothing. `GET /api/v1/household` has `"cook_per_step": false` by default.
- `POST /api/v1/household/from-browser` (admins only, else `403 admins_only`) `{ "time_zone": "Europe/London", "cup_ml": 250 }`. Each value is stored **only while the household has none** (cabledrawer 17 Oct, spec section 6): once set it is never changed silently, so an admin opening the app from abroad changes nothing. Always answers `200` with the settings as stored (the household shape above). A zone that isn't `UTC` or an Area/City name from `zoneinfo` (so not `localtime`, `Factory` or `posixrules`) or cup not 240/250 → `422`. Changing them on purpose comes with Settings (0.8), on a separate endpoint the web app never calls automatically.
- **After sign-in:** if `time_zone` or `cup_ml` is null and the login is an admin, the web app sends `{ "time_zone": <Intl.DateTimeFormat().resolvedOptions().timeZone>, "cup_ml": <240 if navigator.language is en-US, else 250> }`. Existing 0.1 installs fill it in on the first admin visit after updating. Members never send it. Never location.

### 6.3a The plan (0.6)

Tables (all with `household_id`; links between them are composite keys, so they can't reach into another household): `meal_slot` (`name`, `position`, `enabled`), `meal` (`day`, `slot_id`, `status` planned · cooked · didnt · moved; one per day and slot), `meal_item` (`meal_id`, `position`, `kind` recipe · tub · ingredient · note, one of `recipe_id` / `tub_id` / `food_id` to match, or none for a note (0.7 P1: its text is in `name`), `name` (the recipe's or ingredient's name, copied when the item is added and refreshed when it is deleted for good), `servings` only with a recipe), `batch_cook` (`recipe_id`, `recipe_name`, `cook_meal_id` (the meal it was cooked for, null if none; deleting that meal clears it first, in `mealwright/plan.py`), `cooked_on`, `tub_count`, `pattern` lunches · lunch_dinner · dinners · pick, `prep_note`, `colour`) and `tub` (`batch_id`, `amount_quarters` 0 to 4, `place_id`, `member_login_id`, `use_by`). Default slots: Breakfast, Lunch, Snack (off), Dinner. Deleting: a slot with meals can't be deleted (hide it); a recipe or ingredient deleted for good leaves its meal item with its name, so past meals still show what was eaten (cabledrawer 26 Oct, as batch cooks keep theirs); a tub deleted for good takes its meal item (the meal stays); a batch cook outlives its recipe, by `recipe_name`; deleting a batch removes its tubs.

- `GET /api/v1/meal-slots` → `[{ "id": 1, "name": "Breakfast", "position": 0, "enabled": true }, …]`, hidden ones too.
- `GET /api/v1/plan?from=2026-11-02&to=2026-11-08` → `{ "start", "end", "meals": [{ "id", "date", "slot_id", "status", "items": [{ "id", "position", "kind": "recipe"|"tub"|"ingredient", "recipe": {"id","name","removed"}|null, "tub_id", "ingredient": {"id","name","removed"}|null, "kept_name", "servings" }] }], "batch_cooks": […], "tubs": […] }`. Batch cooks are those whose tubs sit in these meals, those cooked for these meals (`cook_meal_id`) and those cooked on a day in the range; tubs are those in these meals and those of the batches. A batch's `recipe_id` and a tub's `place_id` and `member_login_id` are shown only when they belong to the household. Merging ingredients moves plain-ingredient items too (and Undo or Split moves them back). `kept_name` is set only when the item's recipe or ingredient was deleted for good (`recipe` and `ingredient` are then null). More than 62 days → `422 range_too_long`; `to` before `from` → `422 bad_range`.

**Writing the plan (0.6 PR 3).** Online only, like the Pantry: nothing here is in the offline queue. Every write takes the household's lock, honours `Idempotency-Key` (a retry answers `200` with `Idempotent-Replayed: true` and plans nothing more), records one change with its **Undo** (`POST /changes/{id}/undo`), and answers `{ "change": {…}|null, "meal_id", "item_id" }`; read the plan again to draw it. Every id that arrives (recipe, ingredient, meal, item, meal slot) must belong to the household, else `404` as if it did not exist. A meal that is no longer `planned` (cooked, didn't, moved: Today's, PR 6) is refused with `409 meal_done`. Days further than a year back or two years ahead of today are refused (`422 bad_day`; cabledrawer 26 Oct).

- `POST /api/v1/plan/items` `{ "date", "slot_id", "recipe_id" | "ingredient_id", "servings"? }` → `201`. Exactly one of `recipe_id` / `ingredient_id` (else `422 one_of`). An empty date and slot gets a new meal; a filled one gets it alongside (at the end). A switched-off slot → `422 slot_off`. Change kind `plan_added`.
- `DELETE /api/v1/plan/items/{plan_item_id}` takes one thing out of a meal; a meal left empty goes too (Undo puts both back, and the batch cook that was cooked for it points at it again). `DELETE /api/v1/plan/meals/{plan_meal_id}` takes the whole meal off. Kind `plan_removed`.
- `POST /api/v1/plan/meals/{plan_meal_id}/move` and `POST /api/v1/plan/items/{plan_item_id}/move`, body `{ "date", "slot_id", "mode": "move" | "copy" | "leftovers" }` (`move` if left out). A meal moved to an empty date and slot keeps its id; onto a filled meal its things go in alongside and the old meal goes. `copy` leaves the first where it was; a tub is in one meal at a time, so it is never copied (a meal with only tubs → `422 nothing_to_copy`, a tub on its own → `422 tub_once`). `leftovers` does the same as `copy` for now: real leftover tubs arrive with Cook once (PR 4; cabledrawer 26 Oct). Dropping on the very place it is in → `422 same_place`. Kinds `plan_moved`, `plan_copied`, `plan_leftovers`. **A cook meal (0.7 P3; proposed, for cabledrawer):** moving the meal of a batch's cooking (`mode: "move"`, to an empty date and slot) also moves the batch's `cooked_on` to that day and shifts every one of its tubs' `use_by` by the same number of days; Undo puts every date back exactly, but only when the meal is back where it was and the batch has not been cooked since (otherwise the Undo says "partly" and leaves the dates). `POST /plan/items/{id}/move` of that recipe (move) moves its whole meal. Refusals: `409 already_cooked` ("This was cooked on Thu 15 Oct. Undo “Cooked it” first.") when the batch has a cooked record; `409 cooking_needs_empty_meal` ("Cooking can only move to an empty meal.") onto a meal that is already planned; `422 too_many_batches` when the new day already has 10 batches. `copy` and `leftovers` of a cook meal change nothing about the batch. `POST /plan/tubs/{id}/place` onto a day after the tub's `use_by` → `422 after_use_by`.
- `PATCH /api/v1/meal-slots/{plan_slot_id}` `{ "enabled": true|false, "name": "Supper" }` (either or both; neither → `422 nothing_to_change`): the "Meals" switches, and (0.8, Settings → Meal slots) renaming. **Admins only** (`403 admins_only`, cabledrawer 7 Nov). A name another meal has (ignoring case) → `409 slot_exists`. A rename's change is kind `plan_slot` ("Renamed Lunch to Midday meal") with an Undo. The planned meals stay with the meal.
- `POST /api/v1/meal-slots` `{ "name": "Supper" }` → `201` with the new meal (`{ id, name, position, enabled }`), last and switched on. Admins only. At most 12 meals (`422 too_many_slots`); a name already there → `409 slot_exists`. Not logged. There is no removing: switch it off (its meals are kept).
- `PUT /api/v1/meal-slots/order` `{ "ids": […] }`: the meals in this order (every one once, else `422 not_all_slots`). Admins only. Kind `plan_slot` ("Changed the order of the meals") with an Undo; already in that order → `change: null`.
- (The switch, as before:) Meals already planned in a hidden slot are kept. Already that way → `change: null`. Kind `plan_slot`.
- **Caps (cabledrawer 26 Oct): 20 things in a meal (`422 meal_full`) and 12 meal slots.** `GET /plan` hands lists of ids to the database, and SQLite takes at most 32,766 values in one query; 62 days × 12 slots × 20 items = 14,880 stays well under. A test keeps that sum honest.
- **Undo** puts the plan back as the change found it, newest step first. A step that no longer fits (the spot has been filled since, a recipe is gone for good, the meal is full) is skipped and the answer says `partly` or `nothing`, like the pantry's Undo.
- **Added to `GET /plan` in PR 3:** each item's `recipe` also has `photo_url` (the small photo, or null), `time_minutes` and `kcal` (per serving, null when unknown); each meal has `kcal` (one serving of each recipe, and of the recipe a tub came from, added up; null when none has kcal; cabledrawer 26 Oct); each tub has `number` ("tub 2 of 4": 2, in the order the batch made them).

**Cook once, eat for… and tubs (0.6 PR 4).** Online only; every write takes the household's lock, honours `Idempotency-Key`, records one change with its **Undo** and answers a plan write (`{ "change", "meal_id", "item_id", "batch_id" }`). Every id (item, batch, tub, slot, login) must belong to the household, else `404`. No database change.

- `POST /api/v1/plan/items/{plan_item_id}/batch/preview` and `POST /api/v1/plan/items/{plan_item_id}/batch` (`201`), body `{ "tub_count": 1–12, "pattern": "lunches"|"lunch_dinner"|"dinners"|"pick", "member_login_ids": [], "extras_to_freezer": false, "prep_note"?, "placements"? }`. The item must be a recipe that is still there, in a `planned` meal (`422 not_a_recipe`, `409 meal_done`); the meal may have one batch of that recipe (`409 batch_exists`). The automatic patterns fill the next meals that are on, after the cook meal, whose slot name has "lunch" or "dinner" in it, and skip meals that already have food or were dealt with, looking 28 days ahead; the cook meal itself is not filled. Tubs not in a meal ("tubs left") are in the fridge, or the freezer with `extras_to_freezer` (`422 no_freezer` if there is none). `placements` is the person's own choice, one entry per tub in order, each `{ "date", "slot_id" }` or `null` (not in a meal); left out, the pattern picks (a wrong length → `422 bad_placements`; a full meal → `422 meal_full`). `member_login_ids`: one login makes every tub theirs, several go round in turn, none means nobody in particular. Use-by: fridge days / freezer months from the household's settings, from the cook day. Colour: the first palette name (`purple`, `amber`, `green`, `blue`, `rose`, `teal`) no batch cooked within two weeks of the cook day uses. Caps: 12 tubs in a batch (`422 too_many_tubs`) and 10 batches cooked on a day (`422 too_many_batches`).
  - The preview changes nothing and answers `{ "recipe_id", "recipe_name", "recipe_serves", "cook_date", "cook_meal_id", "colour", "tubs": [{ "number", "date", "slot_id", "place_kind", "place_id", "member_login_id", "use_by", "meal_has_food" }], "placed", "per_tub": { "kcal", "protein_g", "fibre_g" } }`. The screen sends `placements` back after the person adds, removes or moves a tub. Saving answers the same as other plan writes plus `batch_id`; kind `plan_batch` (Undo takes the batch, its tubs and their places in meals).
- `DELETE /api/v1/plan/batches/{plan_batch_id}`: the batch, its tubs and their places in meals go; a tub in a meal that was cooked → `409 meal_done`. Kind `plan_batch_removed`; Undo brings all back, with the same ids.
- `POST /api/v1/plan/tubs/{plan_tub_id}/place` `{ "date", "slot_id", "from_tubs_left"?: false }`: put a tub in a meal; a tub already in a meal moves (it is in one meal at a time). With `"from_tubs_left": true` (the web app sends it whenever it puts a tub from tubs left: the Pantry's and Cooked it's "Eat it on…", and the Plan's sheet, Add panel and drag) a tub already in a meal is refused instead, `409 tub_taken` "That tub is already planned for another meal." A tub with nothing left → `422 tub_eaten`. To send a tub back to "tubs left", `DELETE /api/v1/plan/items/{id}` on its meal item (the tub stays; the change summary says "Put Veg biryani tub back in tubs left from …"). Kind `plan_tub`.
- `PATCH /api/v1/plan/tubs/{plan_tub_id}` `{ "member_login_id"?: id | null, "use_by"?: date }`: "Whose tub?" and the use-by; only what is sent changes; nothing to change → `change: null`; nothing sent → `422 nothing_to_change`. Kind `plan_tub`.
- `POST /api/v1/plan/tubs/{plan_tub_id}/freezer`: the tub leaves its meal, goes to the first freezer place and gets a use-by of the household's freezer life from today (`409 already_frozen`, `422 no_freezer`, `422 too_late_to_freeze`: a tub whose use-by date has passed, from the day after, as for a packet; cabledrawer 8 Nov). Kind `plan_tub`.
- `POST /api/v1/plan/fill-from-freezer` `{ "from", "to" }` (at most 62 days): each day in the range with nothing planned gets a tub from the freezer, soonest use-by first, in the last meal that is on; days with a meal that was dealt with are left, and so are days too far from today to plan (Month's grid runs into next month). Nothing to fill → `change: null`. Kind `plan_tub`.
- `GET /api/v1/plan/tubs-left?limit=100` → `{ "tubs": [{ "id", "batch_id", "number", "tub_count", "recipe_name", "colour", "cooked_on", "amount_quarters", "place_id", "place_kind", "member_login_id", "use_by" }], "more" }`: tubs in no meal that still have some in them, soonest use-by first.
- `GET /api/v1/plan/people` → `[{ "login_id", "name" }]`: who can be eating (the household's logins until member profiles in 0.8).
- **What was cooked (0.7 K1).** `GET /api/v1/plan/items/{plan_item_id}/cooked` and `GET /api/v1/plan/batches/{plan_batch_id}/cooked` → `{ "id", "meal_item_id", "batch_id", "recipe_id", "portions", "snapshot": { "name", "version", "servings", "lines": [{ "kind", "words", "amount_milli", "unit", "size_id", "size_name", "size_plural", "size_amount_milli", "size_unit", "food_id", "food_name", "recipe_id", "recipe_name", "note" }], "steps": [{ "kind", "text" }] }, "change_id", "cooked_at", "cooked_by": { "login_id", "name" } }`. Read-only: "Cooked it" writes it (later in 0.7). The snapshot is the recipe as it was cooked, with the recipe's own amounts for `servings` (thousandths: 1½ is 1500); a line in one of the ingredient's sizes ("1 packet") keeps that size's name, plural and amount as they were (`size_unit` `g` or `ml`, null for a count), so renaming or deleting the size later changes nothing; `portions` is how many were cooked. It stays the same when the recipe is edited, and stays when the recipe is deleted for good (`recipe_id` becomes null). `change_id` is the change with its stock changes (null once the tidy-up has deleted it). Not cooked yet → `404 not_cooked`; an item or batch of another household → `404 not_found`.
- **"Leftovers" now makes a tub** (`mode: "leftovers"` on the move routes): a recipe in the meal becomes a tub of the batch cook cooked for that meal (made on the spot, `pattern: "pick"`, if there is none; a spare tub in no meal is used first, else a new one up to the cap, `422 batch_full`); a plain ingredient is copied; a tub is not (`422 tub_once`, `422 nothing_to_copy`). A meal with several recipes makes a tub of each (proposed, for cabledrawer).
- **A "Note" plan item (0.7 P1).** `POST /api/v1/plan/items` also takes `{ "date", "slot_id", "note": "Eating out" }` (exactly one of `recipe_id`, `ingredient_id`, `note` → else `422 one_of`; the note is 1 to 200 letters on one line (refused with "A note can be up to 200 letters.", cabledrawer 2 Nov), spaces tidied, hidden characters refused). `GET /plan` gives such an item `kind: "note"` and `note` (the text; `kept_name` stays for a recipe or ingredient deleted for good). A note counts as a filled meal (the patterns of Cook once and Fill from freezer first skip it), needs nothing bought, and a planned meal of only notes is not asked about on Today (a recipe beside a note is). It moves and copies like any item; it has no leftovers (`422 note_no_leftovers`; a whole meal's leftovers leave it out). Database: migration `e0c4a7b19d35` widens `meal_item`'s "exactly one of" rule; going back removes the notes.
- **Cooked per recipe (0.7.0, F157; cabledrawer 6 Nov).** Added to `GET /plan`: each item has `cooked` (true when its meal is cooked, when the item has its cooked record, or, for a Cook once batch's recipe in its cook meal, when the batch has one). `POST /plan/meals/{id}/cooked` makes the meal `cooked` only when every recipe the review can cook has been cooked (or when the answer comes with no pantry change, as before 0.7); otherwise the meal stays `planned`, and the answer's summary names only what that press cooked. The Undo of a press that takes away a record of a `cooked` meal puts it back to `planned`.
- **Serves - N + and who's eating (0.7 P1; cabledrawer 28 Oct, F57).** Added to `GET /plan`: each item has `eating` (how many people the recipe is for now: its own `servings` once set; else the recipe's Serves, which is what a meal planned before 0.7 means; one for the cook meal of a batch, as Cook once and the list count it; null for anything but a recipe, and for a recipe with no Serves) and each meal has `eater_login_ids` (the logins ticked, by sign-in until member profiles in 0.8; **empty means everyone**; proposed, for cabledrawer). Both are online-only plan writes with the household's lock, `Idempotency-Key` and an Undo:
  - `PATCH /api/v1/plan/items/{plan_item_id}`, body `{ "servings": 1 to 99 }`. Amounts and the shopping list follow. Already that number → `change: null`. Not a recipe → `422 not_a_recipe`; a meal already dealt with → `409 meal_done`. Kind `plan_servings`; Undo puts the old number back, which for a meal planned before 0.7 is "none set".
  - `PUT /api/v1/plan/meals/{plan_meal_id}/eaters`, body `{ "login_ids": [] }` (up to 20; replaces the whole list; a login that is not the household's → `404`). Kind `plan_eaters`. The list goes with the meal (and comes back with the Undo of removing it) and stays with a moved meal.
  - Database: migration `f27b95d1c8a3` adds `meal_eater` (`household_id`, `meal_id`, `login_id`; one row per person ticked; the link to the meal includes `household_id`; goes with its meal or login).
- **Portions and "Leftovers on…" (0.7 P1; cabledrawer 28 Oct).** A batch makes a fixed number of portions: its tubs plus the cook-day meal (the cook meal's `servings`, else one, as Cook once and the shopping list count it). A portion is **left** while its tub is in no meal and not eaten. Added to `GET /plan`: each batch has `portions` and `portions_left`. No database change; online only like the rest of the plan.
  - `GET /api/v1/plan/items/{plan_item_id}/portions` → `{ "recipe_name", "has_batch", "batch_id", "portions", "cook_day", "tubs", "in_meals", "left", "use_by" }`. Changes nothing. With no batch cook yet, `has_batch` is false and the counts are null (the first leftovers make the batch); `use_by` is then the cook day plus the household's fridge life. `use_by` is the last day a tub of the batch can go in a meal: the latest use-by of a tub still to place, else the fridge life from the cook day. A tub, ingredient or note → `422 not_a_recipe`.
  - `POST /api/v1/plan/items/{plan_item_id}/leftovers`, body `{ "meals": [{ "date", "slot_id" }] (1 to 12), "if_none_left": "ask" | "cook_more" | "add_anyway" }` (default `ask`). Several meals at once; each must be after the cook meal and today or later (`422 not_after_cook`, as F50) and not after the batch's `use_by` (`422 after_use_by`); `422 same_meal_twice`. The earliest meals take the portions left. For the rest: `ask` changes nothing and answers `409 no_portions_left` with `left` and `wanted`; `cook_more` grows the batch by a tub for each (up to 12, `422 batch_full`; amounts and the shopping list follow, as Cook once does); `add_anyway` plans the recipe in those meals for one serving and leaves the batch as it is. With no batch yet the batch is made, one tub per meal. One change (kind `plan_leftovers`) with one Undo; retries with the same `Idempotency-Key` plan nothing more. Two phones taking the last portion: the first gets it, the second gets `409 no_portions_left`.
  - **A tub is never planned past its use-by (F50).** Each meal takes the spare tub with the earliest use-by that is on or after its day; a meal no spare tub reaches counts as "none left" for that meal. `GET .../portions` adds `spare_use_by` (the use-by of each spare tub, soonest first) so the sheet counts the same way; `left` is still the number of spare tubs. A new fridge tub (Cook more) can't go past its own use-by either (`422 after_use_by`).
  - **The one-day routes ask too (lead's call; proposed, for cabledrawer).** `POST /plan/items/{id}/move` and `POST /plan/meals/{id}/move` with `mode: "leftovers"` (the drag zone "Leftovers here", the one-day picker for a meal of several things) take `if_none_left` like the route above, default `ask`: a recipe whose batch has no spare tub reaching that meal answers `409 no_portions_left` and changes nothing. A recipe with no batch yet still makes one. The screens show the same "No portions left" alert with Cook more or Add anyway.
- **Added to `GET /plan`:** a tub has `place_kind` (`fridge`, `freezer`, `cupboard` or null); a batch's `colour` is a palette name. The batches, tubs, recipes and ingredients a range needs are asked of the database as subqueries, never as lists of ids, so their number can't push a query over SQLite's 32,766 values (a test reads a plan with SQLite allowed only 60).

### 6.3b The shopping list from the plan (0.6 PR 5)

The main shopping list is built from the plan: plan minus pantry stock minus staples, with "Can use instead" stand-ins counted. Plan-made lines are ordinary list lines with `source: "plan"` (read and changed like any other: `GET /shopping/...`, the sync protocol). The rules (all in `mealwright/shop_from_plan.py`, with the builder's choices marked "proposed, for cabledrawer"):

- **What counts:** recipe items of meals with status `planned`, in a slot that is on, from today for the household's `plan_ahead_days` (7 unless changed; the list never asks). A recipe item is worked out for its `servings` (its own "serves" when none); a batch cook's cook meal is worked out for those servings plus one per tub (the people at the cook meal eat too; a Leftovers batch has one tub; proposed, for cabledrawer). Tubs, plain ingredients and inner recipes add nothing. Staples never go on the list.
- **Stock:** all pantry stock, every place. A stand-in covers what the ingredient's own stock doesn't, when it is counted the same way; one pack of stock covers one ingredient. Stock past its use-by date still counts (proposed, for cabledrawer). A line whose amount can't be compared counts any stock as enough; with none in stock the ingredient is listed with no amount. An ingredient whose line or total is over the list's largest amount (1,000,000) is listed with no amount (proposed, for cabledrawer). Amounts are rounded up: whole g or ml, halves of a count.
- **Keys and edits:** a plan line is matched by (main list, ingredient, the ingredient's usual shop or Any shop). Only a line that is not hand-edited and not ticked is changed (rule L-5). A typed line for the same ingredient and shop covers the need. A line the plan no longer needs is removed with a tombstone; one a person removed stays removed while the plan needs no more than the amount they removed, and only for `plan_ahead_days` days after the removal; if the need grows past that amount, or the window passes, a new line is made (the window and the "need grows" rule are proposed, for cabledrawer). A plan line a person moved to another list, or onto a line at another shop, counts as meeting the need there.
- **When:** after every plan or batch write (and its Undo), and when Shopping opens. Each change takes one counter number from `household.list_seq`, stamps the lines it touched with it, and is one `sync_action` row of kind `plan_update` (`login_name` "The plan", no device; payload `{created, changed: [[id, old, new]], removed}`, amounts in base units). Nothing to change takes no number. Phones and live updates see it like any other list change.
- `POST /api/v1/shopping/from-plan` → `{ "days", "from_plan", "changed", "staples": [{ "food": {"id","name"}, "used_in": ["Sambar", …] }] }`. Brings the main list up to date and gives back the staples card. Safe to repeat.
- `PUT /api/v1/shopping/staples/{food_id}/got-it` → the same answer. "Got it": the staple stays off the card until a planned meal item that was not there when it was said uses it (the ids of the meal items that used it then are kept in `staple_check`, one row per ingredient; meals going, or days passing, never bring it back; proposed, for cabledrawer). `DELETE` on the same address is its Undo. `404` for an ingredient that isn't this household's.
- "+ Add" on the card is the ordinary `add` action (a typed line); the card then leaves out any staple that has a live line on the main list.
- **Database:** one new table, `staple_check` (`food_id` primary key, `household_id`, `item_ids` (JSON list), `at`; both links cascade). Migration `a4c8e1f7b296`.

**What to buy in whole packs (0.8, F120; cabledrawer 31 Oct and 7 Nov).** Each list item (`ItemOut`, and the sync pull's item rows) has `pack`, or null when there is nothing to say (no amount, a staple, or a counted ingredient with no size): `{ "packs": 1, "size_id": 12, "buy": "1 jar (500 g)", "need": "120 g needed", "line": "1 jar (500 g) · 120 g needed", "suggestions": [] }`. `packs` is the fewest whole packs of the Usual size that hold the need (`ceil(need / size)`, so packs × size ≥ need and (packs − 1) × size < need). With no size known: `packs`, `size_id`, `buy` are null, `line` is "60 g needed · no pack size yet", and `suggestions` are the common sizes ("Usual pack?"; the shape of `pack_suggestions` in 6.2, with `amount_text` "500 g" for the quick pick). The amount stored on the line stays the need.

**Why an item is on the list (0.8, S3 Plan shopping; cabledrawer 6 Nov).** Each list item in the online API (`ItemOut`: the list read and every item write; not the sync pull. The phone reads the list over this online API, so S4 adds nothing to the pull for it) has `why`, a ready-made string, worked out when the list is read from the plan (nothing is stored; no new column): the planned recipes that need the ingredient and their days, `"Sambar (Tue, Thu) · Rasam (Fri)"` (recipes in the order of their first day; days Mon to Sun; a recipe used inside a planned recipe shows as the planned one), or `"Added by you"` for a typed item. `"120 g needed · "` comes first when the pack to buy is bigger than the need, and `" · no pack size"` last on a plan item with no Usual size. A plan item the plan no longer explains says `"From the plan"`.

**"Make it a staple?" (0.8, S3; cabledrawer 7 Nov).** `ItemOut.staple_offer` is true for a line whose ingredient is not a staple, is Best-before (its row in `data/pack-sizes.csv` has `dates` = "best before"; no row or "use by" never) and whose amount is under a twentieth of its smallest known pack (the household's sizes and the table's, in the ingredient's own unit). The screen offers one tap that makes it a staple (`PATCH /foods/{id}` `{ "staple": true }`), with Undo.

**Recipes inside recipes on the list (0.8, S3).** The list works through a line that uses another recipe: one batch of that recipe's ingredients at its own amounts (scaled with the outer recipe's servings), at any depth, unless the recipe is made ahead and enough of its own pantry ingredient is in stock (with no amount to compare, any stock counts). Proposed, for cabledrawer: one batch per line.

**A new ingredient's aisle (0.8, F54).** An ingredient made without an aisle (typed on Shopping, imported with a recipe, or `POST /foods`) takes the aisle of the bundled table's row for its name, else of a table name found inside it as whole words ("Organic basmati rice" takes basmati rice's), else "other".

### 6.3c Today (0.6 PR 6)

What Today shows, and the three answers to "Did you cook Sambar yesterday?". Online only, like the Plan (the web app keeps the last answer to show while offline, with the answer buttons switched off). "Today" is the household's local day. The rules are in `mealwright/today.py`; the builder's choices are marked "proposed, for cabledrawer" there.

- `GET /api/v1/today` → `{ today, first_day, slots, plan, people, waiting, tubs_left, tubs_left_more, use_soon_lots, use_soon_tubs, next_cook }`.
  - `slots`: the meals that are on, in order. `plan`: the same shape as `GET /plan`, from 7 days ago to 6 days ahead (a week from today; the meals, their items, and the batch cooks and tubs they use). `people`: as `GET /plan/people`.
  - `waiting`: planned meals on days before today, back 7 days (`WAITING_DAYS`), in a slot that is on, newest first (later meals of a day first): `{ meal_id, date, slot_id, leftover_item_id, use_by_fridge, use_by_freezer }`. `leftover_item_id` is the meal's first recipe (what "Any left over?" is about), or null when the meal has no recipe. The two dates are the use-by a new tub would get, from the meal's day.
  - `tubs_left`: as `GET /plan/tubs-left` (up to 200; `tubs_left_more` says there are more). `use_soon_lots`: as `GET /pantry/use-soon`. `use_soon_tubs`: the tubs left whose use-by is within the household's Use soon days.
  - `next_cook`: the first batch cook from today on whose cook meal is still planned: `{ date, slot_id, meal_id, batch_id, recipe_name, tub_count }`, or null.
  - `first_day`: true when the household has no recipe (not removed), nothing in the pantry and no meal ever planned. The web app then shows "Your kitchen is ready".
  - The shopping list's "to buy" count and the "Did you buy 2?" cards come from the shopping list's own copy, as on Shopping.
- `POST /api/v1/plan/meals/{plan_meal_id}/cooked`, body `{ "leftovers"?: { "count": 1 to 12, "place_kind": "fridge" | "freezer", "use_by"?: date, "item_id"?: id } }`. The meal becomes `cooked` and is locked. With `leftovers`, tubs are made of one recipe in the meal (`item_id`, else its first recipe) in the meal's own batch cook (made if there is none), in the fridge or freezer, with the given use-by or the household's tub life counted from the meal's day. They are in no meal, so they are "tubs left". **Nothing is taken from the pantry:** that is the "Cooked it" review in 0.7.
- `POST /api/v1/plan/meals/{plan_meal_id}/didnt`: the meal becomes `didnt`. Nothing else; its ingredients leave the shopping list.
- `POST /api/v1/plan/meals/{plan_meal_id}/moved`, body `{ "date", "slot_id" }`. The old meal becomes `moved` and keeps its slot. Its recipes and ingredients are copied to the new day and meal (a tub moves, since a tub is in one meal at a time); a meal there that already has food gets them alongside (at most 20 things). `meal_id` in the answer is the meal it went to.
- All three answer like the other plan writes (`PlanWrite`: the `change` with its Undo, `meal_id`); a retry with the same `Idempotency-Key` answers from the first change. Kinds `plan_cooked`, `plan_didnt`, `plan_moveit`. Undo asks about the meal again (status back to `planned`) and takes back the tubs, or the things added to the other meal; the shopping list follows.
- Refusals: `409 meal_done` (already answered), `422 not_yet` (the meal's day has not come), `422 no_recipe` (leftovers asked of a meal without a recipe, or of an ingredient), `422 batch_full` (a batch holds at most 12 tubs), `422 no_freezer` / `no_fridge`, `422 same_place`, `422 past_day` (Move it to a day before today), `422 slot_off`, `422 meal_full`, `422 bad_day`; `404` for any id (meal, slot, item) that is not this household's.
- No database change.

### 6.3d "Cooked it": the deduction engine (0.7 K2)

What "Cooked it" would take from the pantry, and the confirm that takes it. The review screen that uses them is K3. Online only. Spec section 2, "Cooking — how deduction works".

- `POST /api/v1/plan/items/{plan_item_id}/cook/preview` and `POST /api/v1/plan/batches/{plan_batch_id}/cook/preview`, body `{ "portions"?: 1 to 999, "answers"?: [ask-once replies] }` → `{ "recipe": {id, name}, "portions", "servings", "rows": […] }`. **Changes nothing.** `portions` left out: the meal item's servings (else the recipe's); a batch: the cook-day meal's servings (else 1) plus a portion for each tub, as Cook once and the shopping list count it. One row per ingredient, in the order the recipe first uses it (lines of one ingredient are added up):
  - `key` (`food:12`; `recipe:7` for a recipe with no pantry ingredient; `line:3` for a line that links to nothing), `status` (`take` · `none_in_pantry` · `staple` · `ask` · `no_amount` · `not_linked` · `make_first`), `lines` (`{id, words}`), `food`, `recipe` (a recipe used as an ingredient), `needed` (an `AmountOut`, for the portions cooked: recipe amount x portions / servings, a counted ingredient rounded to the nearest half; the recipe's own amount as written when it has no servings), `takes` (what would be taken: `{ food, stand_in, amount, before, after, lots: [{ lot_id, place, use_by, amount }] }`, the packet that goes off first, fridge and cupboard before the freezer), `use` (how the row's Use switch starts: off when there is nothing to take), `short` (what the pantry lacks: "add to list"), `make_first` (a recipe used as an ingredient with none or not enough in the pantry: "Make it first?"), `in_freezer` (stock waiting in the freezer, left alone unless `from_freezer`), `from_freezer`, `ask` (the "ask once" question, the same object as `409 ask_once` carries, when a conversion isn't known).
  - Units differ → the household's answers over the bundled table; unknown → `status: "ask"` and no amount until `answers` carries the reply. A staple is never taken. An ingredient with none (or not enough) takes the rest from its "Can use instead" ingredients (id order, counted the same way), shown as extra `takes` with `stand_in: true`, but only when the ingredient has none at all in stock (cabledrawer 31 Oct); with some but not enough the rest is `short`, never mixed with a stand-in. Stock only in the freezer: `use` false and `in_freezer` set. Two packets with one use-by: the opened one first, else the one bought first; a packet that would be left under 2 % is taken whole (`lots[].used_all`). `add_to_list` says the shortfall is ticked to go on the shopping list; the confirm's `choices[].add_to_list` (default true) puts it there (onto the ingredient's open line if it is too small, else a new line), and Undo takes it off again. A recipe used as an ingredient that is made ahead is taken from its own pantry ingredient.
- `POST /api/v1/plan/items/{plan_item_id}/cook` and `POST /api/v1/plan/batches/{plan_batch_id}/cook` (`201`), body: as above plus `"choices"?: [{ "key", "use"?: true, "used"?: {amount, unit | size_id}, "left"?: {…}, "from_freezer"?: false }]` (rows not mentioned are as proposed; `used` and `left` are not both; zero is allowed for `left`). `answers` marked `remember` are saved for next time. The packets are taken as one change, kind `cooked` (a line for each packet touched, shown in Pantry's Recent changes, with Undo), and the **cooked record** is written with the snapshot and the choices (`snapshot.choices`: per row its `key`, `status`, `line_ids`, `food`, `recipe`, `use`, `needed_milli`, `entered` / `entered_milli` (what was typed), `from_freezer`, `used_milli` (taken in all), `short_milli`, `takes`). Answers `{ "change", "cooked" }`; a retry with the same `Idempotency-Key` answers `200` with `Idempotent-Replayed: true` and takes nothing more.
  - A batch deducts once, on the cook day; the tubs are the ones Cook once made. A second confirm for the same item or batch → `409 already_cooked`. The item a batch was made from → `409 cook_the_batch`. A meal that is skipped or moved → `409 meal_done`; a recipe that is gone, or a plain ingredient → `422 not_a_recipe`. A row that still asks, switched on, with no typed amount → `409 ask_once` (the same payload). `422`: `unknown_row`, `twice` (a key chosen twice), `no_ingredient` (an amount for a row with no ingredient), `staple` (an amount for a staple), `left_too_much` (more left than there is). Never below zero: a typed `used` over what there is takes the lot and the record's `short_milli` says how much was missing.
  - **Undo** (`POST /changes/{id}/undo`) puts the packets back and takes the record away, so the item or batch can be cooked again. This does not change the meal's status or make leftover tubs; that is Today's answer (`POST /plan/meals/{id}/cooked`).
- **A whole meal** (cabledrawer 31 Oct: one Confirm and one Undo for the whole meal): `POST /api/v1/plan/meals/{plan_meal_id}/cook/preview` and `POST /api/v1/plan/meals/{plan_meal_id}/cook` (`201`), body `{ "items"?: [{ "item_id", "portions"?, "choices"?: […] }], "answers"? }` (`items` left out: every recipe in the meal; a tub or a plain ingredient has nothing to take). The recipes are worked out from **one pool of packets**, so two recipes never both take the same grams (the second sees what the first left). One change, one Undo, all or nothing (a refusal such as `409 ask_once` or `409 already_cooked` comes before anything is taken), and a cooked record for each recipe: `{ "change", "cooked": [CookedOut] }`; the preview answers `{ "meal_id", "items": [{ "item_id", "proposal" }] }`. A meal with a batch cook's recipe → `409 cook_the_batch`. A recipe's shortfalls are added to the list once per ingredient.
- **Add to list** is its own choice, apart from Use: each row has `add_to_list` (how the proposal ticks it) and `list_amount` (what would go on). A row with nothing in the house offers its whole shortfall, ticked, even though Use starts off; stock only in the freezer offers it unticked; a row whose take leaves the ingredient at or below its running-low level (`running_low: true`; the Pantry's own test) offers one of its smallest size (else the running-low level), unticked. The confirm's `choices[].add_to_list` overrides it (left out: as proposed), whatever the Use switch says: a row with Use off is offered exactly what the preview showed for it (the preview takes no choices: the meal worked out as one, every Use on), with the person's own tick. Undo takes a line it added back off (and gives a line it joined its amount, size and hand-edited flag back) only if nobody has changed that line since; otherwise it is left and the Undo says "partly".
- **What the review screen needs (0.7 K3; all additions, nothing above changes):**
  - A row has `estimate` (true when the recipe and the pantry count the ingredient differently, so `needed` came from changing units: a cup of flour in grams; kg to g, tbsp to ml and size lines are exact and not marked), `unit` (what the pantry counts the ingredient in: g, ml or count), `unit_word` (a counted ingredient's word, plural: "bulbs"; null when it has none), `half` (about half of the packet that goes off first, outside the freezer, in the pantry's unit: its size, else what is left in it; halves of a count, whole g or ml; set on `ask` and `no_amount` rows with stock), `lines[].amount` and `lines[].unit` (the recipe's own amount as written, "1½" and "tbsp", so each side shows its own unit), `ask_need` (on an `ask` row: `{ amount, unit: "g" | "ml" | "item" }`, what the recipe asks for on its own side, for the portions cooked; null when the row's lines mix units, and the screen then asks the old way), `count_note` (on a `no_amount` row of one line whose note starts "2 cloves" or "3 sprigs", F89: `{ count, word: "clove" }`, scaled to the portions and rounded to a half) and `bought`.
  - **The question in the pantry's unit (F106).** The screen asks "How much did you use?" in the pantry's unit and works the conversion out from the answer, sent in the existing `answers`: a recipe in ml and a pantry in g gives `weight_per_ml` with grams per household cup = answer / `ask_need` x the cup; a recipe in g and a pantry in ml the other way round; a recipe in items and a pantry in g gives `item_weight`; a recipe in g and a pantry in items too. Two legs missing (cups against a count) are asked the old way. A saved answer replaces an earlier one (`remember` on); with it off the answer is used for this cook only. For a `no_amount` row with a `count_note` the typed amount is sent as a `size` answer (`name` the word, `amount` the typed amount divided by the count): the ingredient's size "clove" is saved, and an earlier size of that name is **replaced, but only in a cook and only the size the row's `count_note` asked about**; every other caller keeps the rule that an existing size is never changed. The cook's change records the old amount and its Undo puts it back, but only if nothing has changed it since: an older cook's Undo leaves a size that a later cook changed and answers `partly` with "A later cook changed the size of a clove, so it was left as it is." (proposed, for cabledrawer). The up-to-5 `answers` of a preview or a confirm is now up to 20 (a meal can ask for several).
  - `choices[].bought: true` is "Bought some — used them": the row takes nothing (Use is off; `use: true` or an amount with it is `422`; a staple or a row with no ingredient is `422`). The cooked record's `snapshot.choices[].bought` keeps it (false on records made before this).
  - `DELETE /plan/batches/{id}` of a batch that has a cooked record → `409 already_cooked` ("This was cooked on Mon 2 Nov. Undo “Cooked it” first."): the record is never lost. After the Undo it can be taken off.
  - Stock of one ingredient in several places (fridge and cupboard) is one total on its row (`takes[].before`, `after`), as on Shopping (F101); the packets keep their places in `lots`.
- **Undo of "Cooked it"** is the ordinary stock Undo: it gives back what the change took, on top of whatever has happened since, never below zero, and says "partly" when something can't go back (a packet the tidy-up has deleted, a list line that has changed). Whenever it runs, the record goes, so the item can be cooked again.
- In a meal, an ingredient gets at most one running-low pack, and none when the same ingredient is already short in the meal.
- `POST /api/v1/plan/tubs/{plan_tub_id}/eat`, body `{ "quarters"?: 1 to 4 }` → `PlanWrite`. Eating a tub uses the tub, never the ingredients. Left out: all that is left of it. What is left stays where it is. Kind `plan_tub`, with Undo (as the stock Undo: it gives back the quarters it ate on top of what is there now, up to a whole tub, even if the tub was eaten from again since). `409 tub_eaten` (nothing left), `422 too_much` (more than is left).
- The cooked record's `snapshot` has a new `choices` list (empty on a record made before this). No database change: the choices are inside the snapshot.

**Use by or Best before (0.8, cabledrawer 7 Nov).** Every ingredient has a date type, `date_kind`. Nothing chosen (the database column `food.date_kind` is null) → the default: the bundled pack-size table's `dates` column when the name or another name matches a row, else from where it is usually kept (fridge: `use_by`; cupboard, freezer, spice rack or no place: `best_before`). **Only meat, fish and chilled dairy are locked to `use_by`** (`date_kind_locked: true`; cabledrawer 7 Nov): the table row says `use by` and is meat or fish (the row's aisle) or chilled dairy (milk, cream, yoghurt, cheese, paneer: a fixed list of table keys in `date_kinds.py`). It goes by what the food is, not by aisle: idli batter, tofu, spinach and hummus start `use_by` but can be switched, and an ingredient with no table row is never locked. A table row that says best before (butter, eggs) starts `best_before` and can be switched. `PATCH {"date_kind": "best_before"}` on a locked one → `422 date_kind_locked`. Choosing the type already in force without a stored choice changes nothing (`change: null`); otherwise it is one Recent changes line ("Homemade pickle is now Use by") with Undo. A stored choice is kept when the usual place changes.

### 6.4 Stock (the Pantry screen)

**`GET /api/v1/pantry?filter=all&q=thuvaram`** — `filter`: `all` · `use_soon` · `running_low` · `staples`. `q` (from 0.2.1) searches by any name, other names too, with the same matching as `GET /foods?q=`; each place's `items` then counts only what is found, while `counts` stay for the whole pantry. One call gives the whole screen (the phone cards and the desktop columns use the same data).

```json
{
  "today": "2026-10-17",
  "counts": { "items": 47, "tubs": 0, "use_soon": 3, "running_low": 1 },
  "places": [
    {
      "id": 1, "name": "Fridge", "kind": "fridge", "items": 9,
      "groups": [
        {
          "food": { "id": 20, "name": "Paneer", "counted_as": "weight" },
          "stock": { "amount": 400, "display": "2 packs · 400 g", "…": "…" },
          "lots_count": 2, "dates_count": 2,
          "use_by": "2026-10-19", "days_left": 2, "use_soon": true,
          "running_low": false,
          "lots": [
            { "id": 501, "stock": { "display": "1 pack · 200 g", "…": "…" }, "use_by": "2026-10-19", "days_left": 2, "use_soon": true, "added_on": "2026-10-12", "frozen_on": null, "size_id": 30, "open": false },
            { "id": 502, "…": "…" }
          ]
        }
      ]
    }
  ],
  "staples": [ { "id": 3, "name": "Salt", "restocked_at": "2026-10-12T09:00:00Z" }, { "id": 4, "name": "Turmeric", "restocked_at": null } ]
}
```

- A group is one food in one place; lots in it are ordered as they'd be used (oldest/soonest first); the group's `use_by` is its soonest.
- `items` counts groups, and (0.8) the place's tub rows. `counts.tubs` is the number of tubs left. `counts.use_soon` counts the soon ingredient rows and the soon tub rows (the same rows the Use soon strip shows).
- **Tubs (0.8, F131).** Each place has `tubs`: one row per batch and place for tubs left (in no meal) with some in them, soonest first: `{ batch_id, tub_id, recipe_name, colour, tubs, words ("2 tubs", "¾ tub"), use_by, days_left, use_soon }` (`tub_id`: its soonest tub, the one "Eat it on…" puts in a meal). A tub with no place is in the first fridge. `filter=use_soon` keeps the tubs whose use-by is soon; `running_low` and `staples` show none; `q` matches the recipe's name.
- **`date_kind`** (0.8) is on every group and lot: `use_by` or `best_before`, the ingredient's. `use_soon` on a lot is true for a Use by date from the past up to today + `use_soon_days`, and for a Best before date only once it has passed; a group's is true when any lot's is. `counts.use_soon` counts groups (one per ingredient and place) with a lot that is soon.
- `open`: the lot holds less than its size (shows the ¼ ½ ¾ Full picker).
- `running_low`: the food's total in all places is at or below its running-low level.
- Groups in a place are ordered by soonest use-by, then name.

**`GET /api/v1/pantry/use-soon`** → **one row per ingredient and place** (0.8, cabledrawer 7 Nov; Today, Pantry and Use soon all use it), soonest first. A row's `id` is its soonest packet that is soon, `stock` the total of the packets that are soon in that place ("2 packs"), `use_by`/`days_left` the soonest, `lots_count` how many packets and `lot_ids` which, soonest first. The same rule as `use_soon` above (a Best before date counts only once passed):

```json
{ "lots": [ { "id": 501, "food": {"id": 20, "name": "Paneer"}, "place": {"id": 1, "name": "Fridge", "kind": "fridge"},
              "stock": {"display": "2 packs · 400 g", "…": "…"}, "use_by": "2026-10-19", "days_left": 2,
              "date_kind": "use_by", "use_soon": true, "lots_count": 2, "lot_ids": [41, 44], "…": "…" } ],
  "tubs": [ { "batch_id": 3, "tub_id": 12, "recipe_name": "Lemon rice", "words": "2 tubs", "use_by": "2026-10-20",
              "days_left": 3, "use_soon": true, "place": {"id": 1, "name": "Fridge", "kind": "fridge"}, "…": "…" } ] }
```

`tubs` (0.8, cabledrawer 7 Nov): the leftover tubs that are Use soon (a use-by up to the Use soon days ahead, or passed), one per batch and place, soonest first, as the Pantry's tub rows plus their `place`. The strip shows each as "Lemon rice · Fridge · 2 tubs" with "Eat it on…" (`POST /plan/tubs/{tub_id}/place`); a passed one has no button.

**Writes.** All take `Idempotency-Key`, and all answer `{ "change": {…}, "groups": [ …the food's group in each place touched, as above… ], "short_by": null }`. A group that's now empty comes back with `stock.amount: 0` and no lots, so the client can remove it. An emptied or unknown lot is a 404. Other refusals: `409 staple` (adding a staple), `409 already_frozen`, `409 already_there` (moving to where it is), `409 no_change` ("3 left" when there are 3), `409 nothing_left` ("used" on a food with nothing left), `409 in_use` (removing a food that still has stock), `422 too_late_to_freeze` (To freezer on a Use by packet from the day after its date; Best before food can always be frozen).

| Request | Body | Notes |
|---|---|---|
| `POST /api/v1/stock` | `{ "food_id": 7, "amount": {"amount": 2, "unit": "packet"}, "place_id": 3, "use_by": "2026-11-20" }` | Add to pantry. `place_id` defaults to the food's place, else Cupboard. `use_by` optional. "2 packets" makes two lots. `201`. Staple foods → `409 staple` ("Turmeric is a staple, so it isn't counted."). |
| `POST /api/v1/stock/{lot_id}/left` | `{ "fraction": 0.5 }` or `{ "amount": {"amount": 250, "unit": "g"} }` | Set what's left. `fraction` (0–1, the ¼ ½ ¾ Full picks) is of the lot's size; a lot with no size needs `amount`. Can go up (Full). 0 empties it. |
| `POST /api/v1/stock/{lot_id}/used` | `{}` or `{ "amount": {…} }` | Empty body = used it all (Use soon → Used). More than is there → takes all, `short_by` says the rest. |
| `POST /api/v1/stock/{lot_id}/binned` | `{}` or `{ "amount": {…} }` or `{ "soon": true }` | As used, recorded as binned. `soon` (0.8, a Use soon row): every packet of that ingredient in that place that counts as soon, binned in one change with one Undo; not with an amount (`422 soon_with_amount`). |
| `POST /api/v1/stock/{lot_id}/to-freezer` | `{}` or `{ "use_by": "2027-01-17" }`, and `"soon": true` | Whole lot to the first freezer place; use-by today + 3 months unless given; `frozen_on` today. `soon` (0.8, a Use soon row): every packet of that ingredient in that place that counts as soon, in one change with one Undo. |
| `POST /api/v1/stock/{lot_id}/move` | `{ "place_id": 2 }` | Whole lot. Moving into a freezer place this way doesn't change the use-by. |
| `PATCH /api/v1/stock/{lot_id}` | `{ "use_by": "2026-10-22" }` (null clears) | Change the date. |
| `POST /api/v1/foods/{id}/used` | `{ "amount": {"amount": 1.5, "unit": "count"}, "place_id": 1 }` | "How much did you use" on a group: takes from that food's lots, oldest/soonest first (3.5). `place_id` optional; without it freezer lots are skipped. Nothing to take from → `409 nothing_left` ("There's no Ghee left."), and nothing is recorded. |
| `POST /api/v1/foods/{id}/left` | `{ "amount": {"amount": 3, "unit": "count"}, "place_id": 1 }` | "3 left" on a group: takes from the soonest lots first, or tops up the newest lot if the number is higher. `amount` may be 0 ("None left"): every lot in scope is emptied (freezer lots only when the freezer is named), with Undo. Already that much → `409 no_change`. |

Summaries: "Added 2 packets Toor dal → Cupboard", "Used 200 g Spinach", "Binned 1 pack Paneer", "Toor dal: 1 packet → about ½ packet", "Moved Chana masala → Freezer", "Paneer → Freezer, use by 17 Jan".

### 6.5 Recent changes and Undo

**`GET /api/v1/changes?limit=20&before=<id>&food_id=7&area=pantry|ingredients&mine=false`**

- **No `area`: every kind of change, newest first (Settings → Recent changes, F172, cabledrawer 7 Nov)**: pantry, shopping, plan, cooking, recipes, imports, ingredients, and shops and places removed (`shop_removed`, `place_removed`), each with its `can_undo`. Page with `before=<the previous answer's next>`; "Show more" asks for the next page. `area` still works for old clients.
- **One Cooked it is one row (cabledrawer 7 Nov).** The meal's own answer (`plan_cooked`) and its Undo are not listed beside the pantry's `cooked` change of the same press, whose row carries the one Undo (an Undo of either takes back both, F125). A press that has no pantry change (the answer given on its own) is still its own row. A page never splits the pair: the answer is left out wherever the press's first change is, on this page or an older one, so `limit` counts rows, and `before` pages by the id of the last row shown.
- `area=pantry` lists stock changes, and the Undos of stock changes, only (Pantry → Recent changes); omit it for everything (food edits, merges).
- `area=ingredients` (0.3) lists changes to ingredients (`food_created`, `food_edited`, `food_removed`, `merged`, `split`), and the Undos of those, only (Ingredients → Recent changes). Only the signed-in household's changes ever come back.
- Each change carries `totals`, for showing in Recent changes: one entry per ingredient and place, the ingredient's whole amount in that place before and after the change (other packets included; from 0.2.1, saved with the change so it stays right later) worded as sold: `[{ "food_id", "name", "place_before", "place_after", "before": AmountOut, "after": AmountOut }]`. "Added 2 packs Paneer" gives one entry, "Paneer: 1 pack · 200 g → 2 packs · 400 g" if a pack was already there (`place_before` is null for packets the change added); a move gives "Cupboard → Fridge" with the same amount on both sides (only the packets moved). Changes recorded before 0.2.1 add up just the packets they touched. Undos have them too. Ingredient changes have none.
- Each change also carries `lines`, one per packet, for detail (and thinning): `[{ "food": {id, name}, "lot_id", "before": AmountOut, "after": AmountOut, "place_before", "place_after", "use_by_before", "use_by_after" }]` (empty for food changes).
- `mine=true` gives the signed-in login's own changes; `mine=true&limit=1` with `can_undo` finds what **Ctrl+Z** undoes (the client ignores Ctrl+Z while focus is in a text box).

```json
{ "changes": [ { "id": 812, "kind": "used", "summary": "Used 200 g Spinach", "who": {"login_id": 2, "name": "Wren"},
                 "at": "…", "can_undo": true, "undo_until": "…", "undone": null,
                 "lines": [ { "food": {"id": 22, "name": "Spinach"}, "lot_id": 499,
                              "before": {"display": "200 g", "…": "…"}, "after": {"display": "0 g", "…": "…"},
                              "place_before": {"id": 1, "name": "Fridge"}, "place_after": {"id": 1, "name": "Fridge"} } ] } ],
  "next": null }
```

`undo` changes are listed too ("Undid: Used 200 g Spinach") but have `can_undo: false`: there's no redo in 0.2. An Undo of a stock change has its own `lines`: what it actually did to each lot (a partial undo shows only what it put back).

**`POST /api/v1/changes/{id}/undo`** (any household login, within the undo window; takes `Idempotency-Key`)

Undo reverses **just that change**, line by line, and later changes stay:
- amounts: the opposite of that line's difference is applied to the lot as it is now, never below zero (an empty lot is brought back);
- place and use-by: put back only if the lot still has the value the change gave it (someone changed it since → left alone);
- food changes: each changed part (a field, an other name, a size, a stand-in link, a remembered answer) is put back if it still has the value the change gave it; a name that another food has taken since is not put back;
- merge: the snapshot is restored (6.2).

```json
{
  "result": "partly",
  "message": "Took back 150 g of the 500 g: the rest has been used since.",
  "change": { "id": 830, "kind": "undo", "summary": "Undid: Added 1 packet toor dal", "can_undo": false, "…": "…" },
  "undone": { "id": 812, "undone": { "at": "…", "who": {…} }, "…": "…" },
  "groups": [ … ],
  "food": null
}
```

`result`: `done` (all of it), `partly` (some of it; `message` says what), `nothing` (nothing could be put back; still recorded, so the button goes away). Errors: `409 already_undone`, `410 too_old`.

### 6.6 Other

- `GET /api/v1/units` (4.1), `GET /api/v1/foods/{id}/convert`, `GET`/`DELETE /api/v1/conversions` (4.5).
- No Server-Sent Events in 0.2: the web app re-fetches `/pantry` when the tab comes back into view.

## 7. Decisions on the open points (lead, 17 Oct)

1. **Removing a food:** allowed only when it has no stock (and, from 0.4, no recipes); soft delete, undoable; a quiet "Remove" link in the editor. Proposed to cabledrawer in the PR and recorded in the spec as a proposal.
2. **Open packs:** one display rule for every lot plus the `open` flag; the web app adds "· open" and the ¼ ½ ¾ Full picker. A whole number of sizes never says "about" ("1 tub · 500 g").
3. **No redo** (undoing an Undo) in 0.2.
4. **"Not the same"** is saved quietly with no Undo.
5. **Count foods with no count word** read "5 left".
6. **`Idempotency-Key` header** in 0.2. From 0.3 the sync queue sends action IDs in the request body; the server then accepts either (both share the same uniqueness per household).
7. **Change log and Undo** land in the foods-and-units PR.
