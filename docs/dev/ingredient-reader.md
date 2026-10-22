# The ingredient reader, matching and pasted text (0.5, PR 2)

Three pure modules in `backend/src/mealwright/`. No screens, no API addresses, no database change, nothing online. PR 3 joins them to the page reader (PR 1, which hands over each ingredient line as plain text) and to the Import review screen. The product rules are in `docs/spec.md` section 6, "Recipe import, decided for 0.5"; this file says how they were built, and what was decided where the spec is silent (marked **not in the spec**).

## 1. Reading one line: `ingredient_reader.read_line(text, size_words=())`

It never raises. A line it can't read is a result (`readable=False`), and `text` always holds the line exactly as given.

```
ReadLine(
    text,             # the line, exactly as given
    amount,           # Decimal > 0 and <= 1,000,000, or None
    unit,             # g, kg, ml, l, tsp, tbsp, cup, pinch; None for a plain count or a size word
    size_word,        # "sprig", "cloves", "tin", "few"... lower case, as written; or None
    name,             # without amount, unit, size word, brackets, note and prep words
    name_as_written,  # the same with the prep words left in ("chopped tomatoes")
    other_names,      # names given beside it: "toor dal" in "thuvaram paruppu (toor dal)"
    note,             # prep words, what follows a comma, bracket notes; at most 200 characters
    counts,           # counts towards stock by itself (see below)
    readable,         # False: no name left, or over 1,000 characters
)
```

`counts` is true for a real amount in a real unit and for a plain count ("3 eggs"). It is false for a pinch, a size word ("1 bunch"), "a few", and a line with no amount. A size word can still count once matching finds the ingredient has that size (section 2).

**Numbers.** `½  1½  1 1/2  1-1/2  1/2  0.5  .5  1,5  2⅓` (and ¼ ¾ ⅓ ⅔ ⅛ and the other fraction signs). The text of a number is turned into an exact fraction by the recipe editor's own reader (`recipe_schemas.fraction_of`; it was private and is now public, with `GLYPHS`), then rounded to the thousandth, the way amounts are stored (⅓ is 0.333). `1,500` is one thousand five hundred; `1,5` and `1,25` are decimals (**not in the spec**: a comma followed by exactly three digits is a thousands comma). An amount that rounds to 0, is 0, or is over 1,000,000 is no amount. Other digits (Devanagari, for example) are read too.

**Ranges.** `2-3`, `2–3`, `2 - 3`, `2 to 3`, and `2 or 3` (**not in the spec**; the same rule): the higher number is the amount. Units on either side are fine (`200g-300g`, `1 to 1½ cups`). With two different units (`200g-1kg`, `1 kg - 500 g`) both sides are compared in g or ml (a cup as 250 ml, only for the comparison) and the bigger one is kept with its own unit; if they can't be compared (g against ml) the second side is used.

**Two units.** `1 cup (240 ml) rice`, `200 g (7 oz) spinach`, `200g / 7oz`, `7 oz (200 g)`: the metric one (g, kg, ml, l) is the amount. If neither is metric the first stays (`1 cup (8 oz)` is a cup). A cup alone stays `cup`; the household's own cup is applied when the line is matched (section 2). A count with its weight in brackets, `1 (400 g) can chickpeas`, takes the weight and keeps the size word. A metric measure alone in a bracket after the name (`1 cup flour (125g)`, `1 cup rice (about 200 g)`) is the amount too, wherever the bracket sits, when the line's own unit isn't metric; a bracket after a bare count (`2 onions (300 g)`) stays a note. A pack multiple, `2 x 400g tins`, is 800 g (**not in the spec**); only one multiple is read.

**Units** are the recipe editor's (`recipe_schemas.UNIT_ALIASES`) and a few more spellings: mls, kgs, gms, ltr, lt, tbs, tbl, tsps, and `c`/`C` for a cup; a capital `T` is tbsp and a lower-case `t` is tsp. A unit has to be a whole word (`2 garlic cloves` is not 2 g; `3 T-bone steaks` is not 3 tbsp).

**Other systems' units (oz, lb, pint, quart, gallon, inch, cm, mm, fl oz)** (**not in the spec**): they are not the editor's units, and guessing a conversion would be a decision for cabledrawer. A line with only one of these gets **no amount** (so it never counts), and the measure goes into the note ("8 oz"). With a metric one beside it, the metric one wins.

**Size words.** The built-in list (`SIZE_WORDS`): bag, block, bottle, box, bulb, bunch, can, carton, clove, dash, dollop, dozen, drizzle, fillet, glug, handful, head, jar, knob, loaf, pack, packet, piece, pot, rasher, rib, sachet, sheet, slice, splash, sprig, stalk, stem, stick, tin, tray, tub, tube. Plural forms count. The household's own size names are passed in with `size_words=kitchen.size_words`, so a size such as "dabba" is read as one. A size word is looked for straight after the amount (past prep words: "2 large cloves of garlic"); `of` after it is skipped. "a", "an" and "one" at the start are 1 (**not in the spec**), unless a measure follows ("a 400g tin" is 400 g, size word tin). `a few`, `few`, `some`, `several`, `a little`, `a bit of`, `a couple of` have no amount and set `size_word` to that word. Spelled-out numbers ("two onions") are **not read** (**not in the spec**): the line is read without an amount.

**No real amount.** `to taste`, `as needed / required / desired`, `if needed`, `for garnish / serving / frying / dusting...`, `to serve / garnish`, `optional` go into the note. A line with no number has no amount (and never counts). A line that has a number keeps it: "1 tsp salt, or to taste" is 1 tsp (**not in the spec**, which only covers lines without a number). `a pinch of salt` and `pinch of salt` are 1 pinch, kept, never counted.

**The name and the note.** The line is split like this: brackets first (a bracket holding a number, "see note" style words, only prep words, or more than three words per piece is a note; a short bracket of plain words is an other name), then the first comma (everything after is a note), then "to taste" style phrases (the phrase and what follows go to the note), then a slash ("hing / asafoetida": the first is the name, up to two more are other names). Prep words are taken out of the name and kept in the note ("large, finely chopped"). Leading bullets and checkboxes (`•  -  ▢  ☐`) and "about", "approx.", "scant", "heaped" before a number are ignored.

**Prep words** (`PREP_WORDS`), a closed list. A word is on it only if taking it out never turns one ingredient into another. Left out on purpose: dried, ground, powder, whole, frozen, cooked, roasted, smoked, canned, baby, extra, and colours.

- How it is cut or treated: beaten, chopped, cooled, cored, crumbled, crushed, cubed, defrosted, deseeded, deveined, diced, drained, grated, halved, julienned, mashed, melted, minced, peeled, pitted, pounded, quartered, rinsed, seeded, shelled, shredded, sifted, sliced, soaked, softened, squeezed, thawed, torn, trimmed, unpeeled, warmed, washed, zested.
- How: coarsely, finely, freshly, lightly, neatly, roughly, thickly, thinly, well.
- Plain descriptors (`DESCRIPTOR_WORDS`): big, firm, fresh, large, medium, optional, organic, ripe, small.
- Others: divided, heaped, heaping, level, packed.

**A packaged product keeps its prep word** (**not in the spec**): when the size word is a container (tin, can, jar, packet, pack, bag, box, carton, bottle, tub, tube, sachet, pot, block), only the descriptors are taken out. "1 x 400g tin chopped tomatoes" is "chopped tomatoes", which is a different thing from "tomatoes".

## 2. Matching: `ingredient_match`

`kitchen_of(db, household_id) -> KnownIngredients` is one read of the household's ingredients (not removed, not merged away), their other names and sizes, its places and its cup. Every query is limited to the household, and a name or size row is used only if its ingredient is one of the household's. (The brief called the class `Kitchen`; that name is already the request context in `api/v1/context.py`, so this one is `KnownIngredients`.) It also offers `size_words` (for `read_line`) and `cupboard_id`.

`match_line(known, read) -> Match`. Pure; nothing is written.

```
Match(read, label, food_id, food_name, matched_by, size_id,
      counts, amount_base, base_unit, new_ingredient)
```

**How it chooses.**

1. A line that couldn't be read: `needs_you`.
2. Each way the line names the ingredient is a candidate, in this order: `name_as_written` (so a food really called "Chopped tomatoes" beats "Tomatoes"), `name`, then `other_names` (from brackets and slashes). A candidate matches an ingredient when their keys are equal. The key is `names.normalise` (lower case, no accents, nothing in brackets, no punctuation, words made singular) plus "-y" = "-i" (chilli, chillies) and leaf = leaves. Within a candidate, an ingredient's name beats another ingredient's other name; the oldest ingredient wins a tie. Found: `matched`, or `staple` if that ingredient is a staple.
3. Otherwise, the closest ingredient (its name or an other name): all its words are inside the line's name, or all of the line's words are inside its name, or the same words in another order ("red onion" and "Onions", "dal toor" and "Toor dal"). The best share of the words wins; the line's name being more specific than the ingredient's beats the other way round; the oldest ingredient breaks a tie. Found: `to_confirm`, with that ingredient as the guess. A staple is never labelled `staple` by a close match.
4. Otherwise `needs_you`.

**What counts.** A staple never counts. Otherwise a line counts when it has an amount, is not a pinch, and either has a unit, or has no size word, or its size word names one of the matched ingredient's sizes (compared by `names.normalise`, name or plural). `size_id` says which. A line that is not matched says what it would do: `counts = read.counts`, so a size word does not count there.

**Base amounts.** When a line counts, `amount_base` and `base_unit` give g, ml or count: g and kg to grams, ml/l/tsp/tbsp to ml, a cup to the **household's own cup** (`household.cup_ml(...)`, 250 if unset; `amounts.unit_size`), a plain count as it is, a size word as the size's amount (in the ingredient's base unit). A cup that came with a metric amount ("1 cup (240 ml)") is already ml. Never an assumed 250.

**For PR 3: two things `amount_base` does not do.** (1) It is in the *line's* measure, not the ingredient's: "1 cup rice" against Rice counted by weight gives 250 ml, and "200 g onions" against Onions counted by number gives 200 g. PR 3 has to convert (the weight of a cup, the weight of one item) or ask, the way the recipe editor does. (2) The 1,000,000 cap is applied to the amount in the line's own unit, as the recipe editor does, so a converted amount can go over `amounts.MAX_AMOUNT` ("1,000,000 kg" in grams). PR 3 must handle both.

**The first guess for a new ingredient** (`first_guess(known, read, staple=False)`, also on every `Match` as `new_ingredient`): the name is the line's name with a capital ("finely chopped red onions" is "Red onions"; at most 100 characters; a line that couldn't be read uses its own words); counted as weight for g/kg, volume for ml/l/tsp/tbsp/cup, count for a plain number or a size word, and weight when there is no amount or only a pinch (**not in the spec**, same as `make_food`'s default); place is the household's place called Cupboard (any case), else none; staple off. "Treat as staple" is the same guess with `staple=True`. Nothing is added to the pantry. Learning an other name ("Same as Onions" adds "red onion") and creating ingredients happen on Save in PR 3, using `read.name` and `new_ingredient`.

## 3. Pasted text: `pasted_recipe.read_pasted(text) -> PastedRecipe`

```
PastedRecipe(name, ingredients: tuple[str, ...], steps: tuple[str, ...], lines_cut, steps_cut)
```

- Over 100,000 characters (counted before anything is stripped) raises `PastedTooLong`; `str(error)` is the sentence (`PASTED_TOO_LONG`, proposed in `words.md` section 18).
- Hidden characters are stripped, not refused (`names.without_hidden`): the same characters `has_hidden` finds, with line separators turned into line breaks and tabs into spaces. Joiners (Tamil, Hindi) and flag emoji stay.
- **With headings:** `Ingredients` / `You will need` and `Method` / `Instructions` / `Directions` / `Preparation` / `Steps` / `Procedure` (any case, with `#`, `**`, a colon or a bracket after). The words only count as a heading when they are the whole line (at most 40 characters), the first time. `Notes`, `Tips`, `Nutrition`, `Equipment`, `Storage`, `Variations`, `Serving suggestions` start a part that is left out (**not in the spec**; a recipe has no notes box in 0.4). In a numbered method such a part ends where the next number carries on ("1. … Tips … 2. …" keeps step 2); in an unnumbered method it can't be told apart, so it runs to the end. The first non-empty line before the first heading is the title (the name is "" if there is none, or if that line is an amount).
- Only one heading: the amounts above a lone Method heading are the ingredients; after a lone Ingredients heading, the ingredients end at the first numbered step or after the last line that looks like an amount.
- **With no headings (best guess):** the first line is the title; the lines from the first to the last one that look like an amount are the ingredients (short unpunctuated lines among them, and straight after them, such as "Salt", are ingredients too); everything else after them is the method.
- **Looks like an amount:** starts with a number or fraction (or "a pinch/handful/few..."), `read_line` finds an amount, and it has a unit or size word, or is at most seven words and does not end with a full stop. Not a numbered step ("1. Heat oil"), not a time or temperature ("20 minutes", "180°C").
- **Steps:** a leading `1.`, `1)`, `1:`, `Step 1:` or bullet is taken off. If any line is numbered, an unnumbered line straight after a numbered one carries on that step; a blank line ends it. If none are numbered, each line is a step.
- **Limits:** the first 200 ingredient lines and 100 steps are kept (`lines_cut`, `steps_cut` say how many were left out); an ingredient line is cut at 200 characters (`MAX_LINE_CHARS`, the editor's limit for a line's words), the title at 200 and a step at 5,000, never in the middle of a flag emoji, a letter and its marks, or a joined sequence (`names.cut_text`) (**not in the spec**; PR 3 may prefer to tell the person).
- Ingredient lines that look like sub-headings ("For the sauce:") are kept as lines; PR 3 decides what to do with them.
