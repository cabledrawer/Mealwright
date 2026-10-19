# API and data for 0.4 (recipes): the data and the API

Written 19 Oct 2026 for the first 0.4 pull request ("Recipes: the data, the API and the loop guard"). The conventions, error shape, `Idempotency-Key` and Undo are the same as in `api-0.2.md`; read its section 1 first. The spec (`docs/spec.md`, section 6 "Recipes") wins wherever this file disagrees with it. The generated OpenAPI (`/api/v1/openapi.json`) is the exact reference.

Recipes are online only in 0.4. Nothing here touches the shopping-list sync or the offline queue.

## 1. Tables (one migration, `c5e8a1f3b7d2`)

Every table has `household_id`.

| Table | Holds |
|---|---|
| `recipe` | name, description, `time_minutes`, `serves` (1 to 99 or empty), `makes_milli` + `makes_unit`, `made_ahead`, `homemade_food_id` (the recipe's own pantry ingredient), five nutrition columns (`*_milli`, empty = unknown), `source_note`, `version`, who and when it was last saved, `removed_at` (a deleted recipe, for the undo window) |
| `recipe_line` | an ingredient line or a heading: position, `words` (as typed), `amount_milli` and `unit` (in the unit typed, not a base unit), `size_id`, `food_id` or `sub_recipe_id` (never both), `note` |
| `recipe_step` | a step or a heading: position, `text` |
| `tag`, `recipe_tag` | tags the household typed, and which recipe has which |
| `recipe_photo` | the photo's record only (`file_key`, size, who added it). Files and uploads come with the photos pull request. |

Amounts are thousandths of the unit the person typed (`2 tbsp` is `2000`). Nutrition is thousandths too; `NULL` is "unknown" and `0` is a real zero.

## 2. Endpoints

All under `/api/v1`, signed in, same-origin for writes. An id from another household is a 404.

| | |
|---|---|
| `GET /recipes?limit=&after=` | every recipe, A to Z. `{total, recipes: [brief], next}`. A deleted recipe isn't listed. |
| `GET /recipes/tags?q=` | tag suggestions: `{tags: [{name, recipes}]}`. A tag no recipe has any more isn't listed. |
| `POST /recipes` (201) | make a recipe. Only `name` is needed; `serves` defaults to 4 (send `null` for none). |
| `GET /recipes/{id}` | the whole recipe (below). |
| `PUT /recipes/{id}` | replace everything at once. Needs `version`. |
| `DELETE /recipes/{id}` | delete, at once, answering `{change}` with the Undo. |
| `POST /changes/{change_id}/undo` | the existing Undo; for a deleted recipe it brings the recipe back (`recipe` in the answer says which). |
| `GET /recipes/{id}/cannot-use` | the recipes this one can't use, and why. |

Ingredients (`/foods`) gain `used_in_recipes` (a count) and, on one ingredient, `used_in` (the recipes, A to Z); the list gains `filter=unused` ("Not in any recipe") and `counts.unused`.

### 2.1 The recipe

`POST` and `PUT` take the same body (`PUT` adds `version` and `overwrite`):

```json
{
  "name": "Sambar",
  "description": "Lentil & vegetable stew",
  "time_minutes": 50,
  "serves": 6,
  "makes": { "amount": 1.5, "unit": "litres" },
  "made_ahead": false,
  "homemade_name": null,
  "tags": ["Batch-friendly", "Quick"],
  "nutrition": { "kcal": 320, "protein": 14.5, "carbs": null, "fat": 9, "fibre": 11 },
  "lines": [
    { "kind": "heading", "words": "For the dal" },
    { "id": 41, "words": "thuvaram paruppu", "amount": "1½", "unit": "cup", "food_id": 7, "note": "rinsed" },
    { "words": "packet of dal", "amount": 1, "size_id": 12, "food_id": 7 },
    { "words": "Sambar powder", "amount": 2, "unit": "tbsp", "recipe_id": 3 },
    { "words": "salt to taste" }
  ],
  "steps": [ { "kind": "heading", "text": "The dal" }, { "text": "Boil the dal." } ],
  "source_note": "Amma's"
}
```

- **Limits.** (Decided by cabledrawer: name 200, 200 lines, 100 steps, 5,000 characters a step, serves 1 to 99, 20 tags of up to 40 characters, source note 500, time 14,400 minutes. Proposed, waiting for cabledrawer: description 200, a line's words and note 200.) Name 1 to 200 characters; description 200; source note 500; time 1 to 14,400 minutes; `serves` 1 to 99 or `null`; at most 200 lines (headings count), 100 steps (headings count), 5,000 characters in a step, 20 tags of up to 40 characters, a line's words and note up to 200 characters. Over a limit: the usual 422 list, whose `loc` says which box (`["body","lines",3,"amount"]`).
- **Amounts.** A number, or text such as `"½"`, `"1½"`, `"1 1/2"`, `"1/2"`, `"1.5"`. Empty or `null` is no amount. Zero and negatives are refused.
- **Units.** `g kg ml l tsp tbsp cup pinch` (also `grams`, `tablespoons`, …). No unit is a plain count ("10 shallots"). Or `size_id`: one of the linked ingredient's own sizes ("1 packet"), not together with a unit. A line linked to a recipe has no sizes. `makes.unit` is `g kg ml l` or a count word ("dosas").
- **Lines.** `food_id` or `recipe_id`, never both. `words` may be empty when linked (it then starts as the name). A heading has only words. Send a line's `id` back to keep it as the same line (ingredient merges follow lines by id); leave it out for a new line. A line the body leaves out is removed. The same goes for tags: send the whole list.
- **Nutrition.** Empty (`null` or left out) is stored as unknown, never 0. `0` is zero.
- **Text.** Tabs, line breaks, and invisible control characters are refused in every one-line field (422, "That has a tab, a line break or a hidden character in it. Take it out."). A step may have line breaks.
- **Made ahead.** With `made_ahead: true` and no live homemade ingredient, saving makes one (named `homemade_name`, else the recipe's name, cut to 100 characters; counted by weight, by volume or by number to match `makes`), records it in Ingredients' Recent changes, and links it. If the recipe has no live homemade ingredient but an ingredient with that name exists (Made ahead was switched off and on again), that ingredient is linked back, stock and all, unless another recipe has it as its own made-ahead ingredient: then 409 `name_taken` (nothing is saved). `made_ahead: false` unlinks it and keeps the ingredient. An ingredient that is a recipe's own made-ahead ingredient can't be removed: `DELETE /foods/{id}` answers 409 `in_use`, `detail` "Made by the recipe Dosa batter. Turn off Made ahead there to remove it." and `recipe: {id, name}` so the screen can link the name. `GET /foods/{id}` has `made_by: {id, name}` (or `null`) for the same reason.

What `GET` and the writes return: the same fields, plus `id`, `version`, `created_at`, `updated_at`, `updated_by {login_id, name}`, `homemade {id, name}`, `photo`, `used_by` (recipes that use this one), and per line `amount_text` (`"1½"`), `size`, `food`, `recipe`, and `link`:

| `link` | meaning |
|---|---|
| `ingredient` | linked to an ingredient (`food`) |
| `recipe` | linked to a recipe (`recipe`) |
| `recipe_removed` | the recipe it used was deleted; the line keeps its words; `recipe` is still sent so a save keeps the link; Undo makes it `recipe` again |
| `none` | not linked (the ingredient was removed, or none was picked) |
| `null` | a heading |

### 2.2 Two people editing (version)

Every save adds 1 to `version`. `PUT` must send the `version` the editor opened. If it is not the current one, nothing is saved and the answer is

```json
{ "detail": "Wren changed this recipe after you opened it.", "code": "recipe_changed",
  "version": 5, "changed_by": { "login_id": 2, "name": "Wren" }, "changed_at": "2026-10-19T18:04:11+00:00" }
```

"See Wren's version" is a plain `GET /recipes/{id}`. "Save mine anyway" is the same `PUT` again with `version` set to the 409's `version` and `overwrite: true`. The server still requires that to be the current version, so a third person's save in between is never overwritten unseen (another 409). `overwrite` changes nothing else the server does; it is how the request says what it means.

### 2.3 The loop guard

- `GET /recipes/{id}/cannot-use` answers `{recipes: [{id, name, reason, chain}]}`: the recipe itself ("A recipe can’t use itself.") and every recipe that already uses it, directly or through others, with the sentence for the editor ("Sambar powder can’t use Sambar, because Sambar uses Sambar powder.", and longer chains "…because Sambar uses Rasam powder, which uses Sambar powder."). `chain` is the names in order.
- Every `POST`/`PUT` checks again. A recipe using itself: 422 `recipe_self`. A loop: 409 `recipe_loop` with the sentence as `detail`, `chain`, `recipe_id` (the one picked) and `line` (the line's number in the body, from 0). Other refusals about a line (an ingredient, recipe, size or line id that isn't there or belongs to someone else) are 404 `not_found` with `line` too.
- A deleted recipe can't be picked, but a line that already used it can be saved as it is.

### 2.4 Delete and Undo

Bringing a recipe back is refused with 409 `recipe_loop` (the same words as a save) if, while it was deleted, other recipes were changed so that it would now make a loop.

`DELETE` hides the recipe at once. The answer's `change` has `can_undo` and `undo_until` (7 days, the household's undo window), and appears in Recent changes and for Ctrl+Z like any change. Undo (`POST /changes/{id}/undo`) brings the recipe back, and every line of other recipes that used it is linked again, because those lines never lost the link. After the window an hourly job deletes the recipe for good (with its lines, steps, tag links and photo record); lines of other recipes that used it then keep their words and show `link: "none"`. (The photos pull request must also delete the photo files at that point.) A retry of a delete with the same `Idempotency-Key` answers with the original change.

### 2.5 Retries

Creating and saving a recipe that carry an `Idempotency-Key` also remember it, as every other write does (a request with no key leaves nothing behind; a quiet change of kind `recipe_created` or `recipe_saved`, which is not listed in Recent changes and can't be undone). A retried `POST /recipes` makes nothing more and answers `200` with the recipe and `Idempotent-Replayed: true`; a retried `PUT` answers `200` the same way, instead of a `recipe_changed` conflict with yourself. The same key for a different request is 409 `key_reused`. Retrying a create after the recipe was deleted answers 404 `not_found`, because the answer is the recipe as it is now.

## 3. Ingredients that recipes use

- **Merge** moves the recipe lines (and a recipe's made-ahead link) to the kept ingredient; a line's size follows if the ingredient's size was joined with a matching one. The line's words stay. Undo of the merge puts them back.
- **"Made its own ingredient again"** (`/foods/{id}/split`) puts back the lines that the merge moved, as long as they are still on the kept ingredient. A line's packet size stays with the kept ingredient, so such a line loses its size.
- **Remove** keeps every line's words and amount but unlinks it (`link: "none"`); Undo links it again, unless the line was linked to something else or taken out of the recipe since (the Undo then says it only partly worked).
- A merge, a split, removing an ingredient, deleting or bringing back a recipe that others use, Undo of those, and the daily deletion for good each add 1 to the `version` of every recipe whose links they change, marked as changed by whoever did it (`Mealwright` for the daily deletion). An editor that was open on such a recipe is stopped by the usual `recipe_changed` answer instead of writing old links back.
