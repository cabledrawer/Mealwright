# Shopping lists and offline sync (0.3)

Written 17 Oct 2026 as the contract for milestone 0.3's building pull requests (PRs 2 to 6). It says what the server stores, what a phone sends, what the server does with it, and how we test that the pantry always ends up right. **The spec (`docs/spec.md`) wins wherever this file disagrees with it.** Once built, the generated OpenAPI (`/api/v1/openapi.json`) is the exact reference for field names and shapes; this file is the plan they follow. It builds on `docs/dev/api-0.2.md` (conventions, errors, the change log and Undo), which still applies unless this file says otherwise.

Spec line numbers below (`L271`) are from `docs/spec.md` on `main` at `1c4c341`. cabledrawer's 17 Oct and 18 Oct answers were added to the spec in this pull request, and are cited as `new L292` and so on (their line numbers on this branch). Section 16 lists the 18 Oct decisions.

## Map of this file (read this first)

Read section 0 for the whole idea, then only the sections your pull request needs. Find a section's line with `grep -n '^##' docs/dev/sync-protocol.md`. Don't read the whole file.

| § | What it covers | Mainly for |
|---|---|---|
| 0 | The whole design in plain English | everyone |
| 1 | What's in 0.3 and what isn't; which pull request builds what | the lead |
| 2 | Words used: action, counter (`seq`), cursor, `seen`, purchase, standing tick, tombstone, note, card, device ID | everyone, when a word is unclear |
| 3 | Data model: lists, items, purchases (`list_tick`), the sync log (`sync_action`), notes, the "both ticked" question, new columns, device ID, tidying old rows | server, migrations |
| 4 | Actions: the envelope, each action kind, amounts, new ingredients in `add`, what stays online-only | server, phone queue |
| 5 | The server: endpoints (incl. the one-at-a-time list requests, 5.1), order and the counter, repeats, per-action results, catching up ("changes since"), errors, server-made changes, changes made while a phone was offline | server |
| 6 | The rules for clashes (L-1 …), each with its test | server, checker |
| 7 | The pantry side of a tick: tick, a purchase's stock, put away, "Different pack?", taking a purchase back | server pantry |
| 8 | Quiet notes (N1 …) and the "Did you buy 2?" card | server, Shopping screen |
| 9 | Undo | server, screens |
| 10 | Live updates (PR 5) | PR 5 |
| 11 | The phone: what it stores, optimistic display, sending, "N changes waiting", sign-in running out, app updates, how long offline, device ID (PR 6) | PR 5, PR 6 |
| 12 | Signing out: warning and wipe | PR 6 |
| 13 | Screen details that touch the protocol | PR 4 |
| 14 | Two-device tests (SY-01 …) | checker, every sync pull request |
| 15 | The manual two-phone test for the 0.3 release | release, cabledrawer |
| 16 | Decisions cabledrawer made on 18 Oct | everyone |


## 0. In plain English

- Every change to a shopping list (tick, untick, add, change an amount, delete, choose where it goes, "Different pack?") is a small **action** with its own random ID, made on the phone.
- The phone keeps a **queue** of actions. Online, it sends them straight away. Offline, they wait on the phone (as long as it takes) and go when it's back.
- The server works through actions **in the order it receives them**, numbering each one with a **counter**. Phone clocks never decide anything.
- If an action arrives twice (same ID), the second is ignored and the phone gets the same answer as the first time. That's what makes "send it again if unsure" safe.
- Only the server changes the pantry. A tick puts the shopping into the pantry; untick or Undo takes it back out (never below zero).
- Nothing is ever refused with a pop-up because someone else changed the list. Clashes follow the rules in section 6 and, where it matters, leave a **quiet note** with Undo.
- The online web app and the offline phone use **the same path**: online is just a queue that empties at once. So what we test offline is what everyone uses every day.

## 1. Scope

**In 0.3:** shopping lists (one main list per household plus extra lists), list items, the sync protocol in `/api/v1`, the pantry side of ticking, quiet notes and the "Did you buy 2?" card, live updates (Server-Sent Events), the installable app with its offline queue in IndexedDB, connection status, and the sign-out wipe.

**Not in 0.3:** building the list from the plan and the staples check card (0.6, though the data model is ready: `source = plan`, keyed by ingredient and shop), the card on Today (0.6), per-shop aisle order by dragging (0.8), recently viewed recipes offline (0.4), the "Who's this?" picker (0.8). The Pantry, Ingredients and Undo from Recent changes stay online-only, as in 0.2.

**Who builds what** (the lead may move pieces between PRs; the contract stays the same):

| PR | Branch | Builds |
|---|---|---|
| 2 | `m0.3/lists` | Section 3 (all tables and columns, one migration per step), the Aisle field on ingredients, the counter and Undo for list changes, and plain one-at-a-time list requests (make, rename and remove a list; add an existing ingredient, change the amount, delete, Clear ticked), each taking a counter number and recording a change for Undo. A main list for every household. `cannot_remove` checks lists (following merges); merging moves list items; ingredient edits bump `food.version`. 0.2's `replayed()` also checks action IDs (5.7). `Cache-Control: no-store` on all of `/api` (section 12). Isolation tests. **Moved to PR 3 (cabledrawer 18 Oct):** `GET /shopping/changes`, `POST /shopping/actions` with the envelope, repeats and refusals, `dismiss_note`, and `add` with a new ingredient (`new_food`). |
| 3 | `m0.3/server-sync` | From PR 2 (cabledrawer 18 Oct): `GET /shopping/changes`, `POST /shopping/actions` with the envelope, counter, repeats and refusals (sections 4 and 5), `dismiss_note`, `add` with `new_food`; routing PR 2's one-at-a-time list requests through the same action handling (5.1); `sync_action` rows for the other server-made changes in 5.8 (ingredient edits; merges already write one from PR 2) and `follow_shop`. Then `tick`, `untick`, `put_away`, `different_pack`, `clear_ticked`, `answer_double_tick`, `undo` of those, the pantry side (section 7), the double-tick question, the remaining notes, `change.tick_id` and the `repacked` change kind, Pantry Undo of a purchase's changes keeping the list in step (5.8), what happens when something was removed while a phone was offline (5.9), the history job's tidy-up of sync tables, and the backend two-device tests and property test (section 14). |
| 4 | `m0.3/shopping-screen` | The Shopping screen (section 13), writing only through one client function `sendAction(action)` that PR 6 turns into the queue; the "New ingredient" button on Ingredients; the "How do you count it?" question. |
| 5 | `m0.3/live-and-installable` | `GET /api/v1/events` (section 10), live refresh of Shopping and Pantry, the installable app (manifest, service worker for the app shell), the app-update rule (11.6), the connection bar and toast (11.4, with the waiting count filled in by PR 6). |
| 6 | `m0.3/offline-queue` | Section 11 (IndexedDB with `idb`, the offline copy, the queue, optimistic display, sending and retries, sign-in running out), section 12 (sign-out warning and wipe), and the browser end-to-end tests E1s (E1 with both devices signed in as Tess; the two-person E1 waits for 0.8, cabledrawer 18 Oct), E2 and E3. |

## 2. Words used in this file

- **Action:** one thing a person did to a list, with a phone-made ID. Section 4.
- **Counter (`seq`):** the household's server-side number. Each recorded action takes the next one. It is the only order that counts.
- **Cursor:** the counter value a device's copy is up to. "Changes since 1040" means everything that changed after action 1040.
- **`seen`:** the device's cursor at the moment the action was made. It tells the server what that person could see, so it can tell a clash ("Wren hadn't seen Tess's change") from an ordinary later change.
- **Purchase:** one standing tick. Each purchase has its own pantry stock. Two ticks on one item = two purchases.
- **Standing tick:** a tick that hasn't been reversed (by untick, "Just 1" or Undo).
- **Tombstone:** a deleted item's hidden row. It stays so an old queue can't bring the item back.
- **Note:** a quiet line on Shopping ("Wren added milk too") with Undo and a ×. Section 8.
- **Card:** the "Did you buy 2?" question. Section 8.
- **Device ID:** a random ID the app makes for itself after sign-in. Section 11.8.

## 3. Data model (PR 2)

Every table has `household_id` (FK household, cascade on delete) and is reached only through the signed-in login's household. Every change is an Alembic migration. Amounts are stored as integer **milli base units** (`amount_milli`: mg, µl or 1/1000 item), like `stock_lot`. In JSON they are plain base-unit numbers, at most 3 decimal places (api-0.2 section 1). Times are UTC; `made_at` from a phone is stored but never used to order anything.

IDs: lists, items and actions use **phone-made UUIDs** (lowercase, with dashes, 36 characters) so a phone can create and refer to them offline. Notes and questions are made by the server and use integer IDs, like the rest of the database.

### 3.1 `shopping_list`

| Column | Type | Notes |
|---|---|---|
| `id` | str(36), PK | UUID. Phone-made for extra lists; server-made for the main list. |
| `household_id` | | |
| `name` | str(60) | Not unique (two phones may both make "Party" offline; both are kept). |
| `main` | bool | Exactly one main list per household (partial unique index on `household_id` where `main`). Made with the household, and by the migration for existing households, named "This week". |
| `position` | int | Main list first, then extra lists in the order they were made. |
| `created_at`, `created_by_name` | | |
| `removed_at` | datetime, null | Removed extra list. A removed list is **hidden, not frozen**: queued actions still apply inside it (section 6, row L-7), so Undo brings it back complete (cabledrawer 18 Oct, decision 6). Never set on the main list. |
| `removed_action_id` | str(64), null | The `remove_list` action, for Undo and notes. |
| `version` | BigInteger | Counter value of the last change to this row. |

### 3.2 `list_item`

| Column | Type | Notes |
|---|---|---|
| `id` | str(36), PK | Phone-made UUID (spec L280 "phone-made IDs"). |
| `household_id`, `list_id` | | `list_id` FK shopping_list. |
| `food_id` | FK food | Every item is an ingredient (spec L287). Non-food items are staples. |
| `shop_id` | FK shop, null, SET NULL | Copied from the ingredient's usual shop when added, unless the action says otherwise. Null = "Any shop" (new L298). When an ingredient's usual shop changes, its unticked, live items whose `shop_id` was the old usual shop (or null) move to the new one (cabledrawer 18 Oct, decision 7). |
| `amount_milli` | BigInteger, null | The amount to buy, in base units. Null = no amount (cabledrawer 18 Oct, decision 1). |
| `size_id` | FK food_size, null, SET NULL | The size the amount was given in, for display ("2 packets"). |
| `source` | str(10) | `typed` (every action-made item) or `plan` (0.6). |
| `hand_edited` | bool | Set by `set_amount`, and by an `add` merge that keeps the typed amount. Plan updates (0.6) never touch an item with this on (spec L273). |
| `put_away_place_id` | FK place, null, SET NULL | The place chosen for this item. Used by the next tick; changed by `put_away`. |
| `ticked_at`, `ticked_by_login_id`, `ticked_by_name`, `ticked_device_id` | null | A copy of the **first standing tick** (spec L280 "ticked by / when"), kept in step with `list_tick` by the server. All null when nothing is standing. |
| `added_at`, `added_by_login_id`, `added_by_name` | | |
| `deleted_at`, `deleted_by_name`, `deleted_action_id` | null | The tombstone (spec L274). `deleted_action_id` is the `delete` or `clear_ticked` action. |
| `merged_into_id` | str(36), null | Set when an `add` was merged into another line (new L294). The row stays hidden; any later action naming it is applied to the line it joined. |
| `version` | BigInteger | Counter value of the last change to this row or its ticks (spec L280 "version number"). |

Indexes: (`household_id`, `version`); (`list_id`); (`household_id`, `list_id`, `food_id`, `shop_id`) for the merge rule.

### 3.3 `list_tick` (one row per purchase)

| Column | Type | Notes |
|---|---|---|
| `id` | str(64), PK with `household_id` | The `tick` action's ID. |
| `household_id`, `item_id` | | |
| `login_id`, `login_name`, `device_id` | | Who ticked, on which device. |
| `ticked_at` | datetime | Server time it was applied. |
| `place_id` | FK place | Where the stock went (and where `put_away` moved it). |
| `bought_milli`, `bought_size_id` | | What this purchase put in: the item's amount at the tick, or what "Different pack?" said. Null = nothing (staple or no amount). |
| `change_id` | FK change, null, SET NULL | The purchase's own `shopped` change: the tick's, or the one that put it back after an untick (7.5). Only an Undo of **this** change from Pantry unticks the item (5.8). Null for staples and items with no amount. |
| `reversed_at`, `reversed_by_action_id` | null | Set by untick, "Just 1" or Undo. Cleared when an Undo puts the purchase back. |

### 3.4 `sync_action` (the sync log, spec L280)

| Column | Type | Notes |
|---|---|---|
| `household_id`, `id` | PK (both) | `id` is the action ID: 1 to 64 letters, digits, `.`, `-`, `_`, `:` (the 0.2 `Idempotency-Key` rule). The web app always uses UUIDs. |
| `seq` | BigInteger | The counter. Unique (`household_id`, `seq`). |
| `kind` | str(30) | Section 4.2, or a server-made kind: `untick_by_undo`, `place_by_undo`, `follow_shop` (5.8), `merge_foods` (5.8; written from PR 2, because merging moves list items and its Undo needs the row), `purge` (3.9). |
| `login_id`, `login_name` | | Who. |
| `device_id` | str(36), null | Null for server-made actions. |
| `list_id`, `item_id` | null | What it acted on (after following `merged_into_id`). Index (`household_id`, `item_id`, `seq`). |
| `seen` | BigInteger, null | The device's cursor when it was made. Null → treated as "saw everything" (no clash notes). |
| `made_at` | datetime, null | Phone clock. Shown nowhere except the Undo window (section 9). |
| `applied_at` | datetime | Server time. |
| `payload`, `payload_hash` | JSON, str(64) | The action as received (minus the envelope) and its SHA-256 over sorted-key JSON, to spot an ID reused for something else. |
| `status`, `reason` | str(10), str(30) null | `applied` · `merged` · `ignored` (section 5.4). |
| `result` | JSON | The exact per-action result returned, so a repeat gets the same answer. |
| `change_id` | FK change, null, SET NULL | The pantry change it made, if any. |
| `undone_by_action_id` | str(64), null | Set when an `undo` reversed it. |

### 3.5 `list_note` (quiet notes)

`id` int, `household_id`, `list_id`, `item_id` (null for a list-wide note), `food_id` (null for a list-wide note), `for_login_id` (FK login, cascade: who sees it), `kind` (section 8 table), `text` str(300) (server-made, final wording), `undo_action_id` str(64) null (what the note's Undo reverses), `created_at`, `gone_at` (dismissed, used, or no longer true), `version`.

### 3.6 `double_tick` (the "both ticked" question, spec L280)

`id` int, `household_id`, `list_id`, `item_id`, `tick_ids` JSON (the standing ticks, in server order; 2 or more), `login_ids` JSON (who sees the card: the logins that ticked), `same_login` bool, `created_at`, `answer` null · `two` · `one` · `none` (`none` = closed because a purchase was reversed some other way), `answered_at`, `answered_by_name`, `answer_action_id`, `version`. At most one open question per item; a third tick joins the open one. A tick arriving after the question was answered opens a new one for every purchase still standing (cabledrawer 18 Oct, decision 11).

### 3.7 New columns on existing tables

- `household.list_seq` BigInteger, default 0: the counter. `household.list_purged_seq` BigInteger, default 0: the highest `version` whose rows the tidy-up has deleted (5.5).
- `food.aisle` str(20), null: one of `veg_fruit` · `meat_fish` · `dairy` · `bakery` · `dry_goods` · `tins_jars` · `spices` · `frozen` · `drinks` · `household` · `other`, shown as Veg & fruit · Meat & fish · Dairy · Bakery · Dry goods · Tins & jars · Spices · Frozen · Drinks · Household · Other (spec L288). Null shows under Other. In the ingredient editor under "more". `shop.aisle_order` (already there) holds these keys; null = this default order.
- `food.version` BigInteger, default 0: set to the next counter value whenever something a list shows changes (name, other names, counted as, staple, aisle, usual shop, usual place, sizes, created, merged, removed), so devices pick it up in "changes since".
- `change.kind` gains `shopped` (already reserved in api-0.2 section 3.6) and `repacked` ("Different pack?", 7.4). They're kept apart so an Undo from Pantry can tell the tick itself from a later pack change (5.8).
- `change.tick_id` str(64), null: the purchase (`list_tick.id`) a change was made for: its `shopped` changes, its `repacked` changes, the `moved` change of a put-away, and the `undo` changes that reversed any of them. That's how a purchase finds its own stock (7.2) and how an Undo from Pantry knows to update the list (5.8). Foreign key (`household_id`, `tick_id`) → `list_tick` (`household_id`, `id`) with **no** `ON DELETE` action (SQLite's `SET NULL` on a two-column key would empty `household_id` too, and only Postgres 15+ can null one column). The only thing that deletes `list_tick` rows is the tidy-up (3.9), and it sets `change.tick_id` to null for those purchases first, in the same transaction. Index (`household_id`, `tick_id`).

### 3.8 The device ID

No table. The app makes a random UUID after sign-in (11.8) and keeps it on every queued action; each action is sent with the device ID it was made on (4.1). The server stores it only on `sync_action.device_id`, `list_tick.device_id` and `list_item.ticked_device_id`, to tell "two phones" from "one phone sent it twice". Nothing else about the device is stored.

### 3.9 Keeping and tidying (history job, PR 3)

- Notes: deleted 7 days (the undo window) after they're made.
- Closed questions: deleted after the undo window.
- Neither needs a tombstone: open notes and questions are always sent in full (5.5), so one deleted while a phone was offline simply isn't in that phone's next answer, and the phone drops it. An action naming one is `ignored gone` (5.9).
- Ingredients deleted for good by 0.2's hourly job (api-0.2 section 6.6): the job takes a counter number N under the household lock (5.2, recorded as a server-made `purge` action) and sets `household.list_purged_seq = N`, so every device that's behind gets a fresh full copy (`reset`) instead of keeping a dead ingredient. This happens a few times a year.
- Tombstoned and merged-away items, and removed lists, with their ticks: deleted after `history_months` (12). Before deleting the ticks it sets `change.tick_id` to null on their changes (3.7); the changes themselves stay in the history. `household.list_purged_seq` is raised to the highest `version` deleted.
- `sync_action`: after `history_months`, `payload` and `result` are emptied, but the row (`id`, `seq`, `kind`, `status`) is **kept for good**, so a repeat is always caught however old the queue. It's a few thousand short rows a year.
- (PR 3) Merged-away items have no "merged at" time, so they're tidied 12 months after they were **added**. The `purge` action is made by no one: `login_id` null, `login_name` empty.
- When `shopped` changes are thinned into monthly totals, `list_tick.change_id` becomes null; a later untick still unticks but has no stock to take back.

## 4. Actions

### 4.1 The envelope

A phone sends actions in a **batch**:

```json
POST /api/v1/shopping/actions
{
  "protocol": 1,
  "device_id": "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d42",
  "login_id": 2,
  "since": 1040,
  "sent_at": "2026-10-17T10:02:40Z",
  "actions": [
    { "id": "5d0e…", "kind": "tick", "made_at": "2026-10-17T10:02:11Z", "seen": 1040,
      "item_id": "6f1c…" },
    { "id": "8a77…", "kind": "put_away", "made_at": "2026-10-17T10:02:15Z", "seen": 1040,
      "item_id": "6f1c…", "place_id": 2, "tick_ids": ["5d0e…"] }
  ]
}
```

- `protocol`: always 1 in `/api/v1`. The server accepts protocol 1 for the life of `/api/v1`, so a queue made by an older app version is always understood.
- `login_id`: the login that queued these actions. It must be the signed-in login, or nothing is applied (`409 other_login`, section 5.6).
- `since`: the device's cursor. The answer includes everything that changed after it (5.5).
- `device_id`: a lower-case UUID (3.8), checked in the batch, on each action and on `GET …/changes`; anything else is a 422. It is the default for the batch. An action may carry its own `device_id` (the app always sends the one stored with the queue entry, 11.1), and the server uses that one.
- `sent_at`: the device's clock when it sent the batch. Used only to correct `made_at` for Undo's 7-day window (section 9).
- Every action has `id`, `kind`, `made_at` and `seen`, plus the fields for its kind. At most 100 actions per batch.

### 4.2 The action kinds

All are **queueable offline**. Payload fields are required unless marked optional.

| `kind` | Payload | What the server does (details: sections 6 and 7) |
|---|---|---|
| `create_list` | `list_id` (new UUID), `name` | Makes an extra list. |
| `rename_list` | `list_id`, `name` | Renames any list, main included (new L300). Last received wins, no note. |
| `remove_list` | `list_id` | Hides an extra list. The main list → refused `main_list` (new L300). |
| `add` | `list_id`, `item_id` (new UUID), `food_id` **or** `new_food` `{name, counted_as, staple}`, `amount` (optional), `size_id` (optional), `shop_id` (optional) | Adds an item, or joins an existing line (rule L-12). `amount` omitted or null = blank (rule L-14). `shop_id` omitted = the ingredient's usual shop; `null` = Any shop. |
| `set_amount` | `item_id`, `amount`, `size_id` (optional) | Changes the amount to buy; sets `hand_edited`. On a ticked item it changes only the list, never the pantry (that's "Different pack?"). |
| `delete` | `item_id` | Tombstones the item. |
| `tick` | `item_id` | A purchase: stock into the pantry (section 7). |
| `untick` | `item_id`, `tick_ids` | Reverses the listed purchases that are still standing (rule L-2). |
| `put_away` | `item_id`, `place_id`, `tick_ids`, `use_by` (optional) | Records the place on the item and moves the listed purchases' stock there (7.3). On an unticked item it just records the place for the next tick. |
| `different_pack` | `item_id`, `tick_id`, `count` (whole number 1 to 99), `pack` (base amount of one pack), `size_id` (optional) | "What did you buy?": changes that purchase to `count` × `pack` (7.4). |
| `clear_ticked` | `list_id`, `item_ids` | Tombstones the listed items that still have a standing tick, as one action with one Undo (new L297). |
| `answer_double_tick` | `question_id`, `answer` (`two` · `one`) | Settles the card (new L296). |
| `dismiss_note` | `note_id` | Hides a note (×). |
| `undo` | `undoes` (an action ID) | Reverses that action (section 9). |

Refusals and "ignored" outcomes are per action (5.4); nothing in this table ever causes a pop-up. If something an action names was merged, removed or tidied away while the phone was offline, 5.9 says what happens; that's never a refusal.

### 4.3 Amounts in actions need no conversions

A phone offline can't ask the server an "ask once" question, so **actions only carry amounts that need no conversion**: base-unit numbers (`amount`, `pack`) with an optional `size_id` of that ingredient. The phone converts kg → g and L → ml itself and offers only the ingredient's own sizes and its own base unit (g/kg, ml/L or items). "Other…" in "Different pack?" works the same way. So a sync action never gets `409 ask_once`. Amounts over 1,000,000 base units → refused `too_big` (api-0.2 rule).

### 4.4 New ingredients in `add`

- `new_food` makes the ingredient on the server, unless one with that name already exists (ignoring case and accents, among ingredients that aren't merged away or removed; or matching one of its other names): then the item uses that one, and `counted_as`/`staple` from the action are ignored. (PR 3, cabledrawer 18 Oct, with the 7.1 item "Counted another way") If that one is counted another way than the action's `counted_as`, the action's amount was for the other way of counting, so it isn't kept: the add gets a blank add's amount (the usual size, or 1, or none), and, if the action had an amount, the adder gets the quiet note N9 (8). A removed ingredient still within its undo window with that name is brought back instead of making a second one (5.9). So two phones typing "Tahini" offline get one ingredient (test SY-39).
- `counted_as` and `staple` come from the "How do you count it?" answer (new L299, cabledrawer 18 Oct, decision 2).
- `new_food` may also carry `sizes`: a list (at most 10) of `{name, amount}`, the packet sizes chosen in the same question ("packet = 500 g"; `amount` in base units, so the phone converts kg and L itself, 4.3). They are made with the ingredient, the first one usual, and are part of its `food_created` change, so its Undo takes them too. A name needs letters in it, as in the editor's "Add a size" (`1` is refused `bad_action`). If the name is taken by an existing ingredient, or one removed is brought back, `sizes` is ignored. (cabledrawer 18 Oct, decision 8; it works offline.)
- The ingredient is recorded as a `food_created` change. The action's first change carries the action ID as its `idempotency_key` (keeping api-0.2's promise that the two share one uniqueness); any further changes made by the same action carry none.

### 4.5 What stays online-only

Everything that isn't a list action, as in 0.2: the Pantry screen, the ingredient editor (including "New ingredient"), Undo from Pantry → Recent changes, Settings. Offline, those show "You're offline. This needs a connection." The Shopping screen works fully offline.

## 5. The server

### 5.1 Endpoints (all under `/api/v1`, public, in OpenAPI)

| Request | What |
|---|---|
| `POST /api/v1/shopping/actions` | Apply a batch (4.1). Answers `200` with a result per action and the changes since `since`. |
| `GET /api/v1/shopping/changes?since=N` | Everything that changed after counter N (5.5). `since=0` = a full copy. |
| `GET /api/v1/events` | Server-Sent Events (section 10). |

**The batch answer** (PR 3): `{ "results": [ … ], "changes": { … } }`. `results` holds one result (5.4) per action, in the order they were sent; `changes` is the answer to `changes since` (5.5) for the batch's `since`, read after the last action.

**One way to handle a list change (cabledrawer 18 Oct).** All list writes, online or offline, are handled by the same action code. `POST /shopping/actions` is how devices send them (one at a time when online, as a batch from the offline queue). The plain one-at-a-time list requests from PR 2 (`POST /shopping/lists`, `PATCH`/`DELETE /shopping/lists/{id}`, `POST /shopping/lists/{id}/items`, `PATCH`/`DELETE /shopping/items/{id}`, `POST /shopping/lists/{id}/clear-ticked`) are kept, so the Shopping screen (PR 4) can be built on them while PR 3 is in progress, but PR 3 routes each one through the action handling: a `sync_action` row, a counter number and Undo, exactly as if it had come as an action. So online and offline still behave the same and are tested once. Read views for other apps (such as Home Assistant) can be added later on top of the same rows.

### 5.2 Order and the counter

- A batch is one database transaction. **First** it takes the household's lock, without using a number. On SQLite the transaction must start with `BEGIN IMMEDIATE`, which holds the write lock until commit. That only works as the first statement of a transaction, and signing in has already used the request's session (`auth.find_session` reads the session and may write `last_seen_at`), so the endpoint first commits or ends that transaction, then opens its own with `BEGIN IMMEDIATE` through `lock_household` (or an engine "begin" hook in `db.py`, which has none today). Otherwise the transaction starts deferred, is upgraded later, and can fail with `SQLITE_BUSY_SNAPSHOT` (a 500) (the connection's busy timeout, 30 seconds, must be longer than any batch takes). On Postgres later, `SELECT … FROM household WHERE id = … FOR UPDATE` at the top of the transaction, outside every savepoint (a lock taken inside a savepoint that's rolled back can be released with it). So batches for one household run one at a time.
- Then it reads `household.list_seq` once and takes the actions in array order. For each: look for a repeat (5.3); if it isn't one, apply it inside its own savepoint, so a refused action never undoes the others in the batch.
- Only an action that is **recorded** (applied, merged or ignored) takes the next number, handed out in memory. Repeats and refusals take none. Every row the action changes gets `version = seq`. Just before commit, the last number used is written back to `household.list_seq`. So a batch of nothing but repeats or refusals leaves the counter unchanged, and numbers never have gaps (SY-17, SY-43).
- Every writer that numbers list changes (this endpoint, the server-made changes in 5.8, the tidy-up in 3.9) uses one helper, `lock_household`, that takes the lock first in the same way.
- The answer's `changes` (5.5) are read inside the same transaction, after the last action, so they match the numbers just given out.
- `made_at` is never used for order. A queue from three days ago is applied now, in the order it arrives, after whatever already happened.
- **Server order** of an item's purchases ("Just 1" keeps the first, the card lists them) is the order of the `seq` of the actions that made them (PR 3).

### 5.3 Repeats (same action ID)

Under the household lock, before applying an action, the server looks for its ID in this household's `sync_action` rows and in `change.idempotency_key` (0.2's `Idempotency-Key`):

- Found in `sync_action` with the same `kind` and `payload_hash` → **nothing is applied again**. The result is the stored one, with its original `seq`, plus `"repeat": true`.
- Found with a different kind or payload, or found as a 0.2 `Idempotency-Key` → refused `key_reused` ("That change ID was already used for something else.").
- The same ID twice in one batch: the second is a repeat of the first.
- If writing the `sync_action` row still fails on its key (an `IntegrityError`: something else recorded that ID in between, which the lock should prevent), that action's savepoint is rolled back and it's answered as a repeat of the stored row (or `key_reused` if the payload differs). It takes no number.
- Two copies of one batch at once (the phone gave up waiting after 15 seconds and sent it again while the first was still running): the second waits for the lock, then finds every ID and answers with repeats and the same numbers (SY-48).
- 0.2 writes check the other way round too (5.7).

### 5.4 Per-action results

```json
{ "id": "5d0e…", "seq": 1041, "status": "applied", "reason": null, "repeat": false,
  "item_id": "6f1c…", "change": { "id": 812, "kind": "shopped", "summary": "Bought 1 bunch Coriander → Fridge", "…": "…" },
  "message": null, "food_id": 22 }
```

- `change`: the pantry change where there is one (api-0.2 section 6.1), otherwise the list change the action made (`item_added`, `item_amount`, `list_made` …), so Recent changes and Undo can name it. Null when nothing changed.
- `food_id` (PR 3): for an `add`, the ingredient the item is for: the kept one after a merge, or the one `new_food` made or joined. For `tick`, `untick`, `put_away`, `different_pack` and `answer_double_tick`, the item's ingredient (after merges); for a tick whose stock went to the live ingredient that has the name now (7.1), that one. For an Undo of an action outside that family, the ingredient of the change it undid, if any. Null otherwise.

| `status` | Meaning | Device does |
|---|---|---|
| `applied` | Done. `change` is the pantry change, if any (api-0.2 section 6.1). | Drops it from the queue. |
| `merged` | An `add` joined an existing line; `item_id` is that line. | Drops it; points its own item ID at `item_id`. |
| `ignored` | Recorded, but a rule meant it changed nothing. `reason` says which: `deleted` · `not_ticked` · `already_ticked` · `answered` · `gone` (what it names was tidied away or removed for good while the phone was offline, 5.9) · `nothing_to_undo` · `already_undone` · `cannot_undo` · `too_old` · `no_change`. | Drops it. The changes in the same answer show the true state; a note explains if one is due. `too_old`, `already_undone`, and `gone` with a `message`: toast with `message`. |
| `refused` | Not valid; **not recorded**, so sending it again gives the same answer. `reason`: `bad_action` (missing or wrong fields, an unknown kind, or fields a kind doesn't take), `id_taken` (a "new" list or item ID already in use), `key_reused`, `main_list`, `too_big`. `message` is a plain sentence. | Drops it and shows "1 change couldn't be saved" with `message`. None of these happen in normal use: they mean a bug. Something removed while a phone was offline is never a refusal (5.9). |

`message` carries the partial-Undo sentence where there is one ("Took back 150 g of the 500 g: the rest has been used since.").

### 5.5 Catching up (`changes since N`)

```json
GET /api/v1/shopping/changes?since=1040
{
  "cursor": 1052, "reset": false,
  "lists":  [ { "id": "…", "name": "This week", "main": true, "position": 0, "removed": false, "version": 1044 } ],
  "items":  [ { "id": "6f1c…", "list_id": "…", "food_id": 22, "shop_id": 1,
                "amount": 1, "size_id": null, "display": "1 bunch", "source": "typed", "hand_edited": false,
                "put_away_place_id": null,
                "ticks": [ { "id": "5d0e…", "by": { "login_id": 2, "name": "Wren" }, "at": "…",
                             "place_id": 1, "bought": { "amount": 1, "display": "1 bunch" }, "standing": true } ],
                "added_by": { "login_id": 1, "name": "Tess" },
                "deleted": false, "merged_into_id": null, "version": 1041 },
              { "id": "9e02…", "list_id": "…", "deleted": true, "version": 1046 } ],
  "notes":     [ { "id": 31, "list_id": "…", "item_id": "…", "food_id": 7, "text": "Wren added milk too", "undo": "8a77…", "gone": false, "version": 1050 } ],
  "questions": [ { "id": 5, "list_id": "…", "item_id": "…", "title": "Did you buy 2?",
                   "text": "You and Wren both ticked toor dal while offline, so 2 packets went into the pantry.",
                   "yes": "Yes, 2", "no": "Just 1", "open": true, "version": 1049 } ],
  "foods":  [ { "id": 7, "name": "Toor dal", "other_names": ["arhar dal"], "counted_as": "weight", "staple": false,
                "aisle": "dry_goods", "shop_id": 1, "place_id": 3, "count_word": null, "count_word_plural": null,
                "sizes": [ { "id": 12, "name": "packet", "plural": "packets", "amount": 500, "usual": true } ],
                "removed": false, "merged_into_id": null, "version": 1038 } ],
  "shops":  [ { "id": 1, "name": "Supermarket", "position": 0, "aisle_order": null } ],
  "places": [ { "id": 1, "name": "Fridge", "kind": "fridge", "position": 0 } ],
  "people": [ { "login_id": 1, "name": "Tess" }, { "login_id": 2, "name": "Wren" } ],
  "aisles": [ { "key": "veg_fruit", "name": "Veg & fruit" } ]
}
```

- Rows with `version > since`: lists, items (tombstones as `id`, `list_id`, `deleted`, `version`, plus `food_id`, `shop_id` and `removed_by`) and foods.
- `removed_by` on a tombstone (PR 3, for cabledrawer's 18 Oct decision 10, "Paneer · removed by Wren"): the login name of whoever removed the item, or "Your other phone" when it was your own login on another device. To tell your devices apart, send `device_id` with the request (`GET …/changes?since=N&device_id=…`; the batch answer uses the batch's `device_id`). Without it, or for a removal made through a one-at-a-time request (no device ID), it is the login's name.
- Notes and questions **for the signed-in login** are always sent **in full**: every note that isn't gone and every open question, whatever `since` is. The device replaces its notes and questions with them each time. So a note or card deleted while a phone was offline (3.9) disappears at its next sync, and a dead "Did you buy 2?" can't linger (SY-59). They're a handful of rows. A question closed after `since` is also sent once, with `open: false`, so a device that keeps its copy can drop the card straight away.
- `cursor` is `household.list_seq`. The cursor and the rows come from one snapshot: on SQLite a read transaction is one (WAL mode); on Postgres later the request runs at `REPEATABLE READ`.
- `reset: true` (a full copy without tombstones; the device replaces its copy) when `since` is 0 or below `household.list_purged_seq`. The tombstone tidy-up and ingredients deleted for good both raise it (3.9). A full copy has every live row whatever its `version`, including version 0 (the main list made at sign-up, and rows from before the counter existed on an upgraded install).
- (PR 3, cabledrawer 18 Oct) Also `reset: true` when `since` is **above** the counter: the server was restored from a backup or its database swapped, so the phone's copy can't be trusted. Without this the phone would keep a stale copy and skip every change up to its old cursor.
- `display` is the server's as-sold wording (api-0.2 section 5). Items show only what lists need; the pantry is not in the offline copy. On a list (items and `bought`) a count ingredient with a size reads in that size when the amount is a whole number of them ("2 boxes" for 12 eggs bought by the box of 6), and the pantry's "left" ("12 left") never shows (PR 3, SY-65).
- `foods` are the ingredients the device needs for the list **and the add box** (search offline by any name): every ingredient that isn't merged away or removed. A household's few hundred names are small.

### 5.6 Sign-in, household and request errors

- Needs a signed-in session cookie and passes the same-origin check, as every write in 0.1/0.2. (API tokens arrive in 0.8 and will use the same endpoint.)
- Everything is scoped to the login's household. An ID from another household is treated exactly like one that isn't there (5.9): nothing of the other household is read, changed or revealed. Changes and events never include another household.
- Request-level errors (nothing is applied, the queue stays on the device):

| Status | `code` | When |
|---|---|---|
| 401 | — | Not signed in, or the session ran out. |
| 403 | — | Failed the same-origin check. |
| 409 | `other_login` | `login_id` in the batch isn't the signed-in login ("These changes were made by another login."). |
| 413 | `too_many` | More than 100 actions. |
| 422 | `bad_protocol` | `protocol` isn't 1. |
| 422 | — | The envelope itself is malformed (FastAPI's list form). A malformed **action** inside a good envelope is a per-action `refused`. |

The 409 and 413 answers are in OpenAPI as `Refusal` (`detail`, `code`), the shape every 0.2 error has.

### 5.7 How it sits beside the rest of the API

- 0.2's `Idempotency-Key` header still works on pantry and ingredient writes. Action IDs and those keys share **one** uniqueness per household, checked both ways: a sync action whose ID is a 0.2 key → `key_reused` (5.3), and 0.2's `history.replayed()` also looks in `sync_action`, so a 0.2 request whose key is an action ID gets `409 key_reused`. PR 2 makes that change to `replayed()` (test SY-20).
- The change log, Recent changes and Undo from Pantry (api-0.2 section 6.5) see `shopped` and `repacked` changes like any other, except for the Undo cases in 5.8.

### 5.8 Server-made list changes

Some changes reach lists from outside a batch. Each takes the household lock and a counter number (5.2) and is recorded in `sync_action` with a server-made UUID and `device_id` null, so devices see it through "changes since" and events:

- **Undo from Pantry → Recent changes of a purchase's own `shopped` change** (the one in `list_tick.change_id`) isn't a plain 0.2 Undo. It runs the full reversal in 7.5 (every amount change of that purchase not yet undone, newest first, `repacked` included) and unticks it on the list (`kind` `untick_by_undo`). So undoing the tick while a "Different pack?" still stands takes the whole purchase out; it never leaves 900 g in the pantry with the item unticked (SY-50). The list and pantry never disagree.
- **Undo from Pantry of a purchase's other changes** (found by `change.tick_id`) is a plain 0.2 Undo, plus keeping the list in step, and never unticks: a `repacked` change → the purchase's `bought` goes back to what it was before (SY-49); a put-away's `moved` change → `list_tick.place_id` goes back, and so does the item's chosen place if it's still the one moved to (`kind` `place_by_undo`, SY-51).
- **Ingredient edits** that lists show bump `food.version` (3.7); a usual-shop change also moves items (3.2, `kind` `follow_shop`).
- **Merging ingredients** moves the merged-away ingredient's list items to the kept one (the merge's undo snapshot includes them; Undo moves them back). Two lines that become the same ingredient stay two lines.
- **Removing an ingredient** is blocked while it is on a list that isn't removed, or was removed less than the undo window ago. Tombstones don't block. When the ingredient is finally deleted, its tombstoned items go too.

### 5.9 When something changed while the phone was offline

While a phone holds actions, someone online can merge or remove an ingredient, or remove a size, place or shop, and notes and questions are tidied away after 7 days. That's normal use, so none of it is a refusal. An ID that isn't in this household (removed for good, or never in it, including another household's) is handled the same way, so nothing reveals what other households have.

| An action names… | What the server does | Test |
|---|---|---|
| An ingredient merged into another | Follows `food.merged_into_id` to the end of the chain and uses the kept ingredient. An `add` adds the kept ingredient, with the kept ingredient's usual shop (unless the action gave one), and joins its line if rule L-12 matches. | SY-52 |
| An ingredient removed but still in its undo window | An `add` brings it back to Ingredients, the way 0.2's Undo does when stock goes back into a removed ingredient (recorded `brought_back`, api-0.2 section 6.6), and `message` says "Eggs is back in Ingredients." If its name (or an other name) is now used by another ingredient (0.2's `_name_taken`), the add goes to that ingredient instead and the old one stays removed. Undo of the add removes the brought-back ingredient again, as 0.2's Undo of a `brought_back` does. (PR 3) Not while it has stock or is on a list (0.2's rule for removing an ingredient, `cannot_remove`, merges followed): then it stays in Ingredients, and the Undo still takes the add back. A rename or other edit after the bring-back doesn't stop it being removed again: the Undo only puts back what the add changed. | SY-53, SY-66 |
| An ingredient deleted for good | `add` → `ignored gone`, `message` "Eggs was removed from Ingredients, so it wasn't added." (Its list items were deleted with it, 5.8, so nothing else can name it.) | SY-54 |
| A place that's gone (`put_away`, or a tick using the item's chosen place) | The ingredient's usual place, else the first Cupboard place, as for a tick with no choice (7.1). The item's chosen place is cleared, which raises the item's `version` so phones see it. | SY-55 |
| A size that's gone (`add`, `set_amount`, `different_pack`) | The amount is kept (actions carry base amounts, 4.3) and shown in the usual size or base unit, as 0.2 does for lots. `different_pack` makes the size again if it needs one (7.4). | SY-56 |
| A shop that's gone (`add`) | The ingredient's usual shop, else Any shop. (Items already in that shop went to Any shop when it went: `SET NULL`.) | SY-57 |
| A list or item tidied away for good (after 12 months) | `ignored gone`. So is an Undo of an action whose list or item has been tidied away (PR 3). | SY-58 |
| A note that's gone (`dismiss_note`) | `ignored gone`, quietly. | SY-58 |
| A question that's closed or gone (`answer_double_tick`) | `ignored answered` if it's closed but still kept, `ignored gone` if it was tidied away. Nothing changes in the pantry. | SY-58, SY-59 |

## 6. The rules

Every rule in spec section 6 "Offline shopping-list sync", and cabledrawer's 17 Oct answers, with what the server does and the tests that prove it. Test IDs are in section 14. "Other device" means a different `device_id`, even for the same login.

| # | Rule (spec wording, shortened) | What the server does | Spec | Tests |
|---|---|---|---|---|
| L-1 | Phone keeps a queue of actions, each with its own phone-made ID; server works through it in the order received (a server counter, not device clocks); an action sent twice is ignored; tick-off is idempotent. | Sections 4 and 5: one counter per household, numbers in commit order, repeats answered from `sync_action`. | L267, L252 | SY-17, SY-18, SY-19, SY-20, SY-43 |
| L-2 | **A tick sticks.** An untick counts only if it comes after the tick. | `untick` names the ticks the person saw (`tick_ids`). Only those still standing are reversed; any tick it didn't name stays. An untick naming nothing standing → `ignored not_ticked`. | L271 | SY-04, SY-05, SY-27 |
| L-3 | **Both ticked offline** = two purchases, both into the pantry, then "Did you buy 2?" (Yes, 2 · Just 1) as a card, not a pop-up; "Just 1" removes the extra, with Undo. | A `tick` from another device on an item with a standing tick is a **second purchase** (its own stock and `shopped` change) and opens a `double_tick` question, if the purchases put stock in (not for staples or no amount). "Just 1" reverses every purchase after the first in server order; its Undo puts them back and reopens the card. A tick from the **same** device on an item it already ticked, with no untick between → `ignored already_ticked`. A tick arriving after the card was answered opens a new card for every purchase still standing (cabledrawer 18 Oct, decision 11). | L272 | SY-01, SY-03, SY-23, SY-24, SY-28 |
| L-4 | **Same login on two phones:** still asks, worded "This was ticked on two phones". | Same as L-3 (devices differ); `same_login` picks the wording (section 8). | L284 | SY-02 |
| L-5 | **A hand edit beats the app's own sums.** Plan-made items are keyed by ingredient + shop. | `set_amount` sets `hand_edited`. Every action-made item has `source = typed`. 0.6's plan update changes only `source = plan` items with `hand_edited` off, matched by (list, ingredient, shop), and never brings back a tombstoned plan item. | L273 | SY-44 |
| L-6 | **Deleted stays deleted.** Deletes leave a tombstone so an old offline phone can't bring an item back. | List-side actions on a tombstoned item (`set_amount`, `delete`, `put_away`'s list part) → `ignored deleted`. Only an explicit `undo` of the delete brings it back. Pantry-side actions still count (L-9, L-10). | L274 | SY-06, SY-07, SY-45 |
| L-7 | Extra lists work the same way (offline, sharing, put-away); ticked items on any list still go into the pantry. Extra lists can be renamed and removed (Undo); the main list can be renamed, never removed. | All rules apply on every list. A removed list is hidden, not frozen: queued actions still apply inside it, ticks still put stock in, and the person whose queue hit it gets a list-wide note; Undo of the removal brings it back with everything (cabledrawer 18 Oct, decision 6). `remove_list` on the main list → refused `main_list`. | L442, L94, new L300 | SY-32, SY-33 |
| L-8 | **Put away offline** is queued with the tick. | `put_away` is its own queued action, sent in queue order right after the tick. | L275 | SY-14 |
| L-9 | **Tick against a delete** (answer 2): the tick still counts as bought, pantry gets the stock, the item stays off the list; quiet note "Wren had removed this. Your tick still went into the pantry" + Undo. | Either order: the purchase happens, the item stays tombstoned, and the ticker gets note N1 (Undo reverses their tick). In tick-then-delete order the note is due when the delete's `seen` is before the tick (the deleter hadn't seen it). | new L292 | SY-08, SY-09 |
| L-10 | **Untick after a tick** (answer 3) takes the stock back out the way Undo does; if some was used since, only what's left, never below zero. | Reverses the purchase with api-0.2's Undo of its pantry changes (7.5). Also on a tombstoned item: stock comes out, the item stays off, note N5. | new L293, L385 | SY-26, SY-38 |
| L-11 | **No conflict pop-ups.** Other clashes show as a quiet note with Undo. | No action is ever refused because of what someone else did. Clashes give the notes in section 8. | L276 | SY-06 to SY-13 |
| L-12 | **Both add the same ingredient** offline (same list, same shop, both unticked) (answer 4): one line, keeping the bigger amount; quiet note "Wren added milk too" + Undo. | An `add` whose (list, ingredient, shop) matches a live line with no standing tick → `merged` into the oldest such line. **A clash** (the add came from another device that hadn't seen that line: `seen` before the line's add): the line keeps the bigger amount (no amount counts as smallest; the kept amount's `size_id` comes with it), and both adders get note N2. **Not a clash** (the person could see the line, or the line was made on the same device, which always counts as seen even when its own `seen` is older): the amounts add up (2 L + 1 L = 3 L), no note (cabledrawer 18 Oct, decision 8). Adding up adds the base amounts and keeps the line's `size_id` ("1 packet" + 250 g of a 500 g packet = 750 g, shown as "1½ packets"); no amount + an amount = that amount. The phone's `applyLocal` does the same, so what it shows matches. A different shop or list → a separate line. A line that's already ticked → a separate line. The qualifier "same list, same shop, neither ticked" was confirmed by cabledrawer on 18 Oct (decision 9). | new L294, new L310 | SY-10, SY-11, SY-39, SY-47, SY-64, SY-65 |
| L-13 | **Both change the same amount** offline (answer 5): the change the server receives last wins; quiet note. | `set_amount` always applies. If an amount change from another device landed after this one's `seen`, the person it overwrote gets note N3 (Undo puts their amount back). | new L295 | SY-12 |
| L-14 | **Typing something that isn't an ingredient** makes a new one ("How do you count it?"); blank amount = one of its usual size, or 1 if counted in items (answer 11). | `new_food` (4.4). Blank: the usual size × 1 (`size_id` set); count ingredients: 1; otherwise no amount (cabledrawer 18 Oct, decision 1). | new L299 | SY-39, SY-40 |
| L-15 | **Ticking into the pantry:** the ingredient's usual place, or Cupboard; no use-by unless chosen. Ticking an item moves it into the pantry; the user can say where. | Section 7.1. | L286, L195 | SY-46 |
| L-16 | **Items that aren't food** are ingredients with Staple on: ticking never adds stock. | Staple: the tick is recorded on the list, no stock, no `shopped` change, no card. | L287 | SY-28 |
| L-17 | **Different pack on the day:** change the pack when ticking; the pantry gets what was bought; the new size is added to the ingredient's sizes. | `different_pack` (7.4); a new size is marked `added_when_shopping`. | L345, L95 | SY-15, SY-16 |
| L-18 | **"Did you buy 2?"** shows to both people; the first answer settles it and the card disappears for the other (answer 6). On Shopping only until 0.6 (answer 7). | The card goes to the logins that ticked. The first `answer_double_tick` applies; later ones → `ignored answered`. The question goes out as closed, so the card disappears. Reversing a purchase another way closes it as `none`. | new L296 | SY-25, SY-27, E1, E1s |
| L-19 | **Ticked items** fold into "In the trolley · N" at the end of each shop; "Clear ticked" removes them, with Undo (answer 8). | `clear_ticked` tombstones the listed items that still have a standing tick (an item unticked meanwhile stays). A later tick on a cleared item still counts (as L-9; the card, if any, explains it, so no N1 note). The fold itself is the screen's job (section 13). | new L297 | SY-29, SY-30, SY-31 |
| L-20 | **No usual shop** → "Any shop", shown last (answer 9). | `shop_id` null. | new L298 | FE-1 |
| L-21 | **Aisles:** optional per ingredient, default names and order; headings use the spec's names (answer 10). | `food.aisle` (3.7). | L288, new L288 | FE-1 |
| L-22 | **How long offline:** plan for about 3 days; older queues still applied, never thrown away. | No age limit on actions. Undo's 7-day window counts from when the person pressed Undo (section 9), so a queued Undo still works. | L277 | SY-21, SY-22 |
| L-23 | **Sign-in runs out while offline:** the queue stays and is sent once the same login signs back in; a different login gets the sign-out warning first. | `401` keeps the queue; `409 other_login` refuses another login's batch. Device side in 11.5. | L285 | SY-34, SY-35, FE-3 |
| L-24 | **What the phone keeps offline** in 0.3: the app and the shopping lists. | 11.1 (the lists, plus the ingredient names for the add box). | L289 | E2 |
| L-25 | **App updates:** install quietly next time the app opens, never mid-shop; waiting changes sent first. | 11.6: the new version sends the old version's queue (protocol 1) before it shows the list. | L290 | FE-4 |
| L-26 | **Connection status:** see UX principle 16. | 11.4. | L278, L71 | E2 |
| L-27 | **Signing out** wipes the device's offline copy with a warning first if changes haven't been sent (answer 14 wording). | Section 12. | L468, L93, new L302 | E3 |
| L-28 | **Undo reverses just that change**; never below zero; anyone in the household can undo within 7 days. | Section 9. | L385, L386 | SY-23, SY-26, SY-31 |
| L-29 | **Main list subtitle** (answer 13). | Screen (section 13), from `people`. | new L301 | FE-2 |
| L-30 | **Who did it:** each change records the login. | `shopped` and `undo` changes carry the action's login; summaries say who in Recent changes. | L379 | SY-01 |
| L-31 | Every table has `household_id`. | Section 3; isolation tests. | CLAUDE.md | SY-41 |
| L-32 | **Put away on two phones** with different places. | Like answer 5: the last received wins and the overwritten person gets note N6 (cabledrawer 18 Oct, decision 3). | new L305 | SY-13 |
| L-33 | **Only the server changes pantry stock.** | No action carries pantry amounts except `different_pack` (what was bought). An unknown kind, or a field a kind doesn't take → refused `bad_action`. The device's `applyLocal` has no pantry and the offline copy holds none (11.2). | L267 | SY-60, FE-5, P-1 |
| L-34 | **The protocol is part of the public API** (`/api/v1`, OpenAPI); the web app uses no private endpoints. | The three endpoints, every action kind's payload and every result are in `/api/v1/openapi.json` with their schemas. Every list write, including the one-at-a-time list requests kept from PR 2, goes through the action handling (5.1, cabledrawer 18 Oct). | L267, L258 | SY-61 |
| L-35 | **`idb`** (ISC) is approved for the queue; the PR that adds it pins an exact version released at least two weeks earlier. | PR 6 adds `idb` at an exact version (no `^` or `~`), names it and its release date in the PR, and `./check`'s licence step passes. | new L291 | FE-6 |
| FE-7 | | | | | **PR 6.** Two devices: A holds 2 waiting changes and sees a `reset: true` answer (the server was restored, so A's cursor is ahead of it): A's `copy` is replaced, its `queue` is kept and sent in order afterwards; the final list and pantry match what the changes mean on the new copy. | | | FE |

## 7. The pantry side of a tick (PR 3)

### 7.1 A tick

- **Place:** the item's `put_away_place_id` if one was chosen, else the ingredient's usual place, else the first `cupboard` place ("Cupboard"), using `stock.default_place` (spec L286).
- **Amount:** the item's amount at the moment of the tick, stored on the purchase (`bought_milli`, `bought_size_id`). Lots are made as 0.2's add does (api-0.2 section 3.5): "2 packets" makes two one-packet lots, "1½ packets" a full and a half lot, "1 dozen" eggs one lot of 12, a typed amount one lot with no size. Reuse `stock.py`'s add, don't copy it.
- **Use-by:** none (spec L286). 0.3 offers no use-by when shopping; `put_away`'s optional `use_by` is there so a later screen can add it without changing the protocol. Ticking into a freezer place sets no `frozen_on`.
- **Staples** (L287) and **items with no amount**: no stock and no change. The tick is still recorded on the list.
- **Change log:** one `shopped` change per purchase, `login` = the action's login, `at` = server time, `idempotency_key` = the action ID, summary "Bought 2 packets Toor dal → Cupboard" (same pattern as "Added … → Cupboard"), one `change_line` per lot. It appears in Pantry → Recent changes with Undo like any change.
- **Two ticks = two purchases** (L272): each has its own lots and `shopped` change.
- (PR 3) The summary's amount uses 0.2's pantry wording, so a count word reads "Bought 1 bunch of Coriander → Fridge".
- (PR 3, cabledrawer 18 Oct) A tick on a removed item whose ingredient has since been removed (not yet deleted for good) brings the ingredient back, as an `add` would (5.9): the purchase needs it in the pantry. If its name is a live ingredient's now, nothing is brought back and the stock goes to that one (no second "Paneer"). A tick that puts nothing in (a staple, or no amount) brings nothing back. An Undo of the tick takes the stock out and removes the brought-back ingredient again, as an Undo of an `add` does (5.9), unless it has other stock or is on a list by then (0.2's rule for removing an ingredient, `cannot_remove`, merges followed). Then the ingredient stays, and the Undo still takes the tick back. As for the add, a rename after the bring-back doesn't stop it being removed again. An untick, or an Undo from Pantry → Recent changes, leaves it in Ingredients.
- (PR 3, cabledrawer 18 Oct) **Counted another way:** if the live ingredient with that name is counted another way than the removed one (the old Paneer by weight, the new one in items), the old amount is never carried across: it would file 400 g as 400 items. A tick records the purchase with no stock and no change, and the ticker gets a quiet note N8 (8) whose Undo takes the tick back. An `add` through the removed ingredient gets a blank add's amount for the live one (its usual size, or 1), and, if it had an amount, the adder gets note N9, as for a typed new ingredient. A `new_food` that matches an ingredient counted another way than the action says is handled the same way, with note N9 (4.4).

### 7.2 What a purchase's stock is

A purchase's stock is the lots named by the change lines of its own changes (every change whose `change.tick_id` is this purchase: its `shopped` and `repacked` changes and the `undo` changes that reversed them), wherever those lots are now and however much is left.

### 7.3 `put_away` after the tick

- Records `put_away_place_id` on the item, then, for each purchase in `tick_ids` that's still standing, moves that purchase's lots that are not empty and still in the purchase's place to the new place, as one `moved` change ("Moved Coriander → Freezer", with `tick_id`), with its own Undo (5.8 keeps the list in step). `list_tick.place_id` is updated.
- History therefore shows "Bought 1 bunch Coriander → Fridge" then "Moved Coriander → Freezer". Each line reverses cleanly with 0.2's Undo; we don't rewrite the first change.
- On a tombstoned item the stock still moves (it's about where the shopping went); only the list part is ignored.
- (PR 3) The list side is recorded as a list change of kind `item_place`, summary "Put away Coriander → Freezer", so it shows and undoes like the other list changes.

### 7.4 `different_pack`

The person says purchase `tick_id` was really `count` × `pack`:

1. **Size:** if the ingredient has a size of exactly `pack` (or `size_id` names one), use it. Otherwise add one, named like the usual size ("packet"), or "pack" if there is none, with `added_when_shopping` on (api-0.2 section 3.3). The new size is not made usual.
2. **Stock:** `used_since` = what the purchase put in minus what's left in its lots now. Empty the purchase's lots, make `count` lots of `pack` in the purchase's place, then take `used_since` from them (oldest first), never below zero. So a 400 g purchase with 100 g used, changed to 1 kg, leaves 900 g.
3. **Records:** one `repacked` change (with `tick_id`), summary "Paneer: bought 1 pack · 400 g instead of 2 packs · 400 g" (as-sold wording for both), with its own Undo. The purchase's `bought_milli`/`bought_size_id` are updated. The item's own amount ("Planned 2 × 200 g") stays.
4. On a tombstoned item it still applies.
5. **Undo of an older `different_pack`** (from a list, or its `repacked` change from Pantry → Recent changes) first undoes that purchase's later `repacked` changes that still stand, newest first, as part of the same Undo. Undoing the older one alone would fill its old lots again on top of the newer ones (PR 3, found in review). The later `different_pack` actions count as undone.
6. **Open question for cabledrawer (PR 3):** Undo after some of the new packs were used is 0.2's Undo, which fills the old lots back as they were and takes out only what's left of the new ones. Bought 400 g, used 100 g, changed to 1 kg (900 g), used 850 g, Undo → 300 g, though 950 g was used. Never below zero, but more than is really there. The alternative is to treat the Undo as another `different_pack` back to the old packs (empty the purchase's lots, make the old ones, take what was used since). For now the Undo's message says what happened in pack terms, not 0.2's take-back sentence ("Took back 300 g of the 400 g: the rest has been used since." would be wrong: nothing was taken back): "Paneer is back to 2 packs · 400 g. Some had been used since, so check how much is left."

### 7.5 Taking a purchase back (untick, "Just 1", Undo of a tick)

- **Reversing a purchase** = api-0.2's Undo of each of its amount changes that isn't undone yet, newest first (its `repacked` changes and any put-back change, then its `shopped` change). Each puts back what it can, never below zero, and says so ("Took back 300 g of the 500 g: the rest has been used since."). Moves are left alone; they don't change amounts. The `undo` changes carry the purchase's `tick_id`, and their lines say exactly how much came out of which lot. Summaries: "Unticked: Bought 2 packets Toor dal → Cupboard", "Just 1: took back 1 packet Toor dal".
- The purchase gets `reversed_at`. The item's `ticked_*` copy follows the first purchase still standing, or clears. A reversed purchase closes an open question as `none` unless that's how "Just 1" settled it.
- **Putting a purchase back** (Undo of an untick or of "Just 1") puts back **exactly what the reversal took out, lot by lot**, no more: one new `shopped` change ("Ticked again: 300 g Toor dal → Cupboard", with `tick_id`) whose lines are the reversal's lines the other way round, into the same lots (or, if a lot has since been deleted, a new lot of that amount in the purchase's place). If the reversal took back 300 g because 200 g had been used, putting it back gives 300 g, not 500 g (SY-26u, SY-24u). It clears `reversed_at`, points `list_tick.change_id` at the new change, and puts back the purchase's `bought` as it was when it was reversed. (0.2 has no redo, so we don't undo the undo.) Undo of "Just 1" also reopens the card.
- **Undo from Pantry → Recent changes** of a purchase's changes: 5.8.

## 8. Notes and the card

Notes are server-made, final wording, addressed to one login (`for_login_id`), shown on Shopping under the item, or where the item was if it's off the list (cabledrawer 18 Oct, decision 10), or at the top of the list for list-wide notes. Each has Undo and ×. A note goes away when dismissed, when its Undo is used, when what it describes is undone some other way, or after 7 days.

`{who}` is the other person's login name ("Wren"). For the same login on another phone it is "Your other phone". Ingredient names appear exactly as the household typed them.

A note whose Undo would name an Undo (`undo`, `untick_by_undo`, `place_by_undo`) has no Undo, only ×: an Undo can't be undone (9) (PR 3).

| Note | When | Text | Undo reverses |
|---|---|---|---|
| N1 | Tick against a delete (L-9) | "{who} had removed this. Your tick still went into the pantry." (new L292) | The ticker's tick (stock out). |
| N2 | Both added (L-12), to both adders | "{who} added {name} too" (new L294) | The later add (the line goes back to the earlier amount; the later add is gone). |
| N3 | Amount overwritten (L-13), to the overwritten person | "{who} changed {name} to {amount}" | The winning change (your amount back, if it's still theirs). |
| N4 | Edit against a delete, either order (L-6), to the editor | "{who} had removed {name}, so your change wasn't kept." | The delete (the item comes back as it is now). |
| N5 | Untick on a tombstoned item (L-10), only when the untick took stock out (PR 3) | "{who} had removed this, so it isn't back on the list. Your untick took it out of the pantry." | The untick (stock back in). |
| N6 | Put away overwritten (L-32) | "{who} put {name} in the {place}" | The winning put-away (stock moved back). |
| N7 | Queued actions hit a removed list (L-7), one per login | "{who} had removed {list}. Your changes are kept with it." plus, if it had ticks, " Your ticks still went into the pantry." | The removal (the list comes back). |
| N8 | A tick whose ingredient was removed, and the live ingredient with its name is counted another way (7.1, PR 3, cabledrawer 18 Oct), to the ticker | "{name} is counted differently now, so nothing went into the pantry." | The tick (the purchase is taken back). |
| N9 | An `add` with an amount whose ingredient is counted another way than the action meant: a `new_food` whose name is taken by one counted another way (4.4), or an `add` through a removed ingredient whose name is a live one's counted another way (7.1) (PR 3, cabledrawer 18 Oct), to the adder | "{name} was already in Ingredients, counted another way, so check the amount." | The add. |

**The card** (L272, L284, new L296), from the mockup (`Shop.dc.html`):

- Title "Did you buy 2?"; text "You and Wren both ticked toor dal while offline, so 2 packets went into the pantry."; buttons **Yes, 2** · **Just 1**.
- Same login: "This was ticked on two phones, so 2 packets went into the pantry."
- Three or more ticks: "Did you buy 3?", "You, Wren and Arlo all ticked …", **Yes, 3** · **Just 1**.
- Shown to the logins that ticked, on Shopping only until 0.6 (answer 7). The first answer closes it for everyone.
- After "Just 1": toast "Took back 1 packet Toor dal" (or the partial sentence) with Undo. After "Yes, 2": toast "Kept 2 packets" with Undo (brings the card back).

## 9. Undo

- Every list action except `undo`, `dismiss_note` and `refused` ones can be undone with `undo {undoes: <action ID>}` by anyone in the household (L386). The Undo toast on the phone uses the action ID, so it works offline, even before the original has been sent. Both go in the queue, in order.
- What each Undo does: `create_list` → removes the list; `rename_list` → the old name (if it's still this one); `remove_list` → back; `add` → the item is tombstoned (or, if `merged`, the line goes back to its earlier amount); `set_amount` → the earlier amount, if the item still has this action's amount; `delete`, `clear_ticked` → the items it removed come back; `tick` → reverses that purchase (7.5); `untick`, "Just 1" → puts the purchases back (7.5); `put_away` → stock moved back (0.2 move Undo rules) and the item's earlier place; `different_pack` → 0.2 Undo of its `repacked` change (after any later ones of that purchase, 7.4), and the purchase's `bought` goes back; `answer_double_tick` "two" → the card comes back.
- The server-made rows in 5.8 that Recent changes can undo can be undone the same way (PR 3): `food_edit`, `follow_shop` and `merge_foods` → 0.2's Undo of their change. `untick_by_undo`, `place_by_undo` and `purge` can't (`ignored cannot_undo`), like `undo`.
- **Window:** 7 days (the household's undo window), from the undone action's `applied_at` to when the person pressed Undo. Phone clocks can be wrong, so the server corrects the phone's time: each batch carries `sent_at` (the phone's clock when it sent, 4.1), and the time Undo was pressed is taken as `made_at + (server time − sent_at)`. That cancels a phone clock that's simply fast or slow, by any amount. The result is then kept between the undone action's `applied_at` and now. An Undo queued in time is never lost because the phone was offline (SY-22, SY-22b, SY-63). It still trusts the phone not to have its clock changed between pressing Undo and sending; this is a convenience window, not a security rule, so that's accepted. Too late → `ignored too_old`, toast "Too late to undo: changes can be undone for 7 days."
- (PR 3) Undo of "Just 1" while a newer card is open for the same item: the purchases put back join that card instead of reopening the old one. Undo of "Yes, 2" when fewer than 2 of its purchases still stand → `ignored nothing_to_undo` (there's no question to ask again).
- Undo of an Undo → `ignored cannot_undo` (no redo, as 0.2). Already undone → `ignored already_undone`. Undo of an ignored action → `ignored nothing_to_undo`.

## 10. Live updates (PR 5)

`GET /api/v1/events`, `text/event-stream`, same-origin cookie, from our own server only (no third-party push service). Built with FastAPI/Starlette's `StreamingResponse`: no new dependency.

```
retry: 5000

event: hello
data: {"cursor": 1052}

event: shopping
data: {"cursor": 1053}

event: pantry
data: {"change_id": 815}

: keep-alive
```

- `hello` on connect; `shopping` after any commit that raised the household's counter ("lists changed up to N"); `pantry` after any stock change (so an open Pantry screen re-fetches). `pantry` is sent only for stock changes; an ingredient renamed or made a staple elsewhere is picked up by the foreground re-fetch, not by an event. Nothing else: no list contents, no names. A device that gets `shopping` with a cursor above its own calls `GET /shopping/changes?since=…`.
- Only to sessions of the same household. Sent after commit, never before.
- A comment line every 25 seconds keeps proxies from closing it; the session is re-checked each time, and the stream ends with `event: signed_out` when it runs out.
- Headers `Cache-Control: no-store` (as on all of `/api`, section 12) and `X-Accel-Buffering: no` (so nginx-style proxies don't hold events back). The reverse-proxy docs get a line about it.
- One in-process broadcaster: the container runs one server process. (Several processes, or Postgres, would need Postgres `LISTEN/NOTIFY`; noted for later.)
- If the stream drops, the browser reconnects by itself; the app also re-fetches changes when it comes back to the foreground.

## 11. The device (PR 6)

### 11.1 What the phone stores

One IndexedDB database `mealwright` through `idb` (ISC, approved 17 Oct; pin an exact version released at least two weeks earlier, and name it in the PR):

- `meta`: `device_id`, `login_id`, `login_name`, `username`, `household_id`, `cursor`, `protocol`.
- `copy`: the offline copy from "changes since" (lists, items, notes, questions, foods, shops, places, people, aisles), one store per kind, keyed by ID.
- `queue`: auto-numbered entries `{ action, login_id, device_id, queued_at, tries }`, oldest first. `action` already carries its own `device_id`, so it's sent as made even if the device ID changes later.

**On a reset (cabledrawer 18 Oct):** when the server answers `reset: true` (a first copy, a tidy-up, or a phone ahead of a restored server), the phone throws away only its **copy** of the list data (`copy` and `cursor`). The `queue` is **kept**: changes still waiting are sent after the fresh copy arrives, in order, and the screen shows them on top of the new copy. Nothing the person did offline is lost.

The service worker (SvelteKit's own) caches only the app shell. List data lives in IndexedDB, never in the HTTP cache.

### 11.2 Optimistic display

- The screen shows **the copy with the queue applied on top**, using one small pure function (`applyLocal(copy, actions)`). A new action is added to the queue and shown at once (UX principle 8, L63).
- `applyLocal` does the list part only: tick marks the item ticked by me, add inserts (or joins a matching unticked line, adding the amounts as L-12 does for a line this phone could see or made itself), and so on. It never works out pantry stock (only the server changes the pantry, L267). Display text for items the phone made itself uses a simple local format ("2 packets", "400 g") until the server's `display` arrives.
- After every answer from the server: update the copy from `changes`, drop the answered actions, map merged item IDs, and show `applyLocal(copy, what's left in the queue)` again.

### 11.3 Sending

- **One batch in flight at a time**, the oldest up to 100 queued actions of the signed-in login, in queue order. Never reordered, never merged, never dropped except by its result or by "Sign out and lose them".
- Send straight after a new action (gathering anything made within 250 ms), and on: the browser's `online` event, the app opening or coming to the foreground, the event stream reconnecting, "Try now", and the retry timer.
- **No answer, a network error, a timeout (15 s), or 5xx** (including a proxy's 502 to 504): send **the same batch** again after 2, 4, 8, 16, 30, then every 60 seconds, each ±20%. Repeats make this safe (5.3). Back to normal after any success.
- `401`: stop sending and keep the queue (11.5). `409 other_login`: don't send (11.5). `413`: halve the batch and carry on. `422`: a bug; keep the queue, stop, show "Couldn't send your changes" with Try now.

### 11.4 "N changes waiting" and connection status (UX principle 16, L71)

- **N** = the number of queue entries for the signed-in login, including the batch in flight. One tap is one action, so ticking an item and choosing Freezer is 2.
- **Offline** = the last request failed with a network error or timeout, or the browser says it's offline. A blip under 3 seconds shows nothing.
- Offline: phone "Offline — 3 changes waiting" with Try now, above the bottom tabs; desktop "Offline · 3 changes waiting. They'll save when you're back." with Try now at the foot of the sidebar, a small dot when collapsed (mockups). With nothing waiting it says just "Offline".
- Shopping's subtitle while offline: "12 to buy · offline, saving on this phone" (desktop "… on this computer"), from the mockups.
- Back online and the queue empty: a short toast "Back online — all saved". Nothing extra while all is well.

### 11.5 Sign-in runs out while offline (L285)

- A `401` keeps the queue. When online the app asks the person to sign in again: "Please sign in again. Your 3 changes are kept on this phone." ("this computer" on the sidebar layout, as every "this phone" in these messages is worded by layout.)
- The **same login** signs back in → the queue is sent at once.
- The same login signing back in keeps the device ID (a session running out isn't a sign-out), so the queued actions still count as this phone's (SY-62).
- A **different login**: the queue is never sent under another login (the server refuses it anyway with `409 other_login`). The warning comes first, worded as decision 4 in section 16 (new L306). If they carry on, the **whole offline copy** is wiped, not just the queue, exactly as at sign-out (section 12), and a new device ID is made (FE-3). The wipe happens only once the new login's sign-in has succeeded: a wrong password wipes nothing.
- The waiting changes are read again just before the warning is decided and just before the wipe, since another tab may have queued some since the sign-in page opened. Carrying on loses only what the warning showed: the warning remembers the action IDs it showed, and if any change is waiting by then that it didn't show, it warns again with the new count. It compares which changes, not how many (another tab may have sent one it showed and queued a new one).
- A different login can't get past the warning another way. If the app opens already signed in as another login (say, signed in in another tab) while this device holds someone's waiting changes, it doesn't touch them: `meta`, the device ID, the copy and the queue stay exactly as they are, and nothing is sent. That login is signed out again (`DELETE /api/v1/session`) and goes to the sign-in page with its username filled in, which shows the warning.
- Right after that, and only then, the sign-in page says why, in place of the usual "Wren's 3 changes are waiting on this phone…" line (cabledrawer 18 Oct): "You were signed out because Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." With one change: "You were signed out because Wren's change is waiting on this phone. Sign in as Wren to send it." ("this computer" by layout.) Opened as usual, with another username typed in, or while that session hasn't been ended (next point), it shows the usual line. The warning and its buttons are unchanged.
- If the server answers that sign-out with an error (anything but `204` or `401`), the cookie still signs this browser in, so the sign-in page must not send it back into the app, which would only sign it out again, round and round. It stays, and says "Couldn't finish signing out on this phone." ("this computer" by layout) with **Try again**, which asks the server again. Still nothing is wiped. This is kept in memory only: a reload signs out again and lands on the sign-in page again, once. A sign-in that goes through clears it.
- **The phone database can't be read** (an IndexedDB error). That is never taken as "nothing waiting": whose changes are waiting isn't known, and nothing is wiped or written over `meta` on that result.
  - **The same login carries on** (cabledrawer 18 Oct: "The same login carries on: it never wipes anything, so nothing is at risk."). To know it's the same login without reading the database, the login the database was last written for is also kept in `localStorage` (`mealwright.login`: the login's number and username only, on this device only; the wipe removes it). The app opens as usual, still writing nothing over `meta`.
  - **A different login** is signed out again as above. The sign-in page says "This phone couldn't check for changes waiting to be sent. Nothing has been deleted." ("this computer" by layout). Pressing Sign in always gives an answer that is read out: the same line as an alert, with **Try again** (looks again: readable, it carries on as usual, with the usual warning if someone's changes are there) and **Carry on anyway, anything waiting on this phone may be lost** (cabledrawer 18 Oct). Carrying on anyway signs in and then wipes, as at sign-out (12), but only while the database still can't be read: readable by then, it shows the usual warning, with whose changes and how many, instead. A wrong password wipes nothing.
  - **If that wipe can't delete the database**, nobody is let in (12): the sign-in page says "This phone couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again." with **Try again** (cabledrawer 18 Oct).
  - Older installs, whose login isn't in `localStorage` yet, see the warning even as the same login, until the app has started once with the database readable.

### 11.6 App updates (L290)

- The app never calls `skipWaiting()` and never reloads itself while it's open, so a new version never takes over mid-shop. The browser switches to the new version once every window of the app has been closed, so the next cold start opens the new version.
- That means the old version can't send its queue first. Instead, **the new version sends the old version's queue before it shows the list.** On start it opens IndexedDB (its upgrade code keeps `queue` and `meta` exactly as they were) and, if the queue has entries, starts sending them as they are (protocol 1) before showing Shopping. Offline, the list shows from the copy with the queue on top, as always, and the queue goes when it can.
- This is safe because the server accepts protocol 1 for the life of `/api/v1` (4.1). FE-4 tests it.
- Docs: offline needs HTTPS (L461); iPhone Safari can clear offline data after 7 days without use, and adding to the Home Screen helps (L290).

### 11.7 How long offline (L277)

The copy and queue have no expiry on the phone. The app asks the browser for persistent storage (`navigator.storage.persist()`) once it is installed, where that doesn't show a prompt. The server applies queues of any age (L-22).

### 11.8 The device ID

`crypto.randomUUID()` the first time the app runs after a sign-in, kept in `meta` and on every queued action. It's kept when the same login signs back in after the session ran out or the server said `signed_out` (11.5): the copy, the queue and the device ID all stay, and the queue is then sent. A real sign-out wipes it, and the next sign-in makes a new one. It's random, not worked out from the device, and is sent only to our own server.

**A different login always starts clean** (cabledrawer 18 Oct: "A different login always starts clean: fresh copy, new device ID. Same as signing out."). When a sign-in succeeds for a login other than the one in `meta`, the app wipes exactly as at sign-out (section 12) before using the app, and the next start makes a new device ID. This holds whether or not anything was waiting. When changes are waiting, the warning in 11.5 still comes first, and nothing is wiped until the new login's sign-in has succeeded. The app never wipes over waiting changes without that warning: if a different login turns up without that warning having been shown, the waiting changes are kept and never sent under that login.

## 12. Signing out (spec L468, L93, new L302)

**The warning.** If the queue isn't empty when someone taps Sign out, the app first tries to send it (up to 5 seconds). If anything is still waiting:

> **3 changes haven't been sent yet. If you sign out now, they're lost.**
> Try sending now · Stay signed in · Sign out and lose them

- **Try sending now:** sends. If everything goes, it carries on signing out as asked. If not, the warning stays, with "Still can't reach your server."
- **Stay signed in:** closes the warning.
- **Sign out and lose them:** wipes and signs out.

This is the one justified "Are you sure?" (UX principle 6): unsent changes can't be undone. If everything is sent, Sign out just signs out.

**What's wiped**, on this browser only, before the server sign-out:

- The whole IndexedDB database `mealwright`: queue, offline copy, ingredient names, cursor, device ID, `meta`.
- Every Cache Storage cache except the app shell (code only; nothing about the household). From 0.4 this includes cached recipes and photos.
- `sessionStorage`, and every `localStorage` key except per-device display preferences that say nothing about the household (such as the sidebar being collapsed).
- The browser's own HTTP cache never holds household data in the first place: every `/api` response, `/api/v1/events` included, is sent with `Cache-Control: no-store` (PR 2 adds it for all of `/api` if 0.2 doesn't already, with a test).

**Only what the warning showed.** The warning remembers the action IDs of the changes it showed. "Sign out and lose them" reads the queue again just before the wipe; if any change is waiting that it didn't show (another tab queued it), nothing is wiped and the warning comes back with the new count, read out again.

**Adding to the queue and wiping take turns** in every tab, through the browser's Web Locks (`navigator.locks`, no dependency): the read just before a wipe and the wipe itself hold one lock, and so does every add to the queue. A change another tab adds meanwhile lands either before the read (so it is seen, and warned about) or after the wipe, in the new empty database, never in between, unseen and lost. Where the browser has no Web Locks, it works as before, without the lock. That is Safari before 15.4, and any browser on plain `http://` (Web Locks need a secure context; plain HTTP is allowed for testing): the read just before the wipe is the only guard, and the gap between that read and the delete is a few milliseconds.

If the phone database can't be read, whether changes are waiting isn't known, so Sign out doesn't go ahead on its own (it is never counted as none): Settings says "This phone couldn't check for changes waiting to be sent. Nothing has been deleted." with **Try again**, **Stay signed in** and **Sign out anyway — anything waiting on this phone may be lost** (cabledrawer 18 Oct: "Being unable to sign out of a shared or lost phone is worse than possibly losing unsent changes, and it's an explicit choice, never silent."). Sign out anyway wipes as usual. If the database can be read by the time it's pressed and a change is waiting, the usual warning shows instead.

**If the phone database can't be deleted** (on either "anyway" path, or any wipe), nobody may see or reuse the old login's data. A "wipe pending" flag in `localStorage` (`mealwright.wipe-pending`, kept on wipe) is set to "1" before anything is deleted, becomes "failed" if the delete fails, and is cleared only once the database is gone. Deleting it counts as failed after 10 seconds (another tab that never lets go of it). Only "failed" is a failure: a tab sent to sign in while another tab's wipe is still deleting ("1") says nothing about it, and shows the failure only if that wipe then fails (it hears the change through the `storage` event). A "1" left by a tab closed mid-wipe also says nothing, but nobody is let in without the wipe being finished: signing in finishes it before letting anyone in. While the flag is set, the database is never opened, nobody is "last signed in" (so the app doesn't open offline), nothing is shown as waiting, and nobody can sign in: everything else is wiped as usual and the server session is still ended, and the sign-in page says "This phone couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again." ("this computer" by layout; cabledrawer's wording, cabledrawer 18 Oct) with a **Try again** button. Try again, Sign in, and the app starting signed in all try the wipe again first; still failing, the session is ended again and the line is read out again.

Then `DELETE /api/v1/session` (0.1) ends the session on the server. **If the server answers with an error** (anything but `204` or `401`; `502`, `503` and `504` from the reverse proxy count as offline), the flag below stays, and the sign-in page says "Couldn't finish signing out on this phone." with **Try again** (11.5).

The app turning a login away over someone's waiting changes (11.5) is stricter: there, `502`, `503` and `504` count as "couldn't finish", not as offline. Nothing has been wiped in that case, so there is no "sign-out pending" flag to end the session later (and setting one would hide Wren's waiting changes from the sign-in page). Counted as offline, the sign-in page would send the still-valid cookie straight back into the app, to be turned away again, round and round. So it stays on the sign-in page and offers Try again. **Offline:** the wipe happens at once, the sign-in page shows, and a "sign-out pending" flag (kept outside the wiped database) makes the app end the server session first thing when it's back, before anything else can use the old cookie.

**Other tabs** (cabledrawer 18 Oct: "Other tabs clear themselves and go to the sign-in page as soon as you sign out in any tab, with a test."). The tab that wipes tells the others first, on a `BroadcastChannel`, with a `localStorage` `storage` event as the fallback; deleting the database also reaches every tab that has it open (IndexedDB `versionchange`). All of this stays inside the browser. Every other tab then drops what it shows, stops the live stream and sending, never opens (and so never re-creates) the database until someone signs in, and goes to the sign-in page. The same happens when a different login starts clean (11.8).

**A shared phone:** each person signs in with their own login; signing out wipes the first person's copy (after the warning), so the next person starts clean. A tablet shared under one household login ("Family") isn't signed out between people; everyone's changes go under that login (the "Who's this?" picker is 0.8). A session that runs out is not a sign-out: nothing is wiped (11.5).

## 13. Screen details that touch the protocol (PR 4)

- **Order:** shops in their `position` order, each with its aisles in the shop's `aisle_order` (or the default order, L288), items by name within an aisle, ingredients with no aisle under Other. Then **Any shop** last (new L298).
- **In the trolley · N:** at the end of each shop, ticked items fold into one row that opens to show them, each with "Different pack?" and the place; **Clear ticked** there sends `clear_ticked` with the items shown (new L297).
- **Aisle headings** use the spec's names (new L288), not the mockups' older "Fruit & veg" and "Rice & grains".
- **Subtitle** of the main list (new L301): "12 to buy · synced with Wren". Three people: "synced with Wren and Arlo"; four or more: "synced with Wren and 2 others". Only logins count; profile-only members don't. One login in the household: "12 to buy · saved". Extra lists keep the mockup's line ("Extra list · 6 · ticked items still go to the pantry").
- **Put away:** phone toast "Coriander → Fridge · Change · Undo"; desktop "Put away" panel ("Ticked items go straight into the pantry.", Where: Fridge · Freezer · Cupboard, "Undo last tick"), from the mockups.
- **Different pack?** sheet: "What did you buy?" with 2 × 200 g · 1 × 400 g · 1 × 1 kg · Other… and "Pantry gets 1 pack · 400 g.", Done.
- **Lists:** the list picker (This week · extra lists · + New list), with Rename and Remove (extra lists only) in each list's menu; Remove has Undo.
- **New ingredient** (new L299; spec L312): typing a name that isn't an ingredient offers "+ New ingredient: "tahini"", then "How do you count it?" (cabledrawer 18 Oct, decision 2), then adds the item.
- Every on-screen sentence says "ingredient", never "food" (api-0.2 section 1.1; `test_wording.py`).

## 14. Two-device tests

**Setup S0** (built by a test helper, used by every case unless it says otherwise): one household; logins **Tess** (device A) and **Wren** (device B); shops Supermarket and Indian grocer; places Fridge, Freezer, Cupboard, Spice rack. Ingredients: Toor dal (weight, packet 500 g usual, lives in Cupboard, shop Supermarket), Paneer (weight, pack 200 g usual, Fridge, Supermarket), Milk (volume, no size, Fridge, Supermarket), Coriander (count, count word bunch, Fridge, Supermarket), Onions (count, no usual place, Supermarket), Salt (staple, Supermarket), Eggs (count, size box of 6 usual, Fridge, Supermarket; not on the list, none in the pantry). Main list "This week": toor dal 1 packet, paneer 2 × 200 g, milk 2 L, coriander 1 bunch, onions 5, salt. None ticked; none of them in the pantry. Both devices synced at cursor C0.

"Offline" means the device queues its actions; "reconnect" means it sends its whole queue as one batch (unless the case says otherwise). "A→B" = A's batch reaches the server first. Every case with an order is run **in both orders** where it says "both", and asserts list, pantry (lots, places, amounts), change log, notes and cards for **both** logins.

Runs as: **BE** = fast backend test (pytest, `backend/tests/test_sync_*.py`, test names start with the ID, e.g. `test_sy01_same_item_ticked_on_both`); **E2E** = browser end-to-end (Playwright); **FE** = frontend unit test (Vitest).

| ID | Start | A does | B does | Reconnect | Expected list | Expected pantry | Notes / card | Runs as |
|---|---|---|---|---|---|---|---|---|
| SY-01 | S0 | offline: tick toor dal | offline: tick toor dal | both orders | toor dal ticked, two ticks (Tess, Wren) | Toor dal 2 packets (2 lots) in Cupboard; two `shopped` changes, one by each | Card "Did you buy 2?" for both: Tess's says "You and Wren both ticked…", Wren's "You and Tess…". No notes. | BE |
| SY-02 | S0, but B is a second phone signed in as Tess | offline: tick toor dal | offline: tick toor dal | both orders | ticked, two ticks | 2 packets | Card for Tess: "This was ticked on two phones, so 2 packets went into the pantry." | BE |
| SY-03 | S0 | offline: tick toor dal twice (two action IDs, no untick) | — | A | ticked once | 1 packet | Second → `ignored already_ticked`. No card. | BE |
| SY-04 | S0 + coriander ticked by A (tick t0), synced | offline: untick (t0), then tick again (t1) | offline: untick (t0) | both orders | coriander ticked (t1, Tess) | Coriander 1 bunch (not 0, not 2) | B's untick → `ignored not_ticked` (A→B) or applied before A's (B→A); same end either way. No notes. | BE |
| SY-05 | S0 + coriander ticked t0, synced | offline: untick (t0) | offline: untick (t0) | both orders | coriander unticked | Coriander 0 (taken back once, never negative); one `undo` change | Second untick → `ignored not_ticked`. | BE |
| SY-06 | S0 | offline: delete milk | offline: set milk 4 L | A→B | milk gone | no change | Wren: N4 "Tess had removed milk, so your change wasn't kept." Undo → milk back at 2 L. | BE |
| SY-07 | S0 | offline: delete milk | offline: set milk 4 L | B→A | milk gone | no change | Wren: N4, same text. Undo → milk back at 4 L. | BE |
| SY-08 | S0 | offline: tick paneer | offline: delete paneer | A→B | paneer off the list | Paneer 2 packs · 400 g in Fridge | cabledrawer: N1 "Wren had removed this. Your tick still went into the pantry." Undo → paneer back out of the pantry (0). | BE |
| SY-09 | S0 | offline: tick paneer | offline: delete paneer | B→A | paneer off | 2 packs · 400 g in Fridge | cabledrawer: N1, same. | BE |
| SY-10 | S0 | offline: add Eggs 6 (Supermarket) | offline: add Eggs 12 (Supermarket) | both orders | one Eggs line, 12 | no change | Both get N2 ("Wren added Eggs too" / "Tess added Eggs too"). The later add is `merged`. Undo of N2 → A→B: line back to 6; B→A: stays 12; either way one line. | BE |
| SY-11 | S0 + extra list "Party" | offline: add Eggs 6 to This week | offline: add Eggs 6 to Party; and add Eggs to This week with shop Any shop | both orders | three Eggs lines (This week/Supermarket, Party, This week/Any shop) | no change | No notes. | BE |
| SY-12 | S0 | offline: set milk 3 L | offline: set milk 4 L | both orders | A→B: milk 4 L; B→A: 3 L; `hand_edited` on | no change | The overwritten person gets N3 ("Wren changed milk to 4 L" / "Tess changed milk to 3 L"); Undo puts their amount back. | BE |
| SY-13 | S0 + coriander ticked t0 (into Fridge), synced | offline: put away → Cupboard | offline: put away → Freezer | both orders | ticked; place = last received | Coriander 1 bunch in the last received place; two `moved` changes | The overwritten person gets N6; Undo moves it back to their choice. (Decided 3.) | BE |
| SY-14 | S0 | offline: tick coriander, then put away → Freezer | — | A | coriander ticked, place Freezer | Coriander 1 bunch in Freezer, no use-by; changes "Bought 1 bunch Coriander → Fridge", "Moved Coriander → Freezer" | — | BE |
| SY-15 | S0 | offline: tick paneer, then Different pack → 1 × 400 g | — | A | paneer ticked; planned 2 × 200 g, bought 1 × 400 g | Paneer one lot 400 g in Fridge; Paneer gets size "pack 400 g", `added_when_shopping` | — | BE |
| SY-16 | S0 | online: tick paneer (2 × 200 g) | online: Pantry, used 100 g Paneer | — then A: Different pack → 1 × 1 kg | paneer ticked, bought 1 × 1 kg | Paneer 900 g | — | BE |
| SY-17 | S0 | offline: tick toor dal, tick paneer, set milk 3 L, add Eggs 6, delete onions | — | A sends; the answer is lost; A sends the identical batch again | as after the first send | as after the first send (toor dal 1 packet, paneer 400 g) | Second answer: every result `repeat: true`, same `seq`s; counter unchanged. | BE |
| SY-18 | as SY-17 | the first 3 actions sent as one batch, answer lost; then all 5 sent as one batch | — | A | all 5 applied once | toor dal 1 packet, paneer 400 g | Results 1–3 `repeat: true`, 4–5 applied. | BE |
| SY-19 | S0 | online: tick toor dal; the answer is lost; sent again | — | A | ticked once | 1 packet | `repeat: true`. | BE |
| SY-20 | S0 | sends action X (tick toor dal); then another action with X's ID but `delete milk`; then a 0.2 `POST /stock` with `Idempotency-Key` Y and a sync action with ID Y | — | A | toor dal ticked; milk still there | 1 packet + the 0.2 add | Second X → `refused key_reused`; Y action → `refused key_reused`; a 0.2 `POST /stock` whose `Idempotency-Key` is X → `409 key_reused` (5.7). | BE |
| SY-21 | S0 | Saturday, online: tick toor dal; delete milk; clear ticked | Friday (`made_at` 3 days earlier), offline: tick toor dal; add Eggs 6; set milk 3 L | A, then B on Monday | toor dal off (cleared); Eggs 6 on; milk gone | Toor dal 2 packets | Card "Did you buy 2?" for both (no N1, the card explains it); Wren: N4 for milk. | BE |
| SY-22 | S0 | online, 2 weeks ago: delete coriander | 3 weeks ago, offline: tick paneer, Undo it 10 s later; tick coriander | B now | paneer unticked; coriander off | Paneer 0 (bought then taken back: the queued Undo still counts); Coriander 1 bunch | Wren: N1 for coriander. | BE |
| SY-22b | S0 | — | online: tick toor dal; 2 days later, offline: Undo it; reconnect 10 days after the tick | B | toor dal unticked | 0 | The Undo counts (pressed within 7 days). The same Undo pressed on day 9 → `ignored too_old`, toast. | BE |
| SY-23 | after SY-01 (A→B) | online: Just 1 | — | — | toor dal ticked by Tess only | 1 packet (Wren's purchase taken back) | Card gone for both; toast "Took back 1 packet Toor dal". A's Undo → 2 packets, card back for both. | BE |
| SY-24 | after SY-01 (A→B), then Wren uses 800 g in Pantry (Tess's lot empty, Wren's lot 200 g) | online: Just 1 | — | — | ticked by Tess | 0 | "Took back 200 g of the 500 g: the rest has been used since." | BE |
| SY-25 | after SY-01 (A→B) | offline: Yes, 2 | offline: Just 1 | both orders | ticked | A→B: 2 packets; B→A: 1 packet | First answer settles it; the other → `ignored answered`. Card gone for both. | BE |
| SY-26 | S0 | online: tick toor dal (500 g) | online: Pantry, used 200 g Toor dal | — then A: untick | toor dal back on the list, unticked | 0 (took back 300 g) | "Took back 300 g of the 500 g: the rest has been used since." | BE |
| SY-27 | after SY-01 (A→B, both synced) | — | online: untick naming both ticks | — | unticked | 0 | Card closed (`none`) for both. Variant: A, not yet synced, unticks naming only its own tick → only Tess's purchase out, item stays ticked by Wren, 1 packet, card closed. | BE |
| SY-28 | S0 | offline: tick salt | offline: tick salt | both orders | salt ticked | nothing; no `shopped` change | No card. | BE |
| SY-29 | S0 + toor dal ticked by A, synced | online: Clear ticked [toor dal] | offline: tick onions | A, then B | toor dal off; onions ticked (in the trolley) | Toor dal 1 packet; Onions 5 | — | BE |
| SY-30 | S0, B offline from the start | online: tick toor dal; Clear ticked [toor dal] | offline: tick toor dal | B | toor dal off | Toor dal 2 packets | Card for both; no N1. | BE |
| SY-31 | S0 + toor dal and paneer ticked, synced | online: Clear ticked [toor dal, paneer]; then Undo | — | — | both back, ticked | unchanged throughout (1 packet, 400 g) | — | BE |
| SY-32 | S0 + extra list "Party on Saturday": crisps 2 bags, lemonade 2 bottles; synced | online: remove Party | offline: tick crisps; add Candles (new ingredient, staple); set lemonade 3 bottles | A, then B | Party hidden | Crisps 2 bags | Wren: N7 "Tess had removed Party on Saturday. Your changes are kept with it. Your ticks still went into the pantry." Undo → Party back with crisps ticked, Candles, lemonade 3. | BE |
| SY-33 | S0 | `remove_list` on This week; then `rename_list` to "Our week" | — | A | renamed, still there | — | Remove → `refused main_list`. | BE |
| SY-34 | S0 | — | offline: 3 actions; meanwhile B's session runs out | B sends → 401; signs in again as Wren; sends | all 3 applied | as the actions say | Nothing applied before the new sign-in. | BE |
| SY-35 | S0 | — | Wren's 3 queued actions sent under Tess's session | B | unchanged | unchanged | `409 other_login`, nothing applied. | BE + FE-3 |
| SY-36 | S0 | online: tick toor dal | online: Pantry → Recent changes → Undo "Bought 1 packet Toor dal → Cupboard" | — | toor dal unticked; A sees it via changes and an event | 0 | — | BE |
| SY-37 | S0 | online: tick toor dal; Undo from the toast | — | — | unticked | 0 | — | BE |
| SY-38 | S0 + toor dal ticked by A, synced | online: Clear ticked [toor dal] | offline: untick toor dal | A, then B | toor dal stays off | 0 | Wren: N5. Undo → 1 packet again. | BE |
| SY-39 | S0 | offline: add "Tahini", new ingredient (weight), blank | offline: add "tahini", new ingredient (count), blank | both orders | one ingredient (the first one's name and counting); one line | — | N2 for both. | BE |
| SY-40 | S0 | add Toor dal blank; add Onions blank; add a new weight ingredient with no size, blank | — | — | toor dal 1 packet (`size_id` packet); onions 1; the new one with no amount | ticking the new one adds nothing (cabledrawer 18 Oct, decision 1) | — | BE |
| SY-41 | S0 + a second household | actions naming the other household's list, item, ingredient, place, shop, size, note, question; an `add` reusing one of its item IDs | — | A | unchanged | unchanged | Each handled as "not in this household" (5.9): `ignored gone`, or the fallback place, shop or size; the reused item ID → `refused id_taken`. Nothing in the other household changes; changes and events show nothing of it. | BE |
| SY-42 | S0, 20 actions applied | — | device at cursor N | — | `changes?since=N` returns exactly the rows with `version > N` (tombstones included); `since=0` and `since` below `list_purged_seq` → `reset: true` with no tombstones | — | — | BE |
| SY-43 | S0 | two batches sent at the same moment (threads), with repeats and refusals mixed in | | | numbers strictly increasing, no gaps; repeats and refusals take no number; a reader polling meanwhile never skips a number | — | — | BE |
| SY-44 | S0 | `add` | `set_amount` on it | | `source` typed; `hand_edited` on after set_amount | — | — | BE |
| SY-45 | S0 | offline: delete milk | offline: delete milk | both orders | milk gone | — | Second → `ignored deleted`; its Undo → `ignored nothing_to_undo`; the first's Undo brings milk back. | BE |
| SY-46 | S0 | tick onions (no usual place); tick toor dal (Cupboard); put away coriander → Freezer, then tick it | — | | all ticked | Onions 5 in Cupboard; Toor dal 1 lot in Cupboard; Coriander in Freezer; no use-by on any | — | BE |
| SY-47 | after SY-10 (A→B) | — | ticks Eggs using her own (merged) item ID | B | the kept line is ticked | Eggs 12 | — | BE |
| SY-24u | after SY-24 | online: Undo of the Just 1 | — | — | ticked by both again | 200 g (Wren's lot back to exactly what was taken out, not 500 g) | Card back for both. | BE |
| SY-26u | after SY-26 | online: Undo of the untick | — | — | toor dal ticked again | 300 g (not 500 g); one new `shopped` change "Ticked again: 300 g Toor dal → Cupboard" | — | BE |
| SY-48 | S0 | sends [tick toor dal, tick paneer, add Eggs 6]; a test hook holds the server's work open past 15 s; A's client gives up and sends the identical batch on a second thread while the first is still running | — | A | as after one send | toor dal 1 packet, paneer 400 g (once) | The second answer: all `repeat: true`, same `seq`s; counter C0 + 3, no gaps. | BE |
| SY-49 | S0 | online: tick paneer; Different pack → 1 × 1 kg; Pantry → Recent changes → Undo the `repacked` change | — | — | paneer still ticked, bought 2 × 200 g again | Paneer 400 g (two 200 g lots) in Fridge | — | BE |
| SY-50 | S0 | online: tick paneer; Different pack → 1 × 1 kg; Pantry → Undo the original "Bought 2 packs Paneer → Fridge" | — | — | paneer unticked | Paneer 0 (not 900 g, not 1 kg) | — | BE |
| SY-51 | S0 | online: tick coriander (Fridge); put away → Freezer; Pantry → Undo "Moved Coriander → Freezer" | — | — | coriander ticked; tick place Fridge; no chosen place; B sees it through changes | Coriander 1 bunch in Fridge | — | BE |
| SY-52 | S0 + an ingredient "Arhar dal" (weight, no shop) | online: merge Arhar dal into Toor dal | offline (before the merge): add Arhar dal 2 packets | A, then B | one Toor dal line, 3 packets (1 + 2: Wren could see the toor dal line, so the amounts add up, cabledrawer 18 Oct, decision 8), Supermarket | — | `merged` into the toor dal line; no note. | BE |
| SY-53 | S0 | online: remove Eggs from Ingredients | offline (before): add Eggs 6 | A, then B (within 7 days) | Eggs 6 on the list | — | Eggs back in Ingredients (`brought_back`); toast "Eggs is back in Ingredients." | BE |
| SY-54 | S0 | online: remove Eggs; 8 days later it's deleted for good | offline (before): add Eggs 6 | B on day 9 | no Eggs line | — | `ignored gone`, toast "Eggs was removed from Ingredients, so it wasn't added." | BE |
| SY-55 | S0 | online: remove the place Spice rack | offline (before): put away coriander → Spice rack; tick coriander | A, then B | coriander ticked; no chosen place | Coriander 1 bunch in Fridge (its usual place) | — | BE |
| SY-56 | S0 | online: remove Paneer's 200 g pack size | offline (before): set paneer to 3 × 200 g | A, then B | paneer 600 g, no size, shown in grams | — | — | BE |
| SY-57 | S0 | online: remove the shop Indian grocer | offline (before): add Eggs 6 with shop Indian grocer | A, then B | Eggs 6 under Supermarket (its usual shop) | — | — | BE |
| SY-58 | after SY-01 (A→B) and an N1 note for Wren | — | offline 8 days: dismiss the note; answer the card; untick an item tidied away for good (test sets its purge) | B | unchanged | unchanged | All three `ignored gone` (or `answered` if the card is closed but kept), no toast for the note. | BE |
| SY-59 | after SY-01 (A→B), both synced | online: Just 1; remove Eggs, deleted for good on day 8 | offline 10 days, then: Yes, 2 | B on day 10 | toor dal ticked by Tess | 1 packet | B's answer `ignored gone`. B's next changes: no questions (the card goes), `reset: true` (the ingredient purge raised `list_purged_seq`), no Eggs in the copy. | BE |
| SY-60 | S0 | a batch with an unknown kind, and a `tick` carrying an `amount` | — | A | unchanged | unchanged | Both `refused bad_action`. | BE |
| SY-61 | | | | | `/api/v1/openapi.json` lists `POST /shopping/actions`, `GET /shopping/changes`, `GET /events`, a schema for every action kind and result; each one-at-a-time list request (5.1) writes a `sync_action` row and takes a counter number | | | BE |
| SY-62 | S0 | — | online: tick toor dal; the session runs out; offline: tick toor dal again (no untick); signs back in as Wren | B | ticked once | 1 packet | Second tick `ignored already_ticked` (same device ID kept); no card. | BE + FE |
| SY-63 | S0, B's clock 30 days slow | — | online: tick toor dal; offline: Undo on day 2, sent on day 3; and another tick Undone on day 9 | B | first unticked; second still ticked | first 0; second still in | Day-2 Undo counts; day-9 → `ignored too_old`. Same with the clock 30 days fast. | BE |
| SY-64 | S0 | online, synced (sees milk 2 L): add Milk 1 L | — | — | one milk line, 3 L | — | No note (cabledrawer 18 Oct, decision 8). | BE |
| SY-65 | S0 | offline: add Eggs 6, then add Eggs 6 again (two actions, same phone) | — | A | one Eggs line, 12 (base amounts added, the line's size kept: 2 boxes) | — | Second `merged`; no note. A's screen showed 12 before sending (`applyLocal`). Variant: toor dal 1 packet + toor dal 250 g → 750 g, shown "1½ packets". | BE + FE |
| SY-66 | S0 + a removed ingredient "Ghee" (in its undo window) | online: make a new ingredient named "Ghee" | offline (before): add Ghee 1 jar via the removed one | A, then B | one Ghee line, on the new Ghee | — | The old Ghee stays removed. Variant without the new one: old Ghee brought back; Wren's Undo of the add removes it again. | BE |
| P-1 | S0 | random queues for two devices (Hypothesis): any mix of the actions above, random reconnect order, batch splits, lost answers and resends. (PR 3) Three phones, Tess on two (the same login on two devices) and Wren on one, with uses from the pantry in between the syncs. | | | | | After everything: each ingredient's stock = its standing purchases' stock minus uses, never below zero; resending any prefix changes nothing; every action has exactly one `sync_action` row; a tombstoned item is back only through an Undo. (PR 3) Checked after every sync and every use, per purchase: no lot below zero; every lot with stock belongs to exactly one purchase; a purchase taken back has nothing left in its lots, one still standing has at most what it bought (exactly that if nothing was used from its lots); a take-back only takes from its own purchase's lots, never more than is left in them; a put-back (Undo of an untick or of "Just 1") gives back exactly what its take-back took out, lot by lot. | BE |
| E1 | S0, two browser contexts (Tess, Wren) | offline (Playwright `setOffline`): tick toor dal | offline: tick toor dal | A, then B | ticked | Pantry screen: Toor dal 2 packets | "Did you buy 2?" on both screens; Wren taps Just 1 → the card disappears from Tess's screen within 5 s (event stream); Pantry 1 packet. **Stays for 0.8** (cabledrawer 18 Oct): Wren's login is made in the app, as a real second login, with nothing seeded. E1s below is the 0.3 version. | E2E (0.8) |
| E1s | Two browser contexts, both signed in as Tess (two devices). Nothing seeded: Toor dal (weight, packet 500 g) made through the API, 1 packet on the main list | offline: tick toor dal | offline: tick toor dal | A, then B | ticked | 2 packets, then 1 packet (checked through `GET /api/v1/pantry`) | "Did you buy 2?" on both screens, with "This was ticked on two phones, so 2 packets went into the pantry." (the same login on both, so no names); Just 1 on B → the card disappears from A's screen within 5 s (event stream). The 0.3 version of E1 (cabledrawer 18 Oct). Phone and desktop. | E2E |
| E2 | S0, one context | offline: tick 2 items, add 1 | — | reload the page while offline, then go online | the 3 changes survive the reload; then on the server | — | Bar "Offline — 3 changes waiting"; after reconnect, toast "Back online — all saved". | E2E |
| E3 | S0, one context | offline: tick 1 item; Sign out | — | — | — | — | The warning with Try sending now · Stay signed in · Sign out and lose them. Stay signed in keeps the change. Sign out and lose them → IndexedDB database gone, sign-in page; going online ends the server session. | E2E |
| FE-1 | | | | | Grouping: shops in order, aisles in the spec's order and names, no aisle → Other, Any shop last, trolley row per shop | | | FE |
| FE-2 | | | | | Subtitle for 1, 2, 3 and 4 logins; offline wording | | | FE |
| FE-3 | | | | | A different login signs in on a phone holding Wren's queue → the warning, never a send; carrying on wipes the whole offline copy and the device ID | | | FE |
| FE-4 | | | | | A newer app version opens an IndexedDB database written by the older one: `queue` and `meta` kept exactly; it sends the queue as protocol 1 before showing Shopping; nothing calls `skipWaiting()` | | | FE |
| FE-5 | | | | | `applyLocal` never produces pantry data, and the offline copy has no pantry store | | | FE |
| FE-6 | | | | | `package.json` pins `idb` to an exact version (no `^` or `~`) | | | FE |
| FE-8 | | | | | **PR 6c.** The phone database can't be read (IndexedDB fails): never "nothing waiting"; nothing wiped, `meta` not written; the app turns a different login away, the sign-in page says it couldn't check and sends nothing; Settings won't sign out without "Sign out anyway" | | | FE |
| FE-9 | | | | | **PR 6c.** Two tabs: the warning showed Wren's change; another tab sends it and queues a new one; carrying on warns again with the new one and wipes nothing | | | FE |
| FE-10 | | | | | **PR 6c.** `DELETE /session` fails while `GET /me` works: one trip to the sign-in page, which stays and says "Couldn't finish signing out on this phone." once, with Try again; nothing wiped. The "You were signed out because…" line: many changes, one, "this computer", and not on a page opened as usual | | | FE |
| FE-11 | | | | | **PR 6c round 1.** Settings: the warning showed 1 change, another tab queues 3; "Sign out and lose it" warns again with 4, wipes nothing; losing those 4 then signs out. An add waiting on the queue lock lands after the wipe, never lost; without Web Locks the wipe works as before | | | FE |
| FE-12 | | | | | **PR 6c round 1.** Unreadable phone database: the same login (`mealwright.login`) carries on, nothing wiped or written; a different login's Sign in gets the alert with Try again and Carry on anyway, which signs in and wipes (readable by then: the usual warning). Settings: Sign out anyway wipes as usual | | | FE |
| FE-13 | | | | | **PR 6c round 1.** The phone database can't be deleted: the session still ends, the database is never opened again, nobody is last signed in or waiting, nobody can sign in; the sign-in page says so with Try again; the next wipe finishes it | | | FE |

## 15. The manual two-phone test (for the 0.3 release)

For cabledrawer, with two phones. About 20 minutes, plus a night. Your server is only reachable on home Wi-Fi, so do the "shop" part anywhere, but **reconnect at home**.

**Both phones sign in as Tess** (cabledrawer 18 Oct): "I can't make a Wren login until 0.8, so for 0.3.0 both phones sign in as Tess." The two-person version of this test (one phone as Tess, one as Wren) comes back in 0.8. Because both ticks are by the same person, the cards and notes say "phones" or "Your other phone" where they would otherwise name Wren.

**Before you start**

1. On both phones, open Mealwright in the browser, sign in as **Tess** on each, and add it to the Home Screen. Open it from the Home Screen icon from now on. Call them phone A and phone B.
2. On one phone, make a list for a single shop (say Supermarket) with: Toor dal 1 packet, Coriander 1 bunch, Milk 2 L, Onions 5.
3. Tick **Coriander** on phone A now, while online. Wait until both phones show it ticked.
4. Open **Pantry** and write down how much Toor dal and Coriander you have.

**In the "shop" (both phones offline)**

5. On both phones, turn on **aeroplane mode** and make sure Wi-Fi is off too. Each phone should show "Offline".
6. **Same item on both:** tick **Toor dal** on phone A and on phone B.
7. **A tick against an untick:** on phone B, untick **Coriander**. On phone A, untick **Coriander** and then tick it again.
8. **A delete against an edit:** on phone A, delete **Milk**. On phone B, change Milk to 4 L.
9. Each phone should now say "Offline — N changes waiting" (A: 4, B: 3).
10. You can close the app, or restart the phones: the changes stay.

**Back home**

11. Phone A: turn aeroplane mode off and join home Wi-Fi. Open the app. You should see "Back online — all saved".
12. **Leave phone B offline until tomorrow.** Then turn its aeroplane mode off at home and open the app. "Back online — all saved".

**What you should see on both phones**

- Toor dal ticked once on the list, and a card **"Did you buy 2?"** above the list. Because both ticks were yours, the card doesn't name anyone. It says: "This was ticked on two phones, so 2 packets went into the pantry.", with the buttons **Yes, 2** and **Just 1** (cabledrawer 18 Oct). In Pantry: 2 packets more than you wrote down in step 4.
- Tap **Just 1** on one phone. The card disappears from the other phone within a few seconds. Pantry: 1 packet more than you wrote down in step 4.
- **Coriander** ticked, and in Pantry the same as you wrote down in step 4 (not 1 bunch less, not 1 more).
- **Milk** gone from the list. Phone B shows a quiet note "Your other phone had removed Milk, so your change wasn't kept." with Undo. Nothing changed in the pantry for milk.
- Pantry → Recent changes lists the ticks, each one by cabledrawer.

**Bonus (one minute):** on phone B, go offline, tick something, then Settings → Sign out. You should get "1 change hasn't been sent yet. If you sign out now, it's lost." with Try sending now · Stay signed in · Sign out and lose it. Tap **Stay signed in**, go back online, and the change saves.

If anything looks different, take a screenshot, note the step number, and send it to the lead as a bug note. The friction log is for things that are annoying or slow.

## 16. Decided (cabledrawer 18 Oct)

The points the spec and the 17 Oct answers didn't settle. cabledrawer accepted every recommendation on 18 Oct; all are now in the spec, and nothing is open.

1. **An item with no amount** (weighed or measured, no usual size; new L299 covers only "usual size" and "counted in items"): the item shows with no amount; ticking it puts nothing into the pantry, and the ticked row offers "How much? (to the pantry)" (the Different pack? sheet) for one more tap. No prompt. (new L303; SY-40)
2. **"How do you count it?"** (not in 0.2, which guesses weight from the name unless the bundled table knows better): PR 4 adds the question when a typed name is brand new: By weight · By volume · One by one · Don't count it (staple, for kitchen roll and soap), with the bundled table's guess picked first when connected to your Mealwright server. (new L304; L-14, SY-39)
3. **Put away on two phones with different places:** like answer 5, the one the server receives last wins, with a quiet note "Wren put coriander in the Freezer" (N6) and Undo. (new L305; L-32, SY-13)
4. **A different login on a phone holding someone else's changes:** the sign-in page says "Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." If someone else signs in anyway: "Wren's 3 changes haven't been sent yet. If you carry on, they're lost." → Sign in as Wren instead · Carry on and lose them. Carrying on wipes the whole offline copy and the device ID (11.5). (new L306; FE-3)
5. **Starting aisles:** PR 2 changes `backend/scripts/build_conversions.py` to read each ingredient's USDA food category from the same download and write an `aisle` column to `backend/src/mealwright/data/food-conversions.csv`, using a fixed category → aisle list in the script, where every category maps to one of the spec's default aisle names (L288: "Spices and Herbs" → Spices, "Dairy and Egg Products" → Dairy, and so on), with a per-ingredient override in its choices list where a category doesn't fit (dried beans vs fresh). Nothing is typed in by hand. Ingredients not in the table start as Other. The aisle stays editable in the ingredient editor. Rebuilding needs the USDA download (`docs/dev/conversions.md` says where to get it). (new L307; FE-1)
6. **A removed list is hidden, not frozen:** queued ticks and edits for it still apply inside the hidden list, ticks still go into the pantry, and the person whose queue hit it gets N7 with Undo, which brings the list back. (new L308; L-7, SY-32)
7. **Changing an ingredient's usual shop moves it on the lists:** unticked items under its old usual shop (or Any shop) move to the new one; items put under a particular shop on purpose stay. (new L309; 3.2)
8. **Adding something already on the list:** "keep the bigger amount" is only for a real clash (the person couldn't yet see the other line). Online, the add box says "Milk is already on the list · 2 L" and changes that line instead; an add for a line the person could see, or one made on the same phone, adds the amounts up (2 L + 1 L = 3 L), with no note. (new L310; L-12, SY-64, SY-65)
9. **"Same list, same shop, neither ticked"** in the "Both add the same ingredient" line: confirmed, so the wording stays and the line is cabledrawer's. (new L294; L-12)
10. **A note or card for an item that's no longer on the list** shows in a faint row where the item was, in its shop: "Paneer · removed by Wren", until the note is dismissed or the card answered. Nothing else about the item shows. (new L311; section 8)
11. **A tick arriving after the card was answered** opens a fresh card covering every purchase still standing ("Did you buy 3?" after Yes, 2; "Did you buy 2?" again after Just 1). (new L312; L-3, 3.6)
