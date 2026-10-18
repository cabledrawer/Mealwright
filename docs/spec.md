# Mealwright — product spec, PLANNING ONLY

Started 17 Oct 2026. cabledrawer's new from-scratch, self-hosted app, intended for public release. Planning finished 17 Oct; cabledrawer asked for a build plan for Claude Code (`BUILD-PLAN.md`). Not the Meal Prep Add-on for Mealie (that's separate). Will get its own folder/repo/Claude Code project when building starts. (File path kept as `kitchen-app-spec.md` from before the name was chosen.) Moved from the Home Lab project to the Mealwright project on 17 Oct.

**Mockups:** Design canvas "Mealwright mockups" (claude.ai artifact Ux4u2mYZtAfmagKn5EuxK1). Grid: every screen in four versions — phone + desktop side by side, light row on top, dark row beneath. All screens drawn (74 artboards): Today, Plan (week), Month, Shopping, Recipe(s), Pantry, Import review, "Cooked it" review, Cook mode, "Cook once, eat for…", Onboarding, Settings, Drafts (added 17 Oct). Design mockups only, not app code. Updated 17 Oct: Shopping has the offline bar and "Did you buy 2?" card (Tweak: Offline / Back online); Cook mode has "Show ingredients" and the experimental per-step switch; Settings has the daily update-check switch, About (version age, Check now, Report a problem); the chosen F1 logo (see `claude/mealwright-logo.md`; mint version on dark) is used in every desktop sidebar and in Settings → About.

## Planning order

Reordered 17 Oct — UI/usability now leads, cabledrawer's call.

1. Vision and audience — settled 17 Oct; Ethos settled 17 Oct — core, cabledrawer's words: "This is core!"
2. Version 1 scope — settled 17 Oct
3. Core decisions — settled 17 Oct: licence (AGPL-3.0), users/households, stack, name (Mealwright)
4. UX principles — in progress 17 Oct (core, alongside the ethos)
5. User flows and wireframes → clickable prototype, tested on a non-technical user before any code — all screens drawn 17 Oct (see Mockups); still being iterated via canvas comments. Next: link the screens into a clickable prototype and test it.
6. Data model (serves the screens, not the other way round; design the offline shopping-list sync carefully — biggest technical risk) — main decisions settled 17 Oct (sync, foods and units, stock, plan, recipes, history — see section 6); next: one combined list of everything stored, then step 7
7. Security and privacy (must enforce the ethos rules) — main decisions settled 17 Oct (see section 7)
8. Release plan — settled 17 Oct (see section 8) (include contributor policy: DCO vs CLA; verify every dependency's licence; audit for any outbound calls; formal trademark check on the name)
9. Roadmap and build versions — settled 17 Oct (see section 9); building starts with BUILD-PLAN.md

## Ethos — CORE (settled 17 Oct)

Every later decision is checked against this. It is also part of the pitch.

**No data collection. No location requests. Nothing leaves the user's own server and devices.**

Hard rules (no exceptions):

- No telemetry, analytics or usage stats — not even opt-in. No crash reporting services (no Sentry etc.); logs stay local.
- No location access, ever. The app never asks for the device's location. Country/units default from the browser/OS language setting or the user's choice — never geolocation.
- No phoning home: no licence checks, no "news" feed. **No automatic update checks unless the admin switches them on; never sends anything about the install** (rule changed by cabledrawer 17 Oct — see section 7, Updates). Users can also learn of updates via GitHub releases / their own tools (Diun, Renovate).
- No third-party assets at runtime: all fonts, icons, scripts bundled in the image — no CDNs, no Google Fonts.
- Recipe images are downloaded at import and stored locally, never hotlinked (hotlinking would ping the source site every time a recipe is viewed).
- Companion apps, if any: no analytics or ad SDKs; app store privacy label "Data not collected".
- No account with the developer — nothing to sign up for.

**Outbound connection rule (settled 17 Oct):** outbound connections happen only when the user triggers or configures them. Each one is clearly labelled and switched off until the user sets it up. The README gets a "Privacy" section listing every possible outbound connection. Settings → Privacy shows the same list, each with its own switch, under "Nothing leaves this server unless you switch it on". Known cases:

- Recipe URL import: the server fetches the page the user asked for (that site sees the server's IP). User-triggered.
- Update check (cabledrawer 17 Oct): "Check now" (admin click) or an optional daily check, off by default. One plain request to GitHub's public release list; GitHub sees the server's IP, nothing else is sent.
- Notifications (Apprise): go only to the services the user configures (their own ntfy/Gotify/email, or a public one they choose). Nothing configured = nothing sent.
- Single sign-on: talks only to the user's own identity provider.
- Barcode lookups (Open Food Facts; not in 1.0): opt-in, or use a downloaded offline copy of the OFF database (several GB).
- Phone push (not in 1.0): pushes carry no content ("You have an update"), or users route them through their own ntfy (UnifiedPush) instead.

## UX — CORE (in progress 17 Oct)

**Why:** cabledrawer "absolutely hates" Mealie's and Tandoor's UIs — in his words: clutter, too many clicks, utterly unintuitive, and they look bad. Specific failure: in the meal planner you can't simply drag a recipe to copy it, or turn it into leftovers. For an app competing with them, the UI is the product. Looks matter as much as flow — visual quality is a requirement, not polish.

**Visual references (cabledrawer 17 Oct):** Monzo (calm, white space, rounded cards, one main action per screen, big friendly numbers, plain warm language, small satisfying feedback) and the Notes app on iPad (content first, almost no chrome, sidebar + content split, quiet paper-like reading). Translation: Today/Plan/Shopping feel Monzo-like; recipe pages feel Notes-like; desktop/iPad use a sidebar, phones use bottom tabs.

**Platform emphasis (settled 17 Oct, cabledrawer's words: "Desktop and phone = but preference to phone - desktop isn't disadvantaged"):** desktop and phone are both full first-class targets for the v1 web app. Where a trade-off has to be made, phone wins — but never at the cost of a worse desktop experience. Desktop gets its own layouts (sidebar, wide week grid, three-pane recipes), not a stretched phone UI.

### Principles

1. **Phone and desktop both first-class; phone breaks ties.** Big tap targets everywhere; bottom tabs on phone; sidebar on desktop; each layout designed for its device.
2. **Today first.** Home answers: what are we eating, which tubs are left, what needs using up, what do we need to buy — not a recipe grid.
3. **Few taps for common actions.** Tick an item = 1 tap; add to list = 2 taps; log a batch cook in under a minute.
4. **Nothing to set up before it's useful.** Sensible defaults for units, shops, locations; setup optional, never a wall.
5. **Hide the advanced stuff.** Density, conversions, aisle order behind "more", only when needed.
6. **Undo, not "Are you sure?"** Actions happen instantly with an undo toast (Ctrl+Z on desktop).
7. **Plain words.** "Cupboard", "use soon", "tubs left" — never database words like "food items", "units", "labels", "groups".
8. **Fast and calm.** Instant (optimistic) updates; restrained visual style; one consistent component set / design system.
9. **Accessible.** WCAG AA, large text support, real dark mode.
10. **Tested on real people.** Clickable prototype before code, tried by a non-technical person doing real tasks.
11. **Direct manipulation** (from cabledrawer's planner complaint). Things on screen can be picked up and moved: drag to move, drag to copy, drag to spread as leftovers — with tap-based equivalents on phones where dragging is awkward. Every drag has undo.
12. **Use the screen** (cabledrawer 17 Oct). Dense-but-calm layouts on desktop: no wasted space, especially on the Plan screen.
13. **Dark mode toggle in plain sight** (cabledrawer 17 Oct — "pet peeve"). Three-way Auto · Light · Dark switch visible in the sidebar (single cycling button when collapsed; on phone, in the household/settings sheet) — never buried in settings. Choice saved per user. Dark mode is a properly designed theme, not inverted colours.
14. **One scroll direction, no chunky scrollbars** (cabledrawer 17 Oct). Every screen scrolls vertically only — never sideways at page level. On phones the header, bottom tabs and bottom action bar stay fixed and only the content between them scrolls (long recipes, lists); scrollbars are hidden/overlay like native apps. Desktop pages scroll vertically with thin scrollbars.
15. **Toggles are click-to-switch** (cabledrawer 17 Oct, from canvas comments). Anything that can be on/off (an ingredient in the "Cooked it" review, "remember for next time", meal slots, outside connections) is a real switch you click or tap, the same on phone and desktop — not a checkbox in one place and a button in another.
16. **Always show whether you're connected** (cabledrawer 17 Oct). The app shows plainly when it can't reach the server and when it's back, so nobody wonders whether their ticks were saved. Calm, not alarming: nothing extra while all is well; an "Offline — 3 changes waiting" bar when disconnected (above the bottom tabs on phone, at the foot of the sidebar on desktop, with a small dot when collapsed); a short "Back online — all saved" toast on reconnect. Offline changes still happen instantly (principle 8).

### Layout decisions from mockup feedback (cabledrawer 17 Oct)

- **Sidebar** collapses to icons only (logo, search, the five pages with count badges + tooltips, theme button, avatar; expand button). Toggle on every page, remembered per device; Plan starts collapsed (proposed). The avatar opens Settings.
- **Plan (desktop):** compact one-line header (title, week arrows + Today, Meals toggles, colour key, Week/Month); the week grid fills the height; recipe tray sits below the plan as a slim horizontal strip (collapsible), not a side column. Meal cards carry more info: fresh meals = photo strip, time, kcal; tubs = tub number, whose, kcal/protein; cook days = prep note ("Soak chickpeas Tue night") or "1 ingredient on the list". Row labels (Breakfast/Lunch/Snack/Dinner) all run the same direction (vertical) — cabledrawer flagged the inconsistency.
- **Meals (cabledrawer 17 Oct):**
  - A meal can hold several recipes/items (e.g. Dosa + Coconut chutney; a leftover tub + fresh Jeera rice). Meal shows "2 recipes · 590 kcal" and a + to add another; dropping a recipe on a filled meal adds it alongside.
  - Default slots: Breakfast, Lunch, Snack, Dinner — "default is what we build"; households can rename them to anything and add their own (e.g. "Tiffin", "Kids' lunchbox").
  - All slots are optional — header "Meals" toggles switch each row on/off per household.
  - Meal total = sum of its items' nutrition (per meal only; still no daily totals).
- **Month view (drawn 17 Oct):** reached with the Week | Month toggle on Plan. One colour per batch across the month; cook days marked (ring on phone, COOK tag on desktop). Phone: dot grid, tap a day to see its meals underneath. Desktop: meal chips in each cell ("+N more" when full), drag / Alt-drag to copy / drop on a later day for leftovers; side panel with "Batches this month" and "Empty days ahead" with a "Fill from freezer first" button.
- **Shopping:** staples check card has dismiss — "Got it" per staple and × to dismiss the whole check. Desktop shows a "Put away" panel (choose Fridge/Freezer/Cupboard for ticked items, Undo).
- **Sign in (drawn 17 Oct, screen 1):** logo, "Welcome back"; username, password with Show; "Remember this phone/computer" switch (30 days); Sign in; or "Sign in with <your SSO>" (Authentik in the mockups); "Forgot your password? Ask your household's admin to reset it" (no email reset — nothing leaves the server); "Your own server · nothing is sent anywhere else"; "First time here? Set up Mealwright" → Onboarding. When the admin turns password logins off, the page shows only the SSO button and "Trouble signing in? Ask your household's admin." (cabledrawer 17 Oct). Settings → Sign out returns here.
- **Recipes navigation (cabledrawer 17 Oct):** desktop sidebar shows Recipes as a tree (All recipes · Drafts · Ingredients, current page highlighted; breadcrumbs like "Recipes › Drafts"). Phone: the Recipes tab opens All recipes (search, Import a recipe, filters, list) with Drafts and Ingredients buttons at the top; a recipe page's back link returns to All recipes.
- **Canvas order (cabledrawer 17 Oct):** new screens are inserted where they belong logically, never just added at the end.
- **Recipe page:** "Keep screen awake" switch (browser Wake Lock, local only); turns on automatically with "Start cooking". Desktop Recipes uses a Notes-style three-pane layout (nav · recipe list · reading pane); "Import a recipe" is a big full-width button under the Recipes heading. Proposed: small "Show as: written · metric · cups" switch per recipe.
- **Cook mode (drawn 17 Oct):** big text, one step at a time, with the ingredients for that step; screen kept awake.
- **"Cooked it" review (drawn 17 Oct, revised from comments):** table of Ingredient · From · Before → After · Take · Use, fixed columns, equal row heights. Every ingredient has a Use switch — click to leave it out of the deduction or put it back. Count foods get Used/Left + a stepper. Items not in the pantry default to off, with "Bought some — used them" (replaces the old Skip button). The "ask once" unit question (e.g. jaggery weight) has a "Remember for next time" switch, on by default. Side panel: where the tubs go (fridge/freezer split).
- **"Cook once, eat for…" (drawn 17 Oct, revised from comments):** how many tubs, spread pattern (Lunches · Lunch & dinner · Dinners · **I'll pick**), who's eating, extra tubs to freezer, per-tub nutrition, and a preview of where the tubs land. The user chooses where tubs go: "+ Add a tub" on any empty meal, "+ Add a tub too" on a meal that already has food, ✕ to remove a tub, drag to move. The automatic patterns skip meals that already have food, but the user can still add a tub there.
- **Today (cabledrawer 17 Oct, drawn):** a "Did you cook Sambar?" card for yesterday's planned meal (Cooked it → review · Didn't · Move it); nothing changes in the pantry until you answer. **First-day empty state** (canvas tweak "firstDay"): "Your kitchen is ready" with three actions — Import a recipe · Add what's in your cupboards · Plan a meal.
- **Settings additions (cabledrawer 17 Oct, drawn):** Amounts → Tub use-by (fridge 3 days, freezer 3 months, change per tub); Household → Ask "Who's this?" switch (off; for a shared tablet); Outside connections → Your own network (allow list for your own servers); Sign-in → API tokens; Your data → Backups, History & undo, export password.
- **Sign-out warning (cabledrawer 17 Oct, drawn):** if changes haven't been sent yet, Sign out opens a warning; if everything is sent, Sign out just signs you out. The wording was settled for 0.3 (cabledrawer 17 Oct; section 6, "Offline shopping-list sync"): "3 changes haven't been sent yet. If you sign out now, they're lost." — Try sending now · Stay signed in · Sign out and lose them. It replaces the drawn "Wait and try again / Sign out anyway".
- **Shopping extra lists (cabledrawer 17 Oct, drawn):** list picker under the title — This week (main list, built from the plan) · Party on Saturday (extra list) · + New list. Ticked items on any list still go into the pantry.
- **Different pack when ticking (cabledrawer 17 Oct, drawn):** a ticked item has "Different pack?" → What did you buy? (2 × 200 g · 1 × 400 g · 1 × 1 kg · Other…) → pantry gets what was actually bought.
- **Tap any ingredient to edit:** rule stays in the spec; no extra mockup needed for now (cabledrawer 17 Oct).
- **Pantry:** Fridge / Freezer / Cupboard columns (tabs on phone); tubs live in the pantry in their batch colour; amounts shown the way they're sold ("1½ packets · about 750 g", "1½ bottles · about 1.5 L", eggs "9 left · bought as a dozen"); packets of the same food with different use-by dates are grouped ("2 packs · 400 g", tap to see each pack's date, oldest used first); an open pack is edited with quick picks ¼ · ½ · ¾ · Full (best guess, shows "about 250 g", "type grams instead" link) rather than a gram stepper (cabledrawer 17 Oct, drawn); filters All · Use soon · Running low · Staples; side panel with Use soon (Used / Binned / To freezer), Staples chips (tap when it runs out → list), Recent changes with Undo.
- **Import review:** as written → how Mealwright reads it → what's in your kitchen; counts of matched / to confirm / needs you / staple; "Same as <existing food>" vs "New food" to keep the food list clean; "Couldn't read the amount" → Treat as staple or type an amount; Save · Save & plan it; "Nothing is saved until you choose."
- **Plan (phone) long-press sheet:** header and per-tub nutrition centred; Whose tub? · Move to… · Copy to… · To freezer · Remove (back to tubs left).
- **Onboarding (drawn 17 Oct):** phone = one question per screen, 4 steps (Welcome · Amounts · Household · Shops), Skip always available. Desktop = one page, three cards side by side (Amounts · Household · Shops), then "Finish setup". **First step is creating the admin account** (name, username, password; no Skip on this step) — phone step 1 of 5, desktop card 1 "Your account" (cabledrawer 17 Oct, drawn). Household: each person "signs in" (Admin/Member) or "profile only — no login"; optional sign-in link. Shops: names only, no accounts or maps. Places at home default to Fridge · Freezer · Cupboard · Spice rack (renameable).
- **Settings (drawn 17 Oct):** sections in order — Appearance (Auto/Light/Dark, keep screen awake in Cook mode) · Amounts (show as, count foods, remembered sizes, use freezer stock last) · Household · Meal slots (switch, rename, drag to reorder, add; hidden slots keep their meals) · Shops & places (incl. staples check on new lists) · Notifications (ntfy/Apprise, off by default) · Privacy (statement + every outside connection with its own switch: recipe import from links, recipe photos) · Sign-in (SSO, sessions, API tokens, sign out) · Your data (backups daily, keep 7; history 12 months & undo 7 days; export everything with optional password; import from Mealie; change log) · About (version, AGPL-3.0, source code link). Desktop: collapsed sidebar + section list + two columns; phone: one grouped list.

### Meal planner interactions

- Drag a recipe from the recipe tray onto a day/meal slot → planned (or added to a meal that already has food).
- Drag a planned meal to another slot → on drop: Move (Enter) · Copy (Alt) · Leftovers here.
- "Cook once, eat for…" on any planned meal → pick portions (and people) → following slots fill as linked leftover tubs ("tub 2 of 4", same colour as the cook day), or the user picks the slots themselves. Drag a tub to rearrange; remove one → back to "tubs left" (or freezer).
- Phone: long-press a meal → Move to… · Copy to… · Leftovers on… with a day picker.
- Undo for every planner action.

### Visual system used in the mockups (draft, easy to change)

- **Light:** off-white ground, white rounded cards, near-black text, one green accent; saffron for tubs/leftovers; one colour per batch (solid on the cook day, light on its tubs).
- **Dark:** deep green-black ground, slightly lighter cards for layering, soft off-white text (not pure white); batch colours stay solid on cook days, tubs become dark tints with light text; accent green and "use soon" orange brightened for contrast; recipe reading pane a shade darker with slightly dimmed serif text.
- **Type:** Plus Jakarta Sans for UI, Newsreader serif for recipe text (fonts bundled in the real app).
- **Switches:** one switch component everywhere (green when on).

## 1. Vision and audience (settled)

**One-liner:** A self-hosted kitchen app that knows what's in your cupboards. You plan meals and batch cooks, it builds your shopping list from what's actually missing, keeps the pantry up to date as you shop and cook, and shows nutrition per serving where the recipe provides it.

**Audience:** broad, not just cabledrawer's household.

- **Meal prepper:** cooks in bulk once or twice a week, portions it out over several days. Needs batch planning (cook day → portions → days covered), scaling, leftover-portion tracking, nutrition per portion.
- **Pantry family:** 2–5 people, one or two plan, everyone adds to the list and shops. Needs accurate stock, a shared live shopping list, use-before-expiry, a simple UI.
- **Shared need:** import recipes from the web; a shopping list that's right, not padded with things already in stock.

**Positioning:** Mealie/Tandoor have good recipes but shallow inventory and cluttered, unintuitive UIs; Grocy has real stock but a warehouse-style UI and clunky recipes/planning. Mealwright puts pantry + meal prep at the centre, recipes in support, with a clean UI — and a strict privacy ethos.

**Nutrition (decided 17 Oct):** per serving: calories, protein, carbs, fat and fibre — only where the recipe supports it, i.e. taken from the recipe's own nutrition data (schema.org NutritionInformation on import, or the user typing it in). The app does not calculate nutrition from ingredients in v1, so no food nutrition database is needed. Batch portions re-divide the recipe total when portion count differs from the recipe's servings. Missing fields shown as unknown, not zero. Flag nutrition as possibly out of date if the ingredients are edited after import. No daily intake log or per-person targets.

- Open question: calculate from ingredients as a fallback later (post-v1)?

**Non-goals:**

- Not a hosted/SaaS service; self-hosted only
- Not a social/recipe-sharing site
- No grocery store or delivery integrations
- Not a diet/intake tracker or medical/clinical tool; numbers only, no guidance

## 2. Version 1 scope (settled 17 Oct)

Core loop: recipe → plan → shopping list → pantry → cook.

### v1.0 must have

**Recipes**

- Import from URL (schema.org) with ingredient parsing + review/fix screen before saving; images downloaded and stored locally
- Paste-text import (paste a recipe's text → same parser → review screen)
- Manual create/edit, photos, tags, search; scale servings; nutrition fields
- Keep screen awake while cooking; Cook mode (big text, step by step)

**Foods and units (cabledrawer 17 Oct)**

- Stored base: grams, millilitres, and counts (2 eggs, 1 onion) as a first-class unit — plus the recipe's original wording is always kept
- Onboarding choice (cabledrawer 17 Oct): "How do you like amounts shown?" → Grams & millilitres · Cups & spoons · As the recipe wrote it. Display only; changeable any time in settings; nothing lost either way. Proposed: per-recipe "Show as" switch. Imperial option within cups/spoons. Default suggestion from browser/OS language (never location).
- Under "as written", conversions still happen silently in the background for pantry and shopping maths.
- Notes for data model: cup size differs by country (US 240 ml vs metric 250 ml); g↔cups needs a per-food grams-per-cup value; counts can carry a per-item weight (1 onion ≈ 150 g) to bridge count ↔ grams
- One food master list shared by recipes, pantry and shopping

**Pantry (cabledrawer 17 Oct)**

- Stock with quantity, unit, location (fridge/freezer/cupboard; renameable, can add more e.g. spice rack)
- Expiry date optional — user enters it if they want; "use soon" list
- Staples: assumed in stock, not quantity-tracked; when a shopping list is generated, show the staples the plan uses as a "check you have these" section with one tap to add any to the list (and Got it / dismiss); user can mark/unmark any food as a staple
- Count foods (cabledrawer 17 Oct): things like onions, eggs, lemons are tracked by number in the pantry ("5 onions"), not converted to grams. A recipe that says "2 onions" takes 2; a recipe that gives grams for a count food is converted using the per-item weight and shown/rounded as a count (to the nearest half).
- "How much did you use / how much is left?" (cabledrawer 17 Oct): the user can always override the calculation — enter what they used ("used 1½ onions") or what's left ("3 left") — both in the "Cooked it" review and directly on any pantry item.

**Cooking — how deduction works (agreed 17 Oct)**

1. Recipe ingredients and pantry stock are linked by food and stored in a common unit (g / ml / count).
2. Scale to what was cooked: needed = recipe amount × portions cooked ÷ recipe servings.
3. Convert only when units differ: weight↔weight direct; volume↔volume fixed maths (1 tbsp = 15 ml); volume↔weight via a per-food grams-per-cup value; count↔weight via per-item weight. Conversion values from a bundled offline table of common foods (candidate source: public-domain USDA food weights — verify licence in the release step). Unknown conversion → ask once, remember for the household (cabledrawer decided 17 Oct; e.g. "About how much does 1 cup of toor dal weigh? Suggested: 200 g"). The question carries a "Remember for next time" switch (on by default); remembered sizes can be reviewed in Settings → Amounts.
4. Take from the pack that expires first; fridge/cupboard before freezer (freezer only if the user says).
5. "Cooked it" review shows every proposed deduction (e.g. "−200 g toor dal, 800 → 600 g"; "−2 onions, 5 → 3"), each adjustable as used-or-left and each with an on/off switch to leave it out, then one-tap confirm; Undo afterwards.
6. Staples never deducted. Stock never below zero → offer "add to list"; optional per-food "running low" level → same offer. Pack sizes supported ("1 packet = 500 g", part-used shows what's left).
7. Batch cooks deduct ingredients once on the cook day and create the tubs; eating a tub uses the tub, not the ingredients again.
8. Aim: "roughly right, easy to fix" — quick corrections in the pantry and Undo in Recent changes.

**Meal plan (cabledrawer 17 Oct)**

- Week view and month view
- Meal slots: default Breakfast, Lunch, Snack, Dinner — all optional; households can rename them to anything and add their own
- A meal can hold several recipes/items (recipes, tubs, plain foods)
- Batch cooks: cook day → portions → days covered, leftovers counting down; user can place tubs by hand ("I'll pick")
- Portion assignment to household members in v1.0 (cabledrawer 17 Oct, moved up from "later"): each batch portion can be assigned to a person ("Tue lunch: Wren's tub"), optional; shows that portion's nutrition. No per-person daily totals (that would be intake tracking, a non-goal).
- Drag to move / copy / spread as leftovers, with phone equivalents (see UX — CORE)

**Shopping list**

- Generated from plan − stock − staples (+ staples check section above); manual adds
- Multiple shops from v1.0 (cabledrawer 17 Oct): items split per shop, aisle/category order per shop, preferred shop per food
- Shared live between family members; works offline on the phone
- Ticking an item moves it into the pantry; user can specify location if needed (otherwise food's default location)

**Expiry from v1.0 (cabledrawer 17 Oct):** expiry dates + use-soon list + expiry notifications via Apprise (see stack). Optional defrost reminder (evening before a freezer tub is planned).

**Users:** several users per household, Admin/Member roles, API tokens, single sign-on (OIDC) from v1.0 (cabledrawer 17 Oct) alongside local logins

**Onboarding:** first-run setup asks only what matters (units display choice above; household members; optional shops) — everything else defaults (principle 4). Skippable. See Layout decisions for the drawn version.

- **Starter ingredient packs (cabledrawer 18 Oct):** Mealwright ships with optional packs of common ingredients so nobody has to type the basics: **Everyday basics**, **South Indian vegetarian** (with Tamil names as other names), **Household** (staples marked "Don't count it") and **Baking**. Ingredients only, no recipes. A pack adds ingredients to the Ingredients list, each with how it's counted, its aisle, usual UK packet sizes and other names; it never adds pantry stock or list items. Before adding, the person sees the pack's list and can untick any item. Ingredients already there (same name or other name) are skipped, never duplicated, and the whole addition has one Undo. Offered as an optional onboarding step ("Start with common ingredients?") and any time from an "Add a starter pack" button on Ingredients. The packs are bundled in the app (nothing is downloaded) and are written for Mealwright, so they can be shared under the project's licence. The exact items, packet sizes and Tamil names are agreed with cabledrawer before 0.8's first code pull request.

**Moving in:** Mealie importer

**Platform:** single Docker container, SQLite, migrations from day one, data export/backup, web app equally good on desktop and phone (phone breaks ties), installable PWA, light/dark/auto theme with a visible toggle

### After 1.0

Plans after 1.0 are kept outside the repo.

### Not in v1

- More than one household per install (data model ready)
- Languages other than English (UI strings translation-ready)
- Nutrition calculated from ingredients
- Daily intake logging
- Native mobile apps
- Store/delivery integrations

## 3. Core decisions (settled 17 Oct)

**Name (decided 17 Oct):** Mealwright — "maker of meals" (like playwright/wheelwright). Repo/image slug `mealwright` (e.g. `ghcr.io/<owner>/mealwright`). Quick web search 17 Oct found no existing app or project with the name. Rejected: Larder (direct clash — "Larder: Family Meal Planner" on iOS, Hovenly Larder, Empty Larder, others), Dispensa (open-source pantry app on F-Droid), Tiffin (crowded with tiffin delivery services), Cellarer (reads as wine). Runner-up: Stillroom. Before publishing: formal trademark search (UK IPO, USPTO, EUIPO) and app store name check; consider registering the GitHub org/handle early. Logo: the chosen F1 mark (square tub with saffron lid and tab, M cut out) — see `claude/mealwright-logo.md` and `brand/` in the project. The blue pot in the project folder's `logo` folder is an older logo, not used.

**Licence (decided 17 Oct):** AGPL-3.0. Reasons: matches Mealie/Tandoor/Immich; stops a closed hosted fork; cabledrawer as owner is not bound by it; easy to loosen later while he's sole author. Every dependency must be AGPL-compatible (MIT, BSD, Apache-2.0, LGPL, GPL-3.0 fine; check anything else). Contributor policy (DCO vs CLA) to decide in the release plan — a CLA keeps the right to relicense once others contribute.

**Users and households (decided 17 Oct):**

- One household per install; everything shared within it (recipes, pantry, plan, lists); per-user settings only (display units, notifications, theme, sidebar collapsed)
- Two roles only: Admin and Member (cabledrawer 17 Oct; no Shopper role)
- Household members are separate from login accounts: a member profile (name, optional colour/avatar) can exist without a login — kids, a baby, or two people sharing one "family" login — and is what batch portions are assigned to. A login account can optionally be linked to a member profile.
- OIDC: optional auto-create on first login, IdP group → role mapping, option to turn off password logins
- Shared logins supported (no per-person audit trail when shared)

**Stack (decided 17 Oct):**

- Backend: Python + FastAPI
- Database: SQLAlchemy + Alembic; SQLite (v1.0); no Postgres in 1.0
- Frontend: SvelteKit, static build served by the backend; installable PWA; all assets bundled (no CDNs)
- Live updates: Server-Sent Events
- Offline: shopping list (and recently viewed recipes) cached on device; changes queued and synced on reconnect; tick-off is idempotent
- Background jobs: in-process scheduler (APScheduler) — no Redis/second container
- Notifications: Apprise in v1.0 (ntfy, Gotify, email, Discord, Telegram…)
- Auth: Authlib for OIDC (with PKCE + refresh tokens), Argon2 password hashing, secure session cookies
- Images: on a mounted volume, resized on upload
- Packaging: one container (API + frontend), multi-arch amd64/arm64, GHCR
- API-first rules (for future phone apps, cabledrawer 17 Oct): the web app uses only the public, documented, versioned API (`/api/v1`, OpenAPI generated by FastAPI) — no private endpoints; token auth suitable for mobile; the offline/sync protocol is part of the API, not web-app-only logic; server design leaves room for a push relay later.
- Licences of all the above believed MIT/BSD — verify each in the release-plan step. Also check no dependency phones home (e.g. disable any library telemetry).

## 6. Data model (main decisions settled 17 Oct)

### Offline shopping-list sync (decided 17 Oct)

**Why it is the risk:** ticking an item also adds it to the pantry, so two people shopping offline could double the stock. The list itself is easy; the pantry side effect is the hard part.

**How it works:** the phone keeps a queue of actions (tick, untick, add, change amount, delete, put away). Each action gets its own ID made on the phone. On reconnect the phone sends the queue and the server works through it in the order it receives it (a server counter, not device clocks). An action sent twice (same ID) is ignored. Only the server changes pantry stock. The protocol is part of the public `/api/v1`, so future phone apps use it too. Chosen over sending and replacing the whole list (loses the other person's edits) and over shared-editing libraries / CRDTs (weak Python server support, and the pantry rules still need the server).

**Rules:**

- **A tick sticks.** If anyone ticked an item, it's bought; an untick counts only if it comes after the tick.
- **Both ticked the same item offline (cabledrawer 17 Oct):** counts as two purchases — both go into the pantry — and once the phones reconnect the app asks plainly: "You and Wren both ticked toor dal. Did you buy 2?" → Yes, 2 · Just 1. Shown as a card on Shopping (and Today), not a blocking pop-up; "Just 1" removes the extra, with Undo.
- **A hand edit beats the app's own sums.** When the plan changes, the list updates amounts it worked out itself, never one a person typed. Plan-made items are keyed by food + shop so regenerating updates them instead of duplicating.
- **Deleted stays deleted.** Deletes leave a hidden marker (tombstone) so an old offline phone can't bring an item back.
- **Put away offline (cabledrawer 17 Oct):** choosing Fridge/Freezer/Cupboard while offline is queued with the tick.
- **No conflict pop-ups.** Other clashes show as a quiet note ("Wren ticked this too") with Undo.
- **How long offline (cabledrawer 17 Oct):** plan for a weekend away (about 3 days). The phone keeps the shopping list, recently viewed recipes and the queue for that long; older queues are still applied, never thrown away.
- **Connection status:** see UX principle 16.
- **Offline wording grows with PR 6 (cabledrawer 18 Oct):** until the offline queue arrives (0.3 PR 6), changes made offline aren't kept on the phone, so the wording says only what is true. Shopping's subtitle while offline says "12 to buy · offline", and the toast on reconnecting says "Back online". PR 6 adds ", saving on this phone" ("… on this computer" on desktop) and "— all saved" once they are true. Extra lists say just "Extra list · 5 · offline" while offline, in PR 5 and after PR 6 alike: only the main list's subtitle grows (cabledrawer 18 Oct).
- **Opening the app offline (cabledrawer 18 Oct, PR 6):** the app opens as the person last signed in on that phone, and Shopping works from the phone's copy. Pantry, Ingredients and Settings stay online-only in 0.3; offline they show a short note, "You're offline. Pantry needs your Mealwright server — your shopping list works offline." (naming the screen: Ingredients, Settings), with a Shopping button. The bar still shows Offline. Settings keeps two parts offline under that note: Sign out, and the theme switch, which is saved on the device so it works without the server (cabledrawer 18 Oct: "Keep it visible"). The "+ Add to pantry" button also stays visible offline, as a normal button: tapping it doesn't open the sheet, it shows "Adding to the pantry needs your Mealwright server. Try again when you're back online." (cabledrawer 18 Oct).
- **A phone that has never loaded the list, opened offline (cabledrawer 18 Oct, PR 6):** Shopping says "Your shopping list isn't on this phone yet. It'll be here after you've opened it once while connected."
- **"This phone" or "this computer" (cabledrawer 18 Oct, PR 6):** chosen by layout. With the bottom tabs the app says "this phone"; with the sidebar it says "this computer", so a tablet held wide says "computer".

**What this adds to the data model:** list items with phone-made IDs, source (from plan / typed by hand), "hand-edited" flag, ticked by / when, put-away location, deleted marker, version number; a sync log of applied actions (action ID, user, device, type, server order, applied time) for repeat-detection and Undo; a "both ticked" question record until answered.

**Decided for 0.3 (cabledrawer 17 Oct):**

- **Same login on two phones:** if one login ticks the same item on two phones while offline, the app still asks "Did you buy 2?", worded "This was ticked on two phones".
- **Sign-in runs out while offline** (not a sign-out): the waiting changes stay on the phone and are sent once the same login signs back in. If a different login signs in, the sign-out warning comes first.
- **Ticking into the pantry:** the item goes to the food's usual place, or Cupboard if it has none, with no use-by unless one is chosen.
- **Items that aren't food** (kitchen roll, soap): every list item is still a food. A non-food item becomes a food with the Staple switch on, so ticking it never adds pantry stock.
- **Aisles:** each food has an optional Aisle (under "more" in the editor). Default aisles: Veg & fruit · Meat & fish · Dairy · Bakery · Dry goods · Tins & jars · Spices · Frozen · Drinks · Household · Other (cabledrawer added Meat & fish, Tins & jars and Drinks: Mealwright is for the public). Each shop orders the aisles by dragging (Shops & places, 0.8); until then shops use the default order. Aisle headings on Shopping use these names, not the older ones in the mockups ("Fruit & veg", "Rice & grains"), and the Aisle field arrives in 0.3.
- **What the phone keeps offline:** in 0.3 the app itself and the shopping lists; recently viewed recipes from 0.4.
- **App updates:** a new version installs quietly the next time the app is opened, never mid-shop, and waiting changes are always sent first. Docs note that offline needs HTTPS, and that iPhone Safari can clear a web page's offline data after 7 days without use (adding it to the Home Screen helps).
- **No new libraries needed:** Server-Sent Events are built into FastAPI; SvelteKit's own service worker support is used. `idb` (ISC, very small) is approved for the IndexedDB queue (cabledrawer 17 Oct); the pull request that builds the queue pins an exact version released at least two weeks earlier. Well-tested code matters more than one package fewer.
- **A tick against a delete** (both offline): the tick still counts as bought, so the pantry gets the stock, and the item stays off the list. The person who ticked sees a quiet note, "Wren had removed this. Your tick still went into the pantry", with Undo.
- **Unticking after a tick** takes the stock back out the way Undo does: if some has been used since, only what's left comes out, never below zero.
- **Both add the same ingredient** offline (same list, same shop, neither ticked): it stays one line, keeping the bigger amount, with a quiet note ("Wren added milk too") and Undo. The "same list, same shop, neither ticked" wording is confirmed (cabledrawer 18 Oct).
- **Both change the same item's amount** offline: the change the server receives last wins, with a quiet note.
- **"Did you buy 2?"** shows to both people who ticked. The first answer settles it and the card disappears for the other person. Until 0.6 the card shows on Shopping only; Today gets it with 0.6.
- **Ticked items** fold into an "In the trolley · N" row at the end of each shop. "Clear ticked" removes them, with Undo.
- **Ingredients with no usual shop** go in an "Any shop" section, shown last.
- **Typing something that isn't an ingredient yet** makes it a new ingredient, asking "How do you count it?". A blank amount means one of its usual size, or 1 if it's counted in items.
- **Extra lists** can be renamed and removed, with Undo. The main list can be renamed but never removed.
- **Main list subtitle:** "12 to buy · synced with Wren", or "12 to buy · saved" in a one-person household.
- **Signing out with unsent changes:** "3 changes haven't been sent yet. If you sign out now, they're lost." Buttons: Try sending now · Stay signed in · Sign out and lose them. This is the one justified exception to "Undo, not Are you sure?" (UX principle 6): changes that were never sent can't be undone.
- **An item with no amount** (weighed or measured, with no usual size): ticking it puts nothing into the pantry, and the ticked row offers "How much?" for one more tap if you want it counted. No prompt (cabledrawer 18 Oct).
- **"How do you count it?"** is asked once, when a typed name is a brand-new ingredient: By weight · By volume · One by one · Don't count it (a staple, for kitchen roll and soap). When connected to your Mealwright server, the bundled table's guess is picked first (the table is on the server; nothing is looked up on the internet) (cabledrawer 18 Oct).
- **Put away on two phones** with different places: the one the server receives last wins, with a quiet note ("Wren put coriander in the Freezer") and Undo (cabledrawer 18 Oct).
- **A different login on a phone holding someone's unsent changes:** the sign-in page says "Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." If someone else signs in anyway: "Wren's 3 changes haven't been sent yet. If you carry on, they're lost." Buttons: Sign in as Wren instead · Carry on and lose them. Carrying on wipes the phone's offline copy, as signing out does (cabledrawer 18 Oct).
- **Starting aisles:** ingredients from the bundled table get a starting aisle from their USDA food category, with each category mapped to one of the default aisle names above; the rest start as Other. The aisle stays editable in the ingredient editor (cabledrawer 18 Oct).
- **A removed list is hidden, not frozen:** changes queued for it on a phone that was offline still apply inside it, and ticks still go into the pantry. That person gets a quiet note ("Tess had removed Party on Saturday. Your changes are kept with it. Your ticks still went into the pantry.") with Undo, which brings the list back (cabledrawer 18 Oct).
- **Changing an ingredient's usual shop** moves its unticked items from the old usual shop (or Any shop) to the new one; items someone put under a particular shop on purpose stay (cabledrawer 18 Oct).
- **Adding something that's already on the list:** online, the add box says "Milk is already on the list · 2 L" and changes that line. When the person could already see the line, or it was added on the same phone, the amounts add up (2 L + 1 L = 3 L), with no note. "Keep the bigger amount" is only for two people adding the same thing without seeing each other's line (cabledrawer 18 Oct).
- **A note or card for an item that's no longer on the list** shows in a faint row where the item was, in its shop ("Paneer · removed by Wren"), until the note is dismissed or the card answered (cabledrawer 18 Oct).
- **A tick arriving after "Did you buy 2?" was answered** opens a fresh card covering every purchase still counted ("Did you buy 3?" after Yes, 2; "Did you buy 2?" again after Just 1) (cabledrawer 18 Oct).
- **A tick on a removed ingredient whose name is now taken** goes into the live ingredient with that name, not a second one (cabledrawer 18 Oct).
- **A phone ahead of the server** (for example after the server was restored from a backup) gets a fresh copy of the lists, not a stale one (cabledrawer 18 Oct).
- **Undo of "Just 1"** joins a newer open "Did you buy 2?" card if there is one; **Undo of "Yes, 2"** with fewer than 2 purchases still ticked does nothing (cabledrawer 18 Oct).
- **Merged-away list items** are tidied away 12 months after they were added (cabledrawer 18 Oct).
- **How an amount reads with its ingredient:** "1 bunch of Coriander" (cabledrawer 18 Oct).
- **Shopping opens on All**, the view with every shop under its own heading, so a new item is never hidden in another shop's tab (cabledrawer 18 Oct).
- **Remove from list** sits in the amount editor (tap the amount on a line) (cabledrawer 18 Oct).
- **Packet sizes travel with a new ingredient** made from the add box ("jar = 250 g", chosen in "How do you count it?"), so it works offline too (cabledrawer 18 Oct).
- **Undo of a pack change after some was used** works like 0.2's Undo for now: it puts back what it can and says so (cabledrawer 18 Oct).
- **The same name counted differently** (a removed ingredient's name now belongs to one counted another way): the amount is never carried over, and a quiet note says so (notes N8 and N9 in the sync protocol) (cabledrawer 18 Oct).

### Foods and units (decided 17 Oct)

**Shape:**

- **One food = one thing you buy and cook with** (toor dal, onions, milk). Each food has: name, other names, how the pantry counts it (weight / volume / count / staple), usual place at home, preferred shop, and optional extras (pack size, weight of one item, weight of a cup, running-low level).
- **Stored in grams, millilitres or counts** behind the scenes; the recipe's own wording is always kept.
- **Conversions in two layers:** a built-in table shipped with the app, with the household's own answers on top. Household answers always win; app updates never overwrite them.
- **Every recipe ingredient points to a food;** anything the app can't match goes to the Import review screen.

**Close cousins (cabledrawer 17 Oct):** the user decides whether two things are one food or two (e.g. "onion" and "red onion"), using the existing "Same as <food>" / "New food" choice, and can merge or split foods later. v1.0 also has an optional **"Can use instead"** link between foods (red onion can stand in for onion). With a link set:

- The shopping list counts stock of the stand-in. It doesn't add onions while you have red onions, and shows a quiet note: "Using red onions you have".
- The "Cooked it" review takes from the stand-in and shows it on that row, with its Use switch as usual.
- The link goes one way unless the user sets it both ways.

**Brands (cabledrawer 17 Oct):** no brand tracking. A brand only appears if the user types it as part of a food's name (e.g. "MDH sambar masala"), and then it is simply its own food. There is no separate brand field. Pack size stays.

**Other names (cabledrawer 17 Oct):** in v1 households add their own other names for a food (e.g. thuvaram paruppu, arhar dal → toor dal). Import matching uses them. Built-in name profiles for ingredients (e.g. Tamil / Hindi name sets) are not in 1.0.

**Ingredients screen (cabledrawer 17 Oct):** not its own top-level section. It sits under Recipes — the sidebar shows a tree: Recipes → All recipes · Drafts · Ingredients; on phone the All recipes screen has Drafts and Ingredients buttons at the top. The screen lists every food (search by any name; filters All · Staples · Not in any recipe · Maybe the same), has a **New ingredient** button (cabledrawer 17 Oct, 0.3), and has an editor: name, other names, how it's sold (sale units), weight of a cup, running-low level, usual place and shop, staple switch, "Can use instead", the recipes that use it, Merge with another, Undo. Changes save as you go. **Tap any ingredient anywhere** (a recipe's ingredient list, a pantry item, a shopping-list item, Import review) to open the same editor.

**Removing an ingredient (cabledrawer 17 Oct):** the Ingredients editor has a **"Remove from Ingredients"** button, which deletes that food's record entirely. It appears only when nothing depends on the food: none in the pantry, not on any shopping list and (from 0.4) not used in any recipe. Like every change it can be undone for 7 days. **Words (cabledrawer 17 Oct):** on screen it's always "ingredient", because the screen is called Ingredients; "food" is the internal word in the data model and code and is never shown. Inside a recipe (0.4) the action is "Take out of this recipe", never "Remove", so the two can't be confused. **After the 7 days (cabledrawer 17 Oct):** a removed ingredient is then deleted for good, with its other names, sizes, links, remembered answers and its monthly history totals. Recent changes keep their sentences, with the name, until those changes are summarised at 12 months. An Undo that would put stock back into a removed ingredient brings the ingredient back and says so.

**Data model additions:** food "can use instead" links (food → stand-in food, one-way); food merge history (so a merge can be undone and old recipe links still resolve).

**Decided for 0.2 (cabledrawer 17 Oct):**

- **Conversion table source:** USDA FoodData Central, SR Legacy (April 2018, final release): public domain under CC0 1.0. USDA asks for credit, given in `docs/` and Settings → About. A hand-picked subset of about 200 common foods is bundled as a small CSV, rebuilt by a script in the repo from the USDA file. Foods it doesn't cover (many Indian ingredients) are asked once. No values are copied from sources with unclear licences. **Checked by hand (cabledrawer 17 Oct):** the pull request that adds the table gives it its own section in "What cabledrawer needs to check": where the data came from, the licence, the credit wording, and 10 sample foods with their cup weights, so he can check them in his own kitchen. Rejected: Open Food Facts (ODbL), FAO density tables (licence unclear).
- **Cup size:** each food's weight per millilitre is stored; "Weight of 1 cup" is shown in the household's cup size: 240 ml when the browser language is US English, otherwise 250 ml (changeable in Settings, 0.8). Tablespoon 15 ml, teaspoon 5 ml.
- **Rounding:** amounts as sold to the nearest ¼ ("1½ packets"); count foods to the nearest ½; "about" figures to 2 significant figures ("about 750 g", "about 1.5 L"). A food sold in more than one size is shown in the one marked Usual.
- **Merge:** the merged-away food's name becomes an other name of the food it's merged into; its stock, sizes and "Can use instead" links move across (count ↔ weight via the weight of one item, or asked once). Undo within 7 days restores everything exactly. After that, "split" turns one of the other names back into its own food; old links still resolve through the merge history.
- **"Maybe the same":** simple offline matching (same name ignoring case, plurals and brackets, or a name matching another food's other names), each with a "Not the same" button. No fuzzy-matching library.
- **Shops before Settings exists:** the editor's "Usual shop" has a "+ Shop" chip that adds a shop by name. The four default places are created automatically; renaming places comes in Settings (0.8).
- **Removing an ingredient:** decided by cabledrawer 17 Oct; see "Removing an ingredient" above.

### Stock (decided 17 Oct)

**Measure stock the way it's sold (cabledrawer 17 Oct).** Each food has a pantry unit that matches how you buy it, and the app does the maths behind the scenes:

- Toor dal is sold in 500 g packets, so the pantry shows packets ("1½ packets · about 750 g").
- Bread is counted in slices.
- Eggs are counted one by one. Buying "a dozen" adds 12.
- A food can have more than one way it's sold ("packet = 500 g", "dozen = 12", "loaf = 20 slices"). Each one converts into the food's base amount (grams, millilitres or count).

**Part-used packets (cabledrawer 17 Oct):** after cooking, the app suggests its best estimate of what's left ("about ½ packet · 250 g"). The user can correct it either in grams or as a fraction of the packet. Quick picks are ¼ · ½ · ¾ · full, or you type an amount.

**Marks in the opened pantry row (cabledrawer 18 Oct, from the 0.2.0 hand test):** for a food with a single packet, the ¼ · ½ · ¾ · Full marks show in the opened row, next to the "Used some" box, so they are easy to find. With several packets the row stays as it is, and the marks stay in each packet's menu. Tapping a mark saves at once, with Undo. Under the marks, "About 250 g left · type it instead" opens the packet's "What's left" box; it says "left" so it can't be confused with "Used some" beside it (cabledrawer 18 Oct).

**Tubs (cabledrawer 17 Oct):** counted in quarters. Eating from a tub uses one whole tub by default; a ¼-step stepper lets you say "used ½". Whatever is left stays where it is ("¾ tub") with its batch colour.

**Packets with different use-by dates (cabledrawer 17 Oct):** each packet is kept separately behind the scenes, so the one that goes off first is used first. The pantry shows them together ("2 packets · 1 kg"); tap to see each packet and its date.

**Slices in a loaf (cabledrawer 17 Oct):** the app asks once, the first time bread is bought ("About how many slices? Suggested: 20"), and remembers the answer for the household, using the same "ask once" pattern as cup weights.

**Different pack size on the day (cabledrawer 17 Oct):** when ticking an item off, the user can change the pack size ("1 × 1 kg" instead of 2 × 500 g). No setup is needed, and the new size is added to the food's sale units.

**Data model:** food sale units (name, amount in base unit — e.g. packet = 500 g, dozen = 12, loaf = 20 slices); stock lots keep the base amount plus the sale unit they were bought in, for display; tub amount stored in quarters (0.25 steps).

**Decided for 0.2 (cabledrawer 17 Oct):**

- **Use soon:** use-by today, tomorrow or the day after (2 days ahead). Not 3, because a fridge tub's default life is 3 days and would land on Use soon the day it's made. Becomes a household setting in 0.8.
- **"Today" is the household's local time** (cabledrawer 17 Oct: "today" for use-by dates and the daily jobs follow the household's local time, not UTC; he's in the UK, GMT/BST). Use-by dates, Use soon and the daily jobs all follow the household's time zone, never UTC. How (proposed by Claude Code, agreed by cabledrawer 17 Oct, with his conditions): the household stores its time zone as a household setting, taken from the admin's browser or OS setting (never location), so no `TZ` setting is needed in `compose.yaml`. It is **captured once** and **never changed silently** afterwards: the server accepts the browser's time zone only while the household has none, so an admin opening the app from another time zone changes nothing. It's shown, and changed only on purpose, in Settings (0.8). **Existing installs** (set up before 0.2) have none yet: the first time an admin opens the app after updating to 0.2, their browser's time zone is stored, once. Until then, dates follow UTC.
- **To freezer:** moves the packet to the Freezer with a new use-by 3 months away (the tub default); the date can be edited.
- **Places on screen:** phone tabs show every place (Fridge, Freezer, Cupboard, Spice rack and any added); if they don't fit, the last tab becomes "More", so nothing scrolls sideways. Desktop shows all four default places as four columns at 1440 px if they fit beside the side panel, otherwise a tidy 2×2, whichever looks right in the screenshots. **Phone tab order (cabledrawer 17 Oct):** All · Fridge · Freezer · Cupboard · More; Use soon sits under More with any extra places, since the All tab already shows the Use soon card.
- **"+ Add to pantry" sheet (no mockup yet):** pick or type a food; amount as sold (1 packet, 2 packets…) or typed grams; place filled in from the food's usual place; optional use-by (none · today · +3 days · +1 week · pick a date; "Today" added by cabledrawer 18 Oct). Screenshots go in the PR; cabledrawer adds it to the mockups canvas afterwards.
- **Parts that depend on later milestones are hidden until they work:** "+ List" and "tap a staple when it runs out" (0.3, shopping list); tubs (0.6); "Used in N recipes", "Not in any recipe" and "Recipes for these" (0.4).
- **Tap a staple when it runs out (cabledrawer 18 Oct, 0.3):** tapping a Staples chip adds that staple to the main shopping list, with the toast "Oil added to the shopping list · Undo", and the chip shows a small tick while it's on the list. Tapping a ticked chip doesn't remove it or add another; the toast says "Oil is already on the shopping list." The tap goes through the same add action and waiting list as Shopping, so it works offline. Screen readers hear "Add Oil to the shopping list" or "Oil, on the shopping list". An "Edit staples" link after the chips opens Ingredients with the Staples filter, where a staple opens the editor as usual. No long-press.
- **Live updates:** in 0.2 the Pantry refreshes when you return to the tab; Server-Sent Events come in 0.3.

### Plan and batch cooks (decided 17 Oct)

The shape is in "Data model notes" below: each meal sits on a date and slot and holds one or more items; a batch cook creates tubs. Decided on top of that:

- **Meals nobody cooked (cabledrawer 17 Oct):** if a planned meal's day passes without "Cooked it", the next morning Today asks gently: "Did you cook Sambar yesterday?" → Cooked it · Didn't · Move it. Nothing changes in the pantry until it's answered.
- **Tub use-by (cabledrawer 17 Oct):** every tub gets a use-by date when it's made. The defaults are 3 days in the fridge and 3 months in the freezer. The user can edit the defaults per household and the date on any tub. Tubs near their date show on "Use soon".
- **Recipe edited after planning (cabledrawer 17 Oct):** future meals follow the latest version of the recipe. Cooked meals keep a record of what was actually made (recipe version, amounts, deductions), so history and pantry changes stay correct.

**Data model:** meal status (planned / cooked / didn't / moved); a cooked record per meal or batch (a snapshot of the recipe as cooked plus its stock changes); tub use-by date; household defaults for fridge / freezer tub life.

### Recipes (decided 17 Oct)

- **Recipes inside recipes, v1.0 (cabledrawer 17 Oct):** a recipe can list another recipe as an ingredient (sambar → homemade sambar powder; dosa → dosa batter). Making the inner recipe puts it into the pantry like any food ("Dosa batter · 1.5 litres · fridge") and the outer recipe takes from it. If there's none, the app offers "Make batter first?". The shopping list works through the inner recipe's ingredients only when there's not enough of it made.
- **Where a recipe came from (cabledrawer 17 Oct):** imported recipes always keep the web address and import date, and show "From: <site>" on the recipe page, crediting the original author. Opening the link is the user's own click in their browser; the server never re-contacts the site. Typed-in recipes have an optional "Source" note ("Amma's", a book title).

**Data model:** recipe ingredient can point to a food or to a recipe; a recipe that can be made ahead links to its own pantry food (homemade); recipe source URL, import date, source note. Guard against loops (a recipe can't contain itself, directly or indirectly).

### History and undo (decided 17 Oct)

- **How long it's kept (cabledrawer 17 Oct):** by default the full history of pantry changes (cooked, bought, binned, moved, adjusted) is kept for 12 months, then thinned to monthly totals. Undo works on the last 7 days. Both numbers are defaults the household can change in Settings → Your data.
- **Who did it (cabledrawer 17 Oct):** each change records the login that made it ("Wren ticked toor dal"). On a shared login it shows the login's name ("Family"). By default nothing more is tracked, to keep things simple. A household can switch on an optional "Who's this?" picker for shared logins.

**Data model:** change log entries (type, food/lot, amounts before → after, login, optional member, time, undo link); household settings for history length, undo window and the "Who's this?" picker; monthly summary rows for thinned history.

**Decided for 0.2 (cabledrawer 17 Oct):**

- **Undo reverses just that change**; later changes stay. If the packet has been used up since, Undo puts back what it can and says so. Stock never goes below zero.
- **Anyone in the household** can undo anyone's change within the undo window (7 days).
- **Ctrl+Z on desktop** undoes your own last change. When the cursor is in a text box, Ctrl+Z undoes the typing as normal, never a pantry change.
- **Thinning history** runs as a daily job with APScheduler (approved 17 Oct, MIT), in the household's local time.
- **Recent changes on Ingredients (cabledrawer 18 Oct, 0.3):** Ingredients gets its own Recent changes, a side panel on desktop and a "Recent changes" button on the phone, listing ingredient changes: new ingredients (including "+ Staple"), Staple on/off, removals, merges and edits, each with Undo for 7 days. Pantry's Recent changes stays stock-only.

### Everything Mealwright stores (combined list, 17 Oct — draft)

Plain-language list of every kind of record, grouped. Every record belongs to the household (household_id), so more than one household per install stays possible later.

**People and access**

- Household: name, settings (meal slots, places, shops, staples check, freezer last, tub life, history length, undo window, "Who's this?" picker, outside-connection switches, notification targets).
- Member profile: name, colour/avatar; can exist without a login.
- Login: username or SSO identity, role (Admin/Member), optional link to a member, personal settings (units display, theme, sidebar, keep screen awake).
- Sessions and API tokens (per device, can be signed out).
- Devices (for offline sync): phone-made ID, last seen.

**Foods and stock**

- Food: name, other names, pantry unit, usual place, preferred shop, staple flag, running-low level, weight of one item, weight of a cup, household's ask-once answers.
- Sale units: packet = 500 g, dozen = 12, loaf = 20 slices.
- "Can use instead" links; merge history.
- Stock lot (each packet): food, amount, sale unit, place, use-by, added date.
- Places (Fridge, Freezer, Cupboard, Spice rack…) and shops (with aisle order).

**Recipes**

- Recipe: title, servings, steps, photos, tags, nutrition per serving, source URL / import date / source note, version number.
- Ingredient: points to a food or another recipe, amount, original wording, note.
- Homemade link: a recipe that's made ahead (batter, podi) has its own pantry food.

**Plan and cooking**

- Meal slot (name, order, on/off).
- Meal: date + slot, status (planned / cooked / didn't / moved).
- Meal item: recipe, tub, or plain food.
- Batch cook: recipe, cook date, tub count, spread pattern, prep note, batch colour.
- Tub: batch, amount in quarters, place or meal, member, use-by.
- Cooked record: snapshot of the recipe as cooked, per-ingredient choices, stock changes.

**Shopping**

- List items: phone-made ID, food, shop, amount, from plan / typed by hand, hand-edited flag, ticked by/when, put-away place, deleted marker, version.
- Staples check answers (Got it / dismissed).
- "Both ticked" questions waiting for an answer.
- Sync log of applied actions.

**History and housekeeping**

- Change log (with undo links) and monthly summaries.
- Downloaded recipe images (on the mounted volume, not in the database).

**Gaps found when checking against the 15 screens:**

- **Cook mode ingredients (decided, cabledrawer 17 Oct): both ways.** A "Show ingredients" button on every step slides up the full list, always. Per-step ingredients are offered as an **experimental** option: the app guesses which ingredients belong to each step from the step's wording and shows them under it, labelled "Experimental — guessed from the step, may be wrong". The user switches it on in Cook mode or Settings, and can fix a guess by tapping the step when editing the recipe. **Cook mode mockups need updating** (all four versions). Data model: step ↔ ingredient links, each marked guessed or set by hand.
- **Import drafts (decided, cabledrawer 17 Oct):** if you leave Import review without saving, the app offers "Save as draft?" and says drafts are kept for 15 days. Drafts are deleted quietly after 15 days. **Needs a new screen: Drafts** (list of unfinished imports, open to carry on reviewing, or delete) — to be drawn in all four versions. Data model: import draft (source, parsed result, user's choices so far, created date, expiry).
- **Notification record (decided, cabledrawer 17 Oct):** the app records each use-soon / defrost reminder it has sent, so the same reminder is never sent twice.
- **Shopping lists (decided, cabledrawer 17 Oct):** one main live list per household, split by shop, plus optional extra lists (e.g. "Party on Saturday"). Extra lists work the same way (offline, sharing, put-away). Data model: shopping list (name, main yes/no); list items belong to a list.

## 7. Security and privacy (main decisions settled 17 Oct)

**Built in (enforces the ethos):**

- **One outbound gate:** every outgoing connection passes through one place in the code, which checks the Privacy switches; anything not switched on is blocked. An automatic test fails if any other code makes a network call. Library telemetry is disabled.
  - **Runtime guard (cabledrawer 17 Oct):** the running app also refuses, not just the tests: while Mealwright runs, any network connection, UDP send or DNS lookup made outside the gate is blocked, whether it comes from our code or a library (a Python audit hook in `mealwright.outbound`). Local sockets, IP literals and localhost lookups are allowed. Limit: it only sees networking done through Python's socket module, so a C library with its own networking isn't covered (relevant if the Postgres option arrives: its database address would need allowing).
  - **User agent (cabledrawer 17 Oct):** every request through the gate says it comes from `Mealwright`, with no version number and nothing about the install. This is what "generic user-agent" means for the update check below. Revisit if recipe sites block it in 0.5.
  - **Libraries that make their own connections (designed 17 Oct, before 0.8):** Apprise (notifications) and Authlib (single sign-on) open connections themselves, through `requests`, `httpx` or `smtplib`, rather than through the gate's own request function. They're let through like this:
    1. Each library is imported in one integration module only (e.g. `mealwright/notify.py`, `mealwright/sso.py`), and the import-check test lists them next to the networking modules, so no other code can call them.
    2. The integration module calls the library only inside a gate context, e.g. `with gate.library_call(household_id, Connection.NOTIFICATIONS, hosts=...)`. The gate checks the Privacy switch first. If it's off, or nothing is configured, the library isn't called at all.
    3. The context lets through only DNS lookups and connections for the destinations the household configured: the hosts in its Apprise target URLs, or its identity provider's issuer and the endpoints its discovery document lists. Anything else the library tries (another host, its own update check or telemetry) is still refused.
    4. The allowance lasts for that one call, in that thread only (it's carried by a context variable). Work a library hands to its own background threads doesn't inherit it and is refused, so integrations call libraries in a way that keeps the work in the calling thread. This needs checking for Apprise, which can send to several targets in parallel.
    5. Integrations set the library's user agent to `Mealwright` where the library allows it, so no library or Python version is sent.
    6. Each integration gets tests: with the switch off, nothing is sent; with it on, only the configured host is contacted, and a connection to any other host is refused.
    7. **Private addresses (cabledrawer 17 Oct):** notification targets and the identity provider may be on the LAN (e.g. ntfy, Authelia), but only hosts the admin has put on the same allow list used for recipe import (Settings → Outside connections → Your own network). Any other private, internal or loopback address is refused, as for recipe import.
- **Strict browser rules (Content Security Policy):** pages may only load files from the household's own server, so no CDN or tracker can be added by accident.
- **Logins:** Argon2 password hashing, slow-down after repeated wrong guesses, secure session cookies, no default admin password (the first person to set up creates the admin).
- **HTTPS is required (cabledrawer 17 Oct).** Mealwright is meant to sit behind the household's own reverse proxy, any of them (Caddy, Traefik, nginx, Nginx Proxy Manager…), which provides HTTPS. Browsers only allow these over HTTPS: signing in from other devices (the session cookie is HTTPS-only), installing the app (PWA), offline shopping (service worker) and keep-screen-awake (Wake Lock). On a plain `http://` address, sign-in is refused with a plain-English message saying HTTPS is needed, rather than failing silently. `localhost` counts as secure. For testing on a trusted network, the admin can set `MEALWRIGHT_ALLOW_PLAIN_HTTP=true`: sign-in then works over plain HTTP, the web app shows a warning, and a warning is logged at start-up.
- **Reverse proxy addresses (cabledrawer 17 Oct):** the visitor's real address (for the sign-in slow-down and the sign-in log) comes from the proxy's `X-Forwarded-For` header, believed only from the proxies listed in `MEALWRIGHT_TRUSTED_PROXIES` (addresses or networks). It's empty, so off, by default. The visitor's address is the last one a trusted proxy added, so a made-up header from a visitor doesn't count. The slow-down counts wrong guesses per account and per real address, so one person's guesses never slow down everyone.
- **Secrets encrypted on the server:** notification links (Apprise URLs carry tokens) and the SSO client secret.

**Decided (cabledrawer 17 Oct):**

- **Recipe links on your own network:** imports from private and internal addresses (router, other homelab services, the server itself) are blocked by default to prevent SSRF; the admin can add an allow list (e.g. a home wiki).
- **Signing out on a phone** wipes that device's offline copy (shopping list, cached recipes, waiting changes), with a warning first if changes haven't been sent yet.
- **Export everything** offers an optional password that encrypts the file; it is offered but not required.

**Backups (cabledrawer 17 Oct):** the app makes its own backup automatically, daily by default, into its existing data volume, keeping the last 7. The user can change how often and how many are kept. Nothing leaves the server; the user's own backup tools can copy it from there.

**API tokens (cabledrawer 17 Oct):** each token is read-only or full access, with an optional expiry date (e.g. a read-only Home Assistant token can see the list but not delete recipes).

**Logs (cabledrawer 17 Oct):** errors and sign-ins only, never what people cook, buy or type. Kept for 14 days, stored locally, never sent anywhere. **How (0.1.1, cabledrawer asked Claude Code to choose, 17 Oct):** the app keeps its own log file in the data folder (`/data/logs/mealwright.log`, owner-only). A timer starts a new file just after each midnight UTC and deletes files last written more than 14 days ago, so this holds on a quiet server too; "Report a problem" reads recent errors from it. Every line carries a UTC time. **Sign-in lines (anything with a username or address) go only to this file, never to the container output (cabledrawer 17 Oct):** Docker can only limit its copy by size, so on a quiet server it would keep them for months, or years with a large server-wide default. The container output gets start-up messages, warnings and errors; the example compose file still caps it at 2 × 1 MB as a safety net, overriding the server's default. Backups should leave `data/logs` out, or they keep sign-in lines beyond 14 days. **Blocked connections (cabledrawer 17 Oct):** the "Blocked outgoing connection" warning stays in both the container output and the file, but names only the switch in plain words ("recipe import is switched off"), never the host, site or URL: a site name shows what someone was cooking. **Sign-in log lines (cabledrawer 17 Oct):** every sign-in writes "Signed in"; the slow-down is logged once when it starts or doubles, with the wait (not on every refused try, so the log can't be used to fill the disk); a username is logged only if it's a real account, otherwise "unknown user", so a password typed into the username box never reaches the log.

**Bug reports (cabledrawer 17 Oct):** Settings → About has a "Report a problem" button. The server never sends anything; the person does, after seeing exactly what's in it.

1. The app builds a short report on the server: app version, browser and phone type, recent errors from the log, and a "What were you doing?" box.
2. The person sees the whole report first, with personal details already removed (no names, recipes, pantry contents or server address), and can edit or delete any line.
3. They choose how to send it: **Open on GitHub** (a pre-filled new-issue page in their own browser; needs a GitHub account), **Copy**, or **Download as a file**.

No automatic crash reporting. Not in the Privacy list, because the server makes no connection for it. **Settings mockups:** add "Report a problem" to About.

**Updates (decided, cabledrawer 17 Oct)** — three levels, all built:

1. **No connection, always on:** the app knows its own release date; after a while Settings → About shows "This version is 4 months old. New versions are listed at <link>." Opening the link is the user's own click.
2. **"Check now" button, admins only:** one plain request to GitHub's public release list. Nothing about the user or install is sent (no install ID, no version in the request; the user-agent is just `Mealwright`, with no version, as for every request through the gate); the comparison happens on the server.
3. **Automatic daily check, off by default:** the same request once a day, listed in Settings → Privacy with its own switch. When an update exists, admins see a small "Update available" badge, optionally also sent through the household's own notifications.

Also: the app reports its version number on the local network (in `/api/v1`), so Diun, Renovate etc. keep working with no extra connection. **Settings mockups need updating** (Privacy gets the update-check switch; About gets the version-age note and Check now) — all four versions.

## 8. Release plan (settled 17 Oct)

**Decided (cabledrawer 17 Oct):**

- **Contributor policy: DCO.** Contributors add a one-line "Signed-off-by" to each commit, confirming the work is theirs to give under AGPL-3.0. No CLA, so Mealwright stays AGPL-only.
- **No public test version.** The first public release is 1.0.0, and only when every "v1.0 must have" feature is built. No alpha or beta channel. (A small private trial with a few invited testers at 0.9 is allowed; see "Lessons from other self-hosted apps" below.)
- **Version numbers: plain MAJOR.MINOR.PATCH.**
  - 1.0.0 → 2.0.0: major new functionality.
  - 1.0.0 → 1.1.0: smaller feature upgrades.
  - 1.0.0 → 1.0.1: security fixes and tiny updates.
  - Anything that needs the user to act before updating (a manual database step, a removed or renamed setting) also goes to the next major version, even if small, with the steps in the release notes.
- **Where the image lives:** GitHub Container Registry (GHCR) is the main home, next to the code, releases and issues. The same automatic build pushes an identical copy to Docker Hub so people can find it there; the README shows both install names. Built for Intel/AMD (amd64) and ARM (arm64, e.g. Raspberry Pi). Tags: exact version (1.2.3), minor (1.2), major (1) and latest.

**Before 1.0.0 goes out (cabledrawer 17 Oct):**

- **Licences:** the automatic build checks every dependency against an allow list of AGPL-compatible licences (MIT, BSD, Apache-2.0, ISC, LGPL, GPL-3.0, AGPL) and fails on anything else; watch especially for GPL-2.0-only. The bundled food-conversion table is checked by hand. **Fonts (cabledrawer 17 Oct):** OFL-1.1 is also allowed, for font packages only (the bundled Plus Jakarta Sans and Newsreader come from `@fontsource`, which is OFL-1.1); any other OFL-1.1 dependency still fails the check. **PSF-2.0 and MPL-2.0 (cabledrawer 17 Oct):** both are also allowed (e.g. `typing_extensions` is PSF-2.0; `certifi` and `pathspec` are MPL-2.0). MPL-2.0 is only compatible with AGPL through its secondary-licence clause, so an MPL-2.0 package marked "Incompatible With Secondary Licenses" (MPL-2.0 Exhibit B) must be rejected. **MIT-0 and BlueOak-1.0.0 (cabledrawer 17 Oct):** both are also allowed. MIT-0 is MIT without the attribution requirement (`cffi`, used by the Argon2 password library); BlueOak-1.0.0 is a permissive licence (`minimatch`, used by ESLint). **Development-only dependencies (cabledrawer 17 Oct, standing rule):** MIT, MIT-0, BSD-2-Clause, BSD-3-Clause, ISC, Apache-2.0, BlueOak-1.0.0, 0BSD, Unlicense, CC0-1.0, PSF-2.0 and Zlib are approved without asking for packages used only while developing and testing (never in the app image). The allow list marks 0BSD, Unlicense, CC0-1.0 and Zlib as dev-only. Anything that ships in the image, and anything copyleft, unknown or unusual, still needs cabledrawer's OK. **Approved for 0.2 (cabledrawer 17 Oct):** APScheduler with tzlocal (MIT, ships in the image); Hypothesis and @axe-core/playwright with axe-core (MPL-2.0, dev-only; checked 17 Oct: neither carries the "Incompatible With Secondary Licenses" notice).
- **No unasked connections:** the automatic test from section 7, plus one manual run with every Privacy switch off while watching the network. The README Privacy section lists every possible outbound connection.
- **Name:** search the UK, EU and US trademark registers for "Mealwright" in the software classes. Search only, no registration.
- **Security:** automatic scanners in the build (known vulnerabilities in dependencies, code scanning, image scan) plus a self-check against a standard web-app security checklist. Just before release, ask the self-hosting community to review and try to break it.

**Bug reports and contributions (17 Oct):**

- **Bugs:** GitHub issues, using the pre-filled form from Settings → About → "Report a problem". Feature requests go to GitHub Discussions, so issues stay bugs only.
- **Security problems:** reported privately through GitHub's private vulnerability reporting, never as public issues; `SECURITY.md` explains how.
- **Contributions:** cabledrawer reviews and merges everything. Anything bigger than a small fix starts as an issue first. `CONTRIBUTING.md` covers the DCO sign-off, the ethos rules (no telemetry; no new outbound connection unless behind a Privacy switch) and the UX rule "phone breaks ties".
- **AI help must be disclosed (cabledrawer 17 Oct):** contributors say in the pull request when code was written with AI help (alongside the project's own AI disclosure).
- **Expectations (cabledrawer 17 Oct):** the README says Mealwright is a spare-time project and replies may take a week or so.

**Lessons from other self-hosted apps (cabledrawer 17 Oct).** Taken from how Mealie, Immich, Paperless-ngx, Tandoor, KitchenOwl and Actual Budget grew up. All six adopted by cabledrawer.

- **The 1.0 promise.** 1.0.0 is a promise about what won't break during 1.x: the public API (`/api/v1`, including the offline sync protocol), the export format, settings and environment variables, and the data itself. Every 1.x version upgrades in place with no manual steps; anything that can't goes to 2.0 (see version numbers above). The export format is versioned and documented in `docs/`, so people can always get all their data out and back in. Tests: from 0.9, a saved database from each earlier 0.x tag must upgrade cleanly to the latest version; from 1.0, every release is also tested upgrading from a 1.0.0 database. (Why: Mealie's v1 couldn't upgrade in place and carried only recipes, categories and tags across.)
- **A "Not planned" list** in the README and here: things Mealwright won't do, so repeat requests get a link instead of a debate. It starts from the non-goals (section 1), the ethos hard rules and "Not in v1" (section 2), and grows as requests come in. (Why: Actual Budget does this publicly; saying no is the main way a spare-time project stays maintainable.)
- **Real use from 0.3.** From 0.3 (shopping list) cabledrawer's household uses Mealwright for real every week and keeps a short running note of anything annoying or confusing (the friction log). Each milestone lead reads it when its milestone starts. The non-technical prototype test is run before 0.4 starts if at all possible, so its findings shape the recipe, plan and cooking screens. (Why: Tandoor's biggest complaint is a dense, hard-to-learn UI, and Mealwright has as many features.)
- **A small private trial at 0.9.** Two or three invited self-hosters install a 0.9 build on their own servers and use it for about a month, alongside the community review. It stays private: no public image or release, so "no public test version" still stands. How they get the build is decided at 0.9.
- **Plan for stepping away.** `docs/dev/` gets an architecture overview (how the pieces fit together) and a "how to build and release" guide, so someone else could carry on or fork cleanly. Written in 0.9 and kept up to date after. (Why: Paperless-ng stalled when its only maintainer went quiet, and contributors had to fork it as Paperless-ngx.)
- **Release slowly after 1.0.** New features are bundled into minor releases about once a month at most; security fixes go out as patch releases whenever they're needed. (Why: Immich released about every five days, but it has a full team.)

## 9. Roadmap and build versions (settled 17 Oct)

**While building (cabledrawer 17 Oct):** development versions are 0.x (0.1.0, 0.2.0 …), one per build milestone in `BUILD-PLAN.md`. They are not published publicly (no test version, see section 8); cabledrawer can run them on his own homelab. 1.0.0 is the first public release.

**Code home while building (cabledrawer 17 Oct):** cabledrawer's own Forgejo on the homelab, private repo. **No self-hosted CI runner during 0.x (cabledrawer 17 Oct):** running untrusted build code on the homelab needs more isolation than it's worth for a one-person project. Instead, a local `./check` script at the repo root runs everything CI would have run (lint, types, tests, licence allow list, pip-audit, osv-scanner, Bandit, and Trivy plus the no-telemetry check on the built image), before every pull request, with its summary pasted into the PR. 0.x images are amd64 only. cabledrawer builds them on his own computer, saves each as a file, copies it to the server with `scp` and loads it with `docker load` (`docs/dev/test-on-homelab.md`). Images are never pushed to any registry during 0.x (cabledrawer 18 Oct). CI starts at 1.0 on GitHub Actions, when the code moves to GitHub. **How `./check` runs the scanners (cabledrawer 17 Oct):** pip-audit and Bandit through `uvx`, each pinned to an exact version (and to dependencies published before a fixed date); osv-scanner as a Docker image pinned by digest, with the repo mounted read-only; Trivy as a Docker image pinned by digest, scanning an exported image file with no access to Docker. **Bandit, not Semgrep:** Bandit runs fully offline, while Semgrep downloads its rules from its own registry under a non-open rules licence and sends usage metrics by default. All four are Apache-2.0 and are dev tools only, never part of the app. They send package names and versions to vulnerability databases or download one, and nothing about the install or the homelab. Trivy sends anonymous usage data to Aqua and checks for its own updates by default; both are switched off (`--disable-telemetry --skip-version-check`, 17 Oct). **Browser tests (cabledrawer 17 Oct):** Playwright 1.63.0 (Apache-2.0), installed in WSL as a test-only tool in `e2e/`, running headless Chromium against the real app on 127.0.0.1. Its system libraries were installed by cabledrawer (`sudo npx playwright install-deps chromium`). **Trivy rule (cabledrawer 17 Oct):** Trivy fails the check on HIGH or CRITICAL vulnerabilities that already have a fix, and skips ones with no fix yet. At 1.0.0 the code moves public to GitHub via a Forgejo push mirror; section 8 (GHCR + Docker Hub, GitHub issues and Discussions) applies from then on. **When `./check` runs (cabledrawer 17 Oct, from 0.3):** three levels. While working: only the test file for the change, plus lint and type checks on the side being touched. `./check --fast` after a chunk of work or a round of review fixes: backend and frontend checks and tests, without fresh installs, browser tests, scanners or the image. The full `./check` is still required before opening every pull request, again on the final commit after the last fixes (the pasted summary must match what is merged), for every release pull request, and whenever a dependency, lock file or the Dockerfile changes. The checker accepts a pasted summary whose commit matches the pull request's latest commit instead of running it again; it runs the screenshot review and that feature's browser tests. Nothing is skipped silently: a pull request without a full pass on its final commit isn't ready.

**Working lessons from 0.3 (cabledrawer 18 Oct):** (1) Long design docs get a one-page summary at the top with section numbers; helpers read the summary and only the sections their pull request needs, never the whole file. (2) When cabledrawer makes a decision that affects a pull request, the lead copies it word for word into `docs/dev/progress.md` under that pull request, and the checker checks the pull request against that list. (3) All of a milestone's product questions go to cabledrawer before its first code pull request starts. (4) Two pull requests run side by side only when they touch separate parts of the app; ones that share behaviour run one after the other. (5) The mockups canvas is kept up to date only for screens not built yet, and a mockup is changed before its pull request starts, never after. Once a screen is merged, the app and its pull request screenshots show how it looks.

**After 1.0.0:** Plans after 1.0 are kept outside the repo.

## Data model notes collected so far (for step 6)

- A meal = (date, slot) container holding one or more items; an item is a recipe (fresh), a tub from a batch cook, or a plain food ("Fruit"). Meal nutrition = sum of items.
- Slots are per-household configurable: name, order, on/off (defaults Breakfast, Lunch, Snack, Dinner). Hiding a slot keeps its meals.
- Batch cook = recipe + cook date + portion count + spread pattern (lunches / lunch & dinner / dinners / manual); tubs link back to it, each optionally assigned to a household member and placed in a meal, in the freezer, or unplaced ("tubs left").
- Cook-day prep notes ("soak chickpeas the night before").
- Food: name, aliases, default location, tracking mode (weight / volume / count / staple), grams-per-cup (optional), per-item weight (optional), pack size (optional), running-low level (optional), preferred shop (optional). Household-learned conversions (from "ask once", when "remember" is on) stored on the food.
- Recipe ingredient: food link, amount in base unit, original text (as written), note ("peeled").
- Stock lot: food, amount (base unit), location, expiry (optional), added date — deductions take the soonest-expiring lot first.
- Locations: per-household list (defaults Fridge, Freezer, Cupboard, Spice rack), renameable.
- Shops: per-household list of names, with aisle/category order.
- Stock change log (cooked / shopped / adjusted / moved / binned, who, when) — powers Recent changes and Undo.
- "Cooked it" confirmation records per-ingredient include/exclude and used-or-left overrides.
- Per-user settings include units display (metric / cups / as written), theme (auto/light/dark), sidebar collapsed state, keep screen awake in Cook mode.
- Household settings include outside-connection switches (recipe link import, photo download), notification targets, staples check on/off, use freezer stock last.

## Publishing requirements already noted

Migrations from day one; SSRF protection on URL import; multi-user plus OIDC plus API tokens; household_id on all data; metric base with locale-based display units; SQLite default, Postgres optional; multi-arch image on GHCR; Mealie importer (carry nutrition fields across); docs and changelog; cabledrawer identity and AI disclosure; README "Privacy" section stating the ethos and listing every possible outbound connection; bundled food-conversion table with licence checked.
