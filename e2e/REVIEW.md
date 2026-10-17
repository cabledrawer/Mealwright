# Reviewing a pull request

The checklist the checker applies to every PR before it reaches cabledrawer. A PR passes
only when every box is ticked or the gap is written up in the review with a reason.

## Tools

```sh
cd e2e
npm ci && npx playwright install chromium-headless-shell

# Accessibility and browser tests (also run by ./check)
E2E_APP_PORT=18300 npx playwright test

# Screenshots: the app beside its mockup, phone 390×844 and desktop 1440×900,
# light and dark. Writes e2e/review-shots/<name>/ (git-ignored). Not part of ./check.
E2E_APP_PORT=18300 node review/screens.ts --screen Pantry --path /pantry --serve
node review/screens.ts --screen Ingredients            # mockups only
# --prepare file.ts: seed(api) adds test data; prepare(page, shot) clicks things open
```

`tests/a11y.ts` has `checkPage(page)`: axe with the WCAG 2.0/2.1/2.2 A and AA rules in
light and dark, and on the phone project 44 × 44 px touch targets and no sideways
scroll. New pages go into `tests/a11y.spec.ts`; new states (a sheet open, a toast
showing) get their own `checkPage` call in the feature's tests.

## Checklist

**Spec**
- [ ] Matches `docs/spec.md`, including every "Decided for 0.2 (cabledrawer 17 Oct)" block
      (Foods and units, Stock, History and undo). Where code and spec disagree, the spec wins.
- [ ] Parts that depend on later milestones are hidden, not stubbed: "+ List", "tap a
      staple when it runs out" (0.3); tubs (0.6); "Used in N recipes", "Not in any
      recipe", "Recipes for these" (0.4).
- [ ] Anything the spec doesn't cover is listed under "What cabledrawer needs to check".
- [ ] Every new table has `household_id`; every schema change is an Alembic migration.
- [ ] The web app uses only public `/api/v1` endpoints, and they're in the OpenAPI.

**Ethos**
- [ ] No outgoing network calls outside the outbound gate (`grep -rnE "httpx|requests|urllib|socket|aiohttp|fetch\(" backend/src`; the socket-blocking test still runs).
- [ ] No CDN, Google Fonts or other outside asset; the CSP is unchanged or stricter.
      `review/screens.ts` prints any request to an outside address.
- [ ] No telemetry, analytics, crash reporting, location access.
- [ ] New dependencies: named in the PR, licence on the allow list, versions pinned and
      at least two weeks old, cabledrawer asked first.

**UX**
- [ ] Plain words: "cupboard", "use soon", "packets"; never "items", "units", "lots",
      "entities", "quantity", "SKU", "location". Wording matches the mockup unless the
      spec says otherwise.
- [ ] Undo, not "Are you sure?": no confirm dialogs. Every change shows an Undo toast;
      Ctrl+Z on desktop undoes your own last change.
- [ ] Optimistic updates: the screen changes before the server answers, and rolls back
      with a calm message if it fails (test with the request held or failing).
- [ ] One switch component (`Switch.svelte`) for every on/off; no checkboxes.
- [ ] WCAG AA contrast in light and dark (`checkPage`), dark is the designed theme from
      the mockups, not inverted.
- [ ] Touch targets ≥ 44 px on phone (`checkPage`).
- [ ] Vertical scrolling only: nothing scrolls sideways at 390 px (`checkPage`), not even
      with long food names, many places or many packets.
- [ ] Keyboard: every action reachable with Tab, visible focus, Enter/Space work, Escape
      closes sheets and returns focus; sheets trap focus while open.
- [ ] Screenshots match the mockups in all four versions (`review/screens.ts`), with
      differences either fixed or explained in the PR.

**Tests and checks**
- [ ] Tests for every feature, including the edge cases below that the PR touches.
- [ ] No test weakened: `git diff main -- '*test*' '*spec*' e2e/` shows no deleted
      assertions, loosened expectations, new `skip`/`only`/`fixme`, longer timeouts
      without reason, or excluded axe rules without a comment.
- [ ] `./check` passes, and its summary is pasted into the PR.
- [ ] Commits small, each builds; signed off by cabledrawer with `Assisted-by: Claude Code`.
- [ ] PR starts with "What cabledrawer needs to check"; `CHANGELOG.md` updated.

## Edge cases for 0.2

Stock
- [ ] Zero stock: a food with nothing left shows plainly (not "0 packets · about 0 g");
      using any more is refused or stops at zero.
- [ ] Using more than there is: stock stops at zero, never negative, in the API and on
      screen (and a later Undo restores the right amount).
- [ ] Oldest packet first: with packets of different use-bys, using some takes from the
      earliest use-by; packets with no use-by go after dated ones; fridge/cupboard
      before freezer.
- [ ] Several packets with different use-bys: shown grouped ("2 packs · 400 g"), tap
      shows each with its date; using across two packets empties the first, then takes
      from the second.
- [ ] Quick picks ¼ · ½ · ¾ · Full set what's left of an open packet, show "about 250 g",
      and "type grams instead" works.

Undo and history
- [ ] Partial undo after a packet was used up: undo an earlier "added 500 g" after 300 g
      was used; Undo puts back what it can, says so, and nothing goes below zero.
- [ ] Undo reverses just that change; later changes stay.
- [ ] Undo after 7 days is refused, in plain words (test with a fixed clock), at the
      7-day boundary in the household's time zone.
- [ ] Anyone in the household can undo anyone's change; the change log shows who.
- [ ] Ctrl+Z in a text box undoes the typing, never a pantry change; Ctrl+Z outside a
      text box undoes your own last change (not someone else's).

Merge
- [ ] Merge then undo: the merged-away food comes back exactly (name, other names,
      stock, sizes, "can use instead" links, recipe links).
- [ ] Merge of a count food into a weight food (and back): converted with the weight of
      one item, or asked once when it's missing.
- [ ] The merged food's name becomes an other name; search by it finds the result.

Units and rounding
- [ ] Cup size 240 ml with a US English browser, 250 ml otherwise; tablespoon 15 ml,
      teaspoon 5 ml; "Weight of 1 cup" shown in the household's size.
- [ ] Rounding: as-sold to the nearest ¼ ("1½ packets"); count foods to the nearest ½;
      "about" figures to 2 significant figures ("about 750 g", "about 1.5 L"); check
      values near the edges (0.12, 0.13, 0.875 packets; 1,234 g → "about 1,200 g";
      999 ml → "about 1 L"; tiny amounts don't show as "0").
- [ ] Household answers win over the bundled table; app updates don't overwrite them.

Use soon and dates (household time zone, Europe/London)
- [ ] Use soon = use-by today, tomorrow or the day after; not the day after that; not
      yesterday's (shown as past, not hidden).
- [ ] "Today" follows the household's local date, not UTC: test at 00:30 BST (still the
      previous day in UTC).
- [ ] Clock-change days: last Sunday of March (23-hour day) and last Sunday of October
      (25-hour day); "today/tomorrow/day after" stays right across them.
- [ ] To freezer: moves the packet to the Freezer with a use-by 3 months away, editable.

Screens
- [ ] Phone place tabs: every place shows; when they don't fit the last becomes "More";
      nothing scrolls sideways.
- [ ] Desktop: four default places as four columns at 1440 px beside the side panel, or
      a tidy 2×2.
- [ ] The ingredient editor is one component, reachable from the pantry and Ingredients;
      changes save as you go.
- [ ] Search by any name (other names too), filters All · Staples · Maybe the same.

## Where 0.2 differs from the mockups (lead's rulings, 17 Oct; the spec wins)

- Phone Pantry: tabs All · every place (Spice rack included; "More" when they don't
  fit) · Use soon; staples chips; a "Recent changes" section at the bottom, last 3 with
  Undo. No Running low / Staples chips on phone: running-low foods carry a "running
  low" label.
- Desktop Pantry: four place columns at 1440 px beside the side panel, else 2×2; all
  four places in the screenshots.
- Phone ingredient sheet: also has Running low at and Usual shop (with "+ Shop"), and
  Lives in lists every place.
- Phone header avatar stays as in 0.1.
- Hidden in 0.2: + List, Tubs, Recipes for these, "recipes that use them", Not in any
  recipe, the RECIPES column, USED IN.
- New colour tokens (`#7A2808`, `#FFFBF2`/`#4F3500`, `#2A2414`/`#F3D58C`) must meet AA in
  both themes.
- Seed data for the screenshots: `--prepare review/seed-pantry.ts`.

## Mockup notes (what builders tend to miss)

Colours come from `docs/mockups/*.dc.html`; most are already tokens in
`frontend/src/lib/styles/tokens.css`. Not yet tokens: phone Use-soon heading `#7A2808`;
"Maybe the same" row `#FFFBF2` / text `#4F3500` (dark `#2A2414` / `#F3D58C`).

- **Pantry, phone:** summary line above the title ("47 items · 6 tubs · 3 use soon"),
  round black 44 px "+" (white in dark). Place tabs are a pill segmented control
  (`#E6E9E5`, selected white, 36 px high) with All first. Use soon is a salmon card
  (`#FDE9E1`) with white Used/Binned pills. One white card holds the rows; grouped
  packets expand inline with "Oldest gets used first."; the open packet row has the
  ¼ · ½ · ¾ · Full picks (selected = green tint and border) and "About 250 g · type grams
  instead". Staples chips at the bottom.
- **Pantry, desktop:** header with "+ Add to pantry" (black pill; white in dark),
  "Find in pantry…" search, filter chips All · Use soon · 3 · Running low · Staples.
  Place columns are cards with a count ("9 items"), date chips on the right ("Today"
  orange, "Mon"). Side panel: Use soon (Used / Binned / To freezer), Staples chips with
  "+ Staple", Recent changes with green Undo links (bold verb first: "**Cooked** Sambar ·
  −200 g toor dal").
- **Ingredients, desktop:** breadcrumb "Recipes › Ingredients", subtitle "142 foods ·
  shared by your recipes, pantry and shopping list", big search, chips All · Staples ·
  Not in any recipe · Maybe the same (amber). Table columns INGREDIENT · COUNTED AS ·
  LIVES IN · RECIPES with "also: …" under names; selected row green tint. Editor panel
  on the right: "Saves as you go", OTHER NAMES chips, HOW IT'S SOLD box (Usual tag),
  Weight of 1 cup / Running low at, Lives in / Usual shop selects, Staple switch,
  CAN USE INSTEAD, Merge with another…, Undo last change.
- **Ingredients, phone:** the editor is a bottom sheet over the dimmed list, with
  "Done"; sale units as chips ("Packet = 500 g · usual"); "Saves as you go · Undo".
