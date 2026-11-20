# API and data for 0.4 (recipes): the data and the API

Written 19 Oct 2026 for the first 0.4 pull request ("Recipes: the data, the API and the loop guard"). The conventions, error shape, `Idempotency-Key` and Undo are the same as in `api-endpoints.md`; read its section 1 first. The spec (`docs/spec.md`, section 6 "Recipes") wins wherever this file disagrees with it. The generated OpenAPI (`/api/v1/openapi.json`) is the exact reference.

Recipes are online only in 0.4. Nothing here touches the shopping-list sync or the offline queue.

## 1. Tables (migrations `c5e8a1f3b7d2`, and `97d61f9dd082` for photos)

Every table has `household_id`.

| Table | Holds |
|---|---|
| `recipe` | name, description, `time_minutes`, `serves` (1 to 99 or empty), `makes_milli` + `makes_unit`, `made_ahead`, `homemade_food_id` (the recipe's own pantry ingredient), five nutrition columns (`*_milli`, empty = unknown), `source_note`, `version`, who and when it was last saved, `removed_at` (a deleted recipe, for the undo window) |
| `recipe_line` | an ingredient line or a heading: position, `words` (as typed), `amount_milli` and `unit` (in the unit typed, not a base unit), `size_id`, `food_id` or `sub_recipe_id` (never both), `note` |
| `recipe_step` | a step or a heading: position, `text` |
| `tag`, `recipe_tag` | tags the household typed, and which recipe has which |
| `recipe_photo` | the photo's record only: `recipe_id` (empty for an upload not saved on a recipe yet), `file_key` (the random file name), the large copy's `width` and `height`, `list_width` and `list_height`, `bytes` (both files), who added it and when. The files are on the data volume (section 2.6). `97d61f9dd082` (the photos pull request) made `recipe_id` optional and added `list_width` and `list_height`. |

Amounts are thousandths of the unit the person typed (`2 tbsp` is `2000`). Nutrition is thousandths too; `NULL` is "unknown" and `0` is a real zero.

## 2. Endpoints

All under `/api/v1`, signed in, same-origin for writes. An id from another household is a 404.

| | |
|---|---|
| `GET /recipes?limit=&after=&q=&tag=&can_cook_now=&use_soon=` | every recipe, A to Z, each with its stock hints (section 4). `{total, all_recipes, recipes: [row], next}`. A deleted recipe isn't listed. |
| `GET /recipes/tags?q=` | tag suggestions: `{tags: [{id, name, recipes}]}` (`id` added 0.8). A tag no recipe has any more isn't listed. |
| `PATCH /recipes/tags/{id}` | rename a tag (`{name}`, the tag limits). A name another tag has (ignoring case and accents) is 409 `tag_exists`, carrying that tag: it is refused, not merged (a tag that no shown recipe has is folded in instead). Not in Recent changes. (0.8, cabledrawer 9 Nov) |
| `POST /recipes/tags/{id}/merge` | `{into}`: the recipes with this tag get `into` (one if both), the tag goes. Answers `{change, into}`; the change (kind `tags_merged`) is in Recent changes and its Undo (`POST /changes/{id}/undo`) brings the tag back on exactly the recipes that had it, refused with 409 `tag_exists` while a tag with the old name exists. (0.8) |
| `POST /recipes` (201) | make a recipe. Only `name` is needed; `serves` defaults to 4 (send `null` for none). |
| `GET /recipes/{id}` | the whole recipe (below). |
| `POST /recipes/{id}/duplicate` (201) | (0.7, paper cuts) make a copy named `<name> (copy)` and answer with it, like `GET /recipes/{id}`. It has everything in the recipe: lines, steps with their ingredient links, tags, nutrition, Serves, Makes, Made ahead, where it came from and the photo (copied to files of its own, so removing the photo on one never touches the other). It has none of the recipe's cooked history or its place in the plan. A copy of a Made ahead recipe gets its own pantry ingredient named like the copy. If a recipe (or that ingredient) already has the name, the copy is `<name> (copy 2)`, then `(copy 3)` and so on, so a copy never fails for its name (proposed, for cabledrawer). The same `Idempotency-Key` makes one copy (200 and `Idempotent-Replayed` the second time). Another household's recipe, or a deleted one: 404. |
| `PUT /recipes/{id}` | replace everything at once. Needs `version`. |
| `DELETE /recipes/{id}` | delete, at once, answering `{change}` with the Undo. |
| `POST /changes/{change_id}/undo` | the existing Undo; for a deleted recipe it brings the recipe back (`recipe` in the answer says which). |
| `GET /recipes/{id}/cannot-use` | the recipes this one can't use, and why. |
| `POST /recipes/photos` (201) | upload a photo (the file itself as the body); answers `photo` with its id. Section 2.6. |
| `GET /recipes/photos/{id}/large`, `/list` | the photo's large or list copy (a JPEG). |
| `DELETE /recipes/photos/{id}` (204) | delete an upload that isn't saved on a recipe (cabledrawer 20 Oct). |

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
  "source_note": "Tess's",
  "photo_id": 5
}
```

- **A step's ingredient lines (0.7 K1, for Cook mode's per-step ingredients).** A step may carry `"lines": [0, 2]`: the ingredient lines it uses, set by hand, as positions in the same save's `lines` (counting from 0), so a new line can be linked in the save that adds it. Left out or `null`: the step keeps the links it had when the recipe had a step with the same words before and the line is still in the recipe; any other link goes. `[]`: none. A position past the end, a heading line, or lines on a heading step → `422`. The recipe answers each step with `"lines": [{ "line_id", "line", "kind" }]`, where `line` is the line's position in `lines` and `kind` is `"guessed"` (guessed from the step's words, 0.7 K4) or `"by_hand"`.
- **Limits.** (Decided by cabledrawer: name 200, 200 lines, 100 steps, 5,000 characters a step, serves 1 to 99, 20 tags of up to 40 characters, source note 500, time 14,400 minutes. Proposed, waiting for cabledrawer: description 200, a line's words and note 200.) Name 1 to 200 characters; description 200; source note 500; time 1 to 14,400 minutes; `serves` 1 to 99 or `null`; at most 200 lines (headings count), 100 steps (headings count), 5,000 characters in a step, 20 tags of up to 40 characters, a line's words and note up to 200 characters. Over a limit: the usual 422 list, whose `loc` says which box (`["body","lines",3,"amount"]`).
- **Amounts.** A number, or text such as `"½"`, `"1½"`, `"1 1/2"`, `"1/2"`, `"1.5"`. Empty or `null` is no amount. Zero and negatives are refused. Text is at most 20 characters, spaces included; longer text is refused with the same error as any amount the server can't read, before it's read.
- **Units.** `g kg ml l tsp tbsp cup pinch` (also `grams`, `tablespoons`, …). No unit is a plain count ("10 shallots"). Or `size_id`: one of the linked ingredient's own sizes ("1 packet"), not together with a unit. A line linked to a recipe has no sizes. `makes.unit` is `g kg ml l` or a count word ("dosas").
- **Lines.** `food_id` or `recipe_id`, never both. `words` may be empty when linked (it then starts as the name). A heading has only words. Send a line's `id` back to keep it as the same line (ingredient merges follow lines by id); leave it out for a new line. A line the body leaves out is removed. The same goes for tags: send the whole list.
- **Nutrition.** Empty (`null` or left out) is stored as unknown, never 0. `0` is zero.
- **Photo.** `photo_id` is an upload's id (from `POST /recipes/photos`) or the photo the recipe has already. Left out: the photo stays as it is. `null`: no photo, and the one it had is deleted when the save goes through, files included. A new id: that photo replaces the old one, which is deleted the same way. (cabledrawer 20 Oct.) A contract for the editor: "Remove photo" must send `"photo_id": null` explicitly; leaving the field out never removes the photo. A test checks both on the same recipe. Only an upload of your own household that isn't on any recipe yet can be attached; any other id (unknown, another household's, one on another recipe) is 404 `not_found`, "That photo isn't here any more.", and nothing is saved.
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

`DELETE` hides the recipe at once. The answer's `change` has `can_undo` and `undo_until` (7 days, the household's undo window), and appears in Recent changes and for Ctrl+Z like any change. Undo (`POST /changes/{id}/undo`) brings the recipe back, and every line of other recipes that used it is linked again, because those lines never lost the link. After the window an hourly job deletes the recipe for good (with its lines, steps, tag links and photo, whose files are deleted once that's committed); lines of other recipes that used it then keep their words and show `link: "none"`. Undo within the window keeps the photo; while the recipe is deleted, its photo isn't shown. A retry of a delete with the same `Idempotency-Key` answers with the original change.

### 2.5 Retries

Creating and saving a recipe that carry an `Idempotency-Key` also remember it, as every other write does (a request with no key leaves nothing behind; a quiet change of kind `recipe_created` or `recipe_saved`, which is not listed in Recent changes and can't be undone). A retried `POST /recipes` makes nothing more and answers `200` with the recipe and `Idempotent-Replayed: true`; a retried `PUT` answers `200` the same way, instead of a `recipe_changed` conflict with yourself. The same key for a different request is 409 `key_reused`. Retrying a create after the recipe was deleted answers 404 `not_found`, because the answer is the recipe as it is now.

### 2.6 Photos (cabledrawer 19 and 20 Oct)

**Upload.** `POST /recipes/photos` takes the photo file itself as the request body (not a form), `Content-Type` `image/jpeg`, `image/png` or `image/webp`; what the file is comes from its bytes, never the type or a name. Only this route takes up to 15 MB (15 × 1024 × 1024 bytes); every other request stays at 4 MiB. The sign-in is checked before the body is read, and the size is counted as it arrives. The server then:

1. refuses anything over 50 megapixels from its header alone (exactly 50,000,000 pixels is taken; 422 `too_many_pixels`, "That photo is too big to use (over 50 megapixels). Try a smaller copy.", cabledrawer 20 Oct), and anything that isn't a JPEG, PNG or WebP Pillow can read whole: GIF, SVG, HEIC, a text file called `.jpg`, a file cut short (422 `not_a_photo`, "That isn't a photo Mealwright can use. Try a JPEG, PNG or WebP."). Over 15 MB is 413 `photo_too_big`, "That photo is bigger than 15 MB.";
2. makes it the large copy's size first (a JPEG is decoded at a smaller scale, Pillow's draft mode, cabledrawer 20 Oct; the scale is picked from the file as stored, before it's turned, so a sideways photo still gets the full 1600 px), so a big photo is held full size in memory only once, and works on one photo at a time for the whole server; then turns it upright (EXIF orientation), keeps an animated picture's first frame, converts colours from the file's colour profile to sRGB, makes see-through parts white, and rebuilds the picture from its pixels alone, so no EXIF (camera, date, GPS), XMP, PNG text, comment, thumbnail or colour profile is kept;
3. saves two JPEGs (quality 85): the large copy (longest side 1600 px, never made bigger) and the list copy (shortest side 156 px, the 52 px list square at 3×, kept as cabledrawer agreed on 20 Oct; never bigger than the photo, and never longer than 1600 px). The file sent is not kept.

The answer (201) is the photo, the same shape as a recipe's `photo`:

```json
{ "id": 5, "width": 1600, "height": 1200, "url": "/api/v1/recipes/photos/5/large",
  "list_width": 208, "list_height": 156, "list_url": "/api/v1/recipes/photos/5/list" }
```

A household can have at most 10 uploads that aren't on a recipe (cabledrawer 20 Oct); the 11th is 409 `too_many_photos_waiting`, "Too many photos waiting to be saved. Save or cancel a recipe first." Uploads still being worked on count too: each takes its place before its photo is cleaned and gives it back if it fails, so uploads sent at once can't all get past the count. Saving one on a recipe, deleting one, or the 24-hour clean-up frees a place. The count is each household's own. There is no `Idempotency-Key` on uploads: a retry uploads the photo again, and the extra one is deleted after 24 hours like any unsaved upload.

**Attach.** Nothing on the recipe changes until Save (cabledrawer 20 Oct): send `photo_id` in `POST /recipes` or `PUT /recipes/{id}` (section 2.1). An upload no recipe has taken within 24 hours is deleted by the hourly job (on this server only; it contacts nothing).

**Show.** `GET /recipes/photos/{id}/large` and `/list` answer the JPEG, for people signed in to the photo's household only: `Content-Type: image/jpeg`, `X-Content-Type-Options: nosniff`, and, like every `/api` answer, `Cache-Control: no-store` (sync protocol section 12; for photos too, cabledrawer 20 Oct). An unsaved upload can be shown (the editor's preview); a photo of a deleted recipe can't, until Undo. A replaced photo always gets a new id, so a URL always shows the same picture. Another household's id, or one that doesn't exist, is 404 `not_found` "That photo isn't here any more.", the same answer for both. The pages' Content Security Policy, `img-src 'self' data: blob:` (unchanged), already allows these URLs, since they're on Mealwright's own address.

**Delete an unsaved upload** (cabledrawer 20 Oct). `DELETE /recipes/photos/{id}` (204) deletes an upload of your household that isn't on a recipe, files included: for an editor that's cancelled. A photo on one of your recipes is 409 `photo_in_use` ("That photo is on a recipe. Take it off in the recipe, then save.", cabledrawer 20 Oct): it goes by saving the recipe with `"photo_id": null`. Another household's id is 404, exactly as an unknown one.

**Files.** In the data folder, `photos/<household id>/<random 32 letters>.jpg` and `…-list.jpg`; the folder is readable by the server only. Each file is written to a temporary file in the same folder and renamed, so a half-written file is never shown. Files are deleted only once the database change that deleted the record is committed. The hourly job also deletes files in a household's folder that have no record and are over a day old (after a crash, say).

## 3. Ingredients that recipes use

- **Merge** moves the recipe lines (and a recipe's made-ahead link) to the kept ingredient; a line's size follows if the ingredient's size was joined with a matching one. The line's words stay. Undo of the merge puts them back.
- **"Made its own ingredient again"** (`/foods/{id}/split`) puts back the lines that the merge moved, as long as they are still on the kept ingredient. A line's packet size stays with the kept ingredient, so such a line loses its size.
- **Remove** keeps every line's words and amount but unlinks it (`link: "none"`); Undo links it again, unless the line was linked to something else or taken out of the recipe since (the Undo then says it only partly worked).
- A merge, a split, removing an ingredient, deleting or bringing back a recipe that others use, Undo of those, and the daily deletion for good each add 1 to the `version` of every recipe whose links they change, marked as changed by whoever did it (`Mealwright` for the daily deletion). An editor that was open on such a recipe is stopped by the usual `recipe_changed` answer instead of writing old links back.

## 4. The All recipes list (search, tags, Can cook now, stock hints)

`GET /recipes` takes `limit` (1 to 500, default 50), `after`, and four things that work together:

| | |
|---|---|
| `q` | words to search for (up to 100 characters). Every word must be found, ignoring case and accents. It looks in the recipe's name, its tags, and its ingredient names: the ingredient's name and **other names** (`thuvaram` finds a recipe with Toor dal), the words typed on the line, and the name of a recipe used as an ingredient. **Never the method.** |
| `tag` | keep recipes with this tag (ignoring case). |
| `can_cook_now=true` | keep recipes that can be cooked now (below). |
| `use_soon=true` | keep recipes that use an ingredient with stock on Use soon: exactly the recipes whose row has a `use_soon` hint (below), from the same code, so the two can't disagree. Added for cabledrawer's "Recipes for these" on Pantry; the filter and link agreed by cabledrawer 20 Oct. It takes the same values as `can_cook_now` (`true` or `false`, and the other spellings a boolean query parameter accepts, such as `1` and `0`); a value that is no boolean at all is a 422. |

`total` is how many match; `all_recipes` is how many recipes the household has (the number in the screen's title). `next` pages through the matches. Every row is the brief (section 2) plus:

```json
{ "kcal": 320, "stock": { "counted": 7, "missing": 1, "can_cook_now": false },
  "use_soon": { "foods": [{ "id": 3, "name": "Spinach" }], "use_by": "2026-10-20", "days_left": 0 },
  "stock_unchecked": false }
```

- `kcal` is per serving; `null` is unknown (the screen says "nutrition unknown"), `0` is a real zero.
- `stock` is `null` when no ingredient line counts. `use_soon` is `null` when nothing the recipe uses is about to go off. `stock_unchecked` is `true` when some line uses a recipe that isn't checked (below); then the screen never says "all in stock", so it doesn't guess.

**What counts as "in stock".** cabledrawer's answer (19 Oct, question 22): an ingredient is in stock when the pantry holds **enough for the recipe at its own servings**, if the two amounts can be compared; if they can't, **any stock counts**. cabledrawer's answers of 20 Oct (1 to 5) are marked. The rest is the spec's, as marked.

- Only ingredient lines **with an amount** count. A line with no amount, such as "salt to taste", never counts towards stock (cabledrawer 19 Oct, question 13); headings don't count (cabledrawer 20 Oct); a line linked to nothing has nothing to check. `counted` is the number of different ingredients that count; `missing` how many of those are not in stock. A recipe where no line counts gets no hint (`stock` is `null`) and is not in Can cook now (cabledrawer 20 Oct).
- A **staple** always counts as in stock (the spec, Stock section: "Staples: assumed in stock, not quantity-tracked").
- Any other ingredient is in stock when the pantry holds **enough for the recipe at its own servings**, when the two amounts can be compared (the line's unit or size against the ingredient's own, using the household's cup size and the weights it knows) (cabledrawer, Q22). Several lines for one ingredient are added up. When they can't be compared (a cup of something with no known weight, a pinch), **any stock counts** (cabledrawer, Q22).
- Stock in every place counts, the freezer too (cabledrawer 20 Oct).
- A line that uses a recipe **marked Made ahead** is checked against that recipe's own pantry ingredient (cabledrawer 20 Oct).
- A line that uses **any other recipe** (not made ahead) is **not checked** for now: inner recipes are checked in a later version (cabledrawer 20 Oct). So is a line using a made-ahead recipe with no pantry ingredient yet, or a recipe that has since been deleted (cabledrawer 20 Oct). A line with no amount is ignored, whatever it points at (cabledrawer 20 Oct, question 13). Such a recipe has `stock_unchecked: true`, and then: it is **never in Can cook now** (`can_cook_now` is `false`, and the filter leaves it out); its hint **never says "all in stock"**, and **not "all in stock but 1" either**; the screen says "N missing" when something that was checked is missing, and no stock words otherwise (cabledrawer 20 Oct). Two levels deep, the outer recipe is unchecked if its direct line is not made ahead; a made-ahead inner recipe with a pantry ingredient works as before, whatever it uses itself.
- `can_cook_now` is: something counts, nothing is missing, and no line is left unchecked (cabledrawer 20 Oct).

**Use soon (cabledrawer 20 Oct):** `use_soon` names the ingredients the recipe uses (lines that count, as above) that have a packet with a use-by date from today up to the household's Use soon limit (today, tomorrow or the day after: spec, Stock). Only the ingredients with the **soonest** date are named, so one date always goes with them. A packet whose date has passed is not a nudge and is left out.

"Planned Sun" waits for 0.6.

**Cost.** However many recipes there are, the list reads a fixed number of rows sets (recipes, lines, ingredients, sizes, conversions, stock, tags, other names, then the page), never one query per recipe. A test counts them with 10 and with 300 recipes. Everything is limited to the signed-in household.

## 5. Where one recipe's ingredients are (the recipe page)

`GET /recipes/{id}/stock?servings=` (signed in; another household's or a deleted recipe is a 404) answers, for the recipe page, the same stock rules as section 4, line by line. It only reads. **`servings`** is optional, a whole number from 1 to 99 (anything else is a 422, like the API's other range errors); it is what the page's minus and plus buttons chose, and the amounts needed scale by `servings` / the recipe's Serves (rounded up, so a short pantry is never called enough). Left out, the recipe's own Serves is used. A recipe with no Serves ignores `servings`. This is cabledrawer's Q22 rule (19 Oct, Q22): there must be enough for the recipe at the chosen servings when the amounts can be compared; when they can't (no known weight for "1 cup"), any stock counts. The All recipes list has no stepper and stays at each recipe's own servings.

```json
{ "lines": [ { "line_id": 41, "food": { "id": 7, "name": "Toor dal" }, "state": "in_stock", "place": "Cupboard" } ],
  "counted": 7, "missing": 1, "stock_unchecked": false }
```

- `state`: `in_stock` (enough, or any when the amounts can't be compared), `staple` (assumed in stock), `short` (some in the pantry, not enough), `missing` (none). `place` is where most of it is (the first of equal places in their order), only for `in_stock`.
- `food` is the pantry ingredient the line is checked against: the linked ingredient, or a made-ahead recipe's own ingredient.
- Lines that don't count are left out: headings, lines linked to nothing, lines using a recipe that isn't checked. Several lines for one ingredient are added up and share its state. **A line with no amount (0.5.1)** still never counts (`counted` and `missing` leave it out), but it gets a mark when there is one: `staple`, or `in_stock` with its place when there is any stock (as when amounts can't be compared, Q22), or the state of another line for the same ingredient that does count; with none of those it is left out, never `missing`. (cabledrawer's hand test: "salt to taste" linked to the Salt staple showed no "Staple".)
- `counted`, `missing` and `stock_unchecked` are exactly the list's hint for this recipe (a test compares them). The screen never says "all in stock" when `stock_unchecked` is `true`.
- "On list" is not here: the page reads the shopping list's own copy, so it follows waiting changes and live updates.
- A fixed number of queries however many recipes and lines there are (tested).

## 6. Optional lines and steps, and the nutrition note (0.8 wave 4, R3; cabledrawer 6 and 9 Nov)

Additive: nothing that was sent before changes.

- **Tables.** Migration `b6d1f3a8c254` adds `recipe_line.optional` and `recipe_step.optional` (false for every existing row), `meal_item.optional_skipped` (a list of line ids; null for every existing meal: every line counts), and `recipe.nutrition_set_at` and `recipe.lines_changed_at` (null for every existing recipe: no note).
- **In and out.** A line in `POST` / `PUT` takes `"optional": true | false` (false when left out, so a save that leaves it out makes the line ordinary again: send it back whole, as the editor does); a step takes the same. A heading with `optional: true` → `422`. `GET` answers `optional` on every line and step. A copy (`POST /recipes/{id}/duplicate`) keeps them. The list rows (`GET /recipes`) say `optional_count`, how many ingredient lines are Optional.
- **Stock hints ignore Optional lines.** A line that is Optional is left out of `counted`, `missing`, `can_cook_now` and `use_soon` on the list and on `GET /recipes/{id}/stock` (like a line with no amount); the per-line answers of `/stock` still include it, so the plan question can say where it is.
- **The nutrition note.** `nutrition.possibly_out_of_date` (read-only) is true when some ingredient line changed (its words, amount, unit, size or link, a line added, removed or moved; not its note, and not whether it is Optional) after the figures were last set, and some figure is set. The figures are set when the recipe is made, when a save changes one, or when a save sends `"nutrition_checked": true` (the editor opened by "Update nutrition": the person looked at them and kept them). Nothing is worked out from the ingredients (not in v1); nothing is fetched.
- **The plan.** `POST /plan/items` takes `optional_use`, the Optional line ids the meal will use; `PUT /plan/items/{id}/optional` changes it (`api-endpoints.md`, plan). `GET /plan` items say `optional_skipped`, and their recipe `optional_count`.
- **Cooked it.** The record's snapshot lines and steps say `optional`; the review proposes, and the record holds, only the lines the meal uses.

## 7. Steps that wait (0.8 wave 5, M1, F124; cabledrawer 31 Oct and 9 Nov)

Additive: nothing that was sent before changes.

- **Tables.** Migration `e8a3c5b1d7f9` (after `b6d1f3a8c254`) adds `recipe_step.wait_kind`, `wait_min_minutes`, `wait_max_minutes` and `wait_overnight` (empty and false for every existing step: a recipe made before keeps its single time, and nothing is guessed from old words). No new table.
- **In.** A step in `POST` / `PUT` takes `"wait": null | {"kind", "min_minutes", "max_minutes"?, "overnight"?}`. `kind` is `marinate`, `soak`, `ferment`, `rest`, `chill` or `prove`; the lengths are whole minutes, 1 to 14,400; `max_minutes` left out means one length; `overnight: true` means the range ends at "overnight", which counts as 12 h (720 minutes): the longest is raised to 720 if it is less, so M3 can work backwards from a number. The longest below the shortest, an unknown kind or a heading with a wait → `422`. A save that leaves `wait` out makes the step not wait (send the recipe back whole, as the editor does). A copy keeps the waits.
- **Out.** Each step answers `wait` (the same four fields, `max_minutes` always set, or `null`). The recipe (`GET /recipes/{id}`), each list row (`GET /recipes`) and a plan item's recipe (`GET /plan`) answer `wait`: all the steps' waits added up (shortest and longest summed, `overnight` if any ends that way, `kind` the kind if all are one kind, `"wait"` otherwise), or `null`. `time_minutes` is the active time when `wait` is set.


**Step timings for Batch cook (0.8 wave 6, B1; cabledrawer 28 Oct and 11 Nov).**

- **Tables.** Migration `c3e9a1d7b504` (after `a7c4e9d2b813`) adds `recipe_step.timing_hands`, `timing_minutes` and `timing_equipment`: what a person set by hand. Empty means guessed. Nothing is backfilled: a guess is made from the step's words every time the step is read (`step_timings.py`), so a step made before this, or one whose words change, always has a current guess, and a value set by hand is never overwritten.
- **In.** A step takes `"timing": null | {"hands"?: "hands" | "waiting", "minutes"?: 1–14,400, "equipment"?: "hob" | "pressure" | "oven" | "none"}`. A value left out or null is not set by hand (it is guessed). A save that leaves `timing` out keeps what the step's old self had if its words are unchanged (a client that knows nothing of timings loses none); `"timing": null` clears it. A heading with a `timing`, an unknown value, or minutes out of range is `422`. A copy keeps what was set by hand.
- **Out.** Each step answers `timing`: `{ "hands", "minutes", "equipment", "hands_guessed", "minutes_guessed", "equipment_guessed" }` (a `*_guessed` is true until set by hand), or `null` for a heading. A step with a wait (M1) is guessed as waiting, for the wait's longest length (overnight is 720).
- **Not changed.** `time_minutes` stays a single optional number (up to 14,400); a recipe made before has no wait and its whole time in it. The cooked-it snapshot and Cook mode don't carry waits yet (M2, M3).
