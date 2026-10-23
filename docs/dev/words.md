# The word list: how Mealwright talks

**Approved by cabledrawer on 19 Oct; sections 14 to 17 approved on 21 Oct. A line still marked "proposed, for cabledrawer" waits for his OK.** Written by Claude Code on 18 Oct from the spec and the screens as they are built (0.3). Every line says where it comes from. Where the built screens disagreed with each other or with the spec, cabledrawer ruled on all twelve on 19 Oct; the rulings are in section 11. cabledrawer approves any change to this list (spec: UX — CORE → Keeping the UI good, item 1). Rulings 1 to 4 ("item", the sign-in switch, curly apostrophes, error endings) are on the screens from the 0.4 paper-cuts pull request. Some quotes in this list still show a straight apostrophe; on screen it is always the curly one (ruling 3).

**Who uses this:** builders write on-screen text from it; the checker checks every pull request's on-screen text against it (`e2e/REVIEW.md`, "Keeping the UI good"). A test already scans the web app for the word "food" (`frontend/src/lib/plainWords.test.ts`).

**Where it comes from:** `spec` = `docs/spec.md` (section or heading named); `api` = `docs/dev/api-0.2.md`; `sync` = `docs/dev/sync-protocol.md`; `review` = `e2e/REVIEW.md`; a path like `frontend/src/lib/network.svelte.ts` is the built wording.

---

## 1. Words we use, and words we never use

| Say | Never say | Where it comes from |
|---|---|---|
| **ingredient** (the screen is called Ingredients) | food, food item | spec "Removing an ingredient → Words" (cabledrawer 17 Oct); api, top; test `plainWords.test.ts`. "Food" stays in code, field names and paths only. |
| **cupboard**, **fridge**, **freezer**, **spice rack** | location, storage location | spec principle 7; "Places at home default to Fridge · Freezer · Cupboard · Spice rack" (Onboarding) |
| **use soon** | expiring, expiry | spec principle 7; the Pantry filter "Use soon" |
| **use by** (a date: "use by Mon") | expiry date, best before | `frontend/src/lib/dates.ts` |
| **tubs left** | leftover units, portions remaining | spec principle 7 (tubs arrive in 0.6) |
| **packet, pack, tub, dozen, bottle, loaf…** (the way that ingredient is sold, one per ingredient) | unit, SKU | spec "Measure stock the way it's sold" (cabledrawer 17 Oct); principle 7 ("never units") |
| **amount** | quantity | `review` (plain words list); the "Amount" field in Add to pantry |
| **staple** ("Always assumed in stock") | default item, pantry staple flag | spec Pantry; `IngredientEditor.svelte` |
| **other names** | aliases, synonyms | spec (other names), `IngredientEditor.svelte` "Other names" |
| **usual shop**, **usual size**, **usual place** | default shop, default size | `IngredientEditor.svelte` |
| **Recent changes**, **Undo** | history, log, audit trail | spec "Recent changes" and "History and undo". (Settings → Your data says "Recent changes" too, not "change log": section 11, ruling 7.) |
| **waiting changes** ("3 changes waiting") | queue, pending sync, unsynced | spec principle 16; `review` |
| **Offline**, **Back online** | disconnected, sync failed | spec principle 16 |
| **sign in**, **sign out** (verbs); **Sign-in** (the Settings section) | log in, log out, login (verb) | spec "Sign in", "Sign-out warning" |
| **household** | family, group, organisation | spec throughout; principle 7 ("never groups") |
| **shopping list** (and "the list" next to Shopping) | cart, basket | spec "Shopping", `store.svelte.ts` |
| **In the trolley** (ticked items) | cart, done | `frontend/src/routes/(app)/shopping/+page.svelte` |
| **ticked** / **Tick** | checked, completed | `store.svelte.ts` toasts ("Basmati rice ticked") |
| **Put away** (choosing where a ticked item goes) | store, file | spec "Shopping" (Desktop "Put away" panel) |
| **Remove from Ingredients** (deletes an ingredient) · **Take out of this recipe** (inside a recipe, from 0.4) · **Remove from list** (Shopping) | delete (for these buttons); "Remove" alone inside a recipe | spec "Removing an ingredient → Words" (cabledrawer 17 Oct); "Remove from list" (cabledrawer 18 Oct) |
| **Merge** (two ingredients that are the same) | combine, dedupe | `IngredientEditor.svelte` |

**Words the checker rejects on screen** (`review`, Plain words): "units", "lots", "entities", "quantity", "SKU", "location", "sync", "queue", "conflict". Principle 7 adds "food items", "labels", "groups". "Item(s)" is **allowed, for shopping-list lines only** (cabledrawer 19 Oct, section 11, ruling 1); the Pantry count says "ingredients".

**Never "Are you sure?"** There are no confirm dialogs: actions happen at once and offer Undo (spec principle 6). There are two justified exceptions: signing out with unsent changes (spec "Signing out with unsent changes"), and removing a line from the shopping list, which asks "Remove Onion from the shopping list?" first (cabledrawer 20 Oct; section 14).

**Never "No conflict pop-ups":** clashes are a quiet note with Undo ("Wren ticked this too") (spec "Offline shopping-list sync").

## 2. Screen and page names

Today · Plan · Shopping · Pantry · Recipes (sidebar names). Phone tabs: Today · Plan · **Shop** · Pantry · Recipes ("Shop" is the short name under the tab: `frontend/src/lib/nav.ts`). Under Recipes: All recipes · Ingredients; Drafts joins them with import in 0.5 and is hidden until then (spec "Recipes navigation"). Other pages: Settings, Sign in, Set up Mealwright (first run). Source: spec "Layout decisions"; `nav.ts`.

## 3. Places, shops and lists

- Places: **Fridge · Freezer · Cupboard · Spice rack**; renameable, so use the household's own names on screen (spec Onboarding; Settings → Shops & places).
- Shops are names only. **Any shop** is the group for ingredients with no usual shop; **All** is the view with every shop under its own heading and is where Shopping opens (spec "Shopping opens on All", cabledrawer 18 Oct).
- Lists: **Main list** (called "This week" until renamed; "main list" is shown in small text beside it) and **extra lists** ("Party on Saturday"). **+ New list**. The picker reads "Main list · 12" and "Extra list · 5 · ticked items still go to the pantry". Source: spec "Shopping extra lists"; `ListPicker.svelte`.
- Aisles use these names: Veg & fruit · Meat & fish · Dairy · Dry goods · Tins & jars · Spices · Other (`frontend/src/lib/shopping/aisles.ts`; spec "Shopping").
- Where something goes: "In the Fridge · 2 L" (the line under a ticked row, section 14), "Milk → Fridge" (the toast), "Moved Milk → Freezer".

## 4. Amounts and dates

- **Amounts are shown the way they're sold** and the arithmetic stays behind the scenes: "1½ packets · about 750 g", "1½ bottles · about 1.5 L", eggs "9 left · bought as a dozen" (spec Pantry; "Measure stock the way it's sold"). The server makes these strings (`display`); the screen never rebuilds them (api, "Decision: the server returns structured numbers and a ready `display` string").
- **A no-break space** sits between a number and its unit or count word ("750 g", "1½ packets", "2 L") so a narrow column never wraps "750 / g" (api, "No-break spaces"). Fractions are ¼ ½ ¾ and "Full"; quick picks read "¼ · ½ · ¾ · Full" (spec "Part-used packets"; "Marks in the opened pantry row").
- **"about"** marks a best guess ("about 250 g", "About 250 g left · type it instead") (spec "Part-used packets").
- **Count words:** "1 bunch of Coriander" (spec, cabledrawer 18 Oct); an ingredient counted one by one says "5 left", not grams.
- **Dates:** "Today", "Tomorrow", a weekday for the next 6 days ("Mon"), then "12 Nov"; "Date passed" when it has gone. In a sentence: "use by Mon", "use by today", "use-by date passed", "no use-by date", "added today", "added yesterday", "added 3 Oct" (`frontend/src/lib/dates.ts`). Dates follow the household's time zone, not UTC (spec "Today is the household's local time", cabledrawer 17 Oct). Day before month, as cabledrawer's phone shows it (`e2e/playwright.config.ts`, locale en-GB; the app's date words use `en-GB`).
- **Amount questions:** "How much? Type an amount, like 200." · "Type an amount, like 500 g or 2 packets." · "How much is left? Best guess is fine." (`AddToPantry.svelte`, `amountEdit.ts`, `LotMenu.svelte`).

## 5. Buttons and links

Rules (all from what is built; the spec only fixes a few of them):

1. **A verb, or a verb and its object, in sentence case:** "Sign in", "Create account", "Add to pantry", "Clear ticked", "Remove from list". No full stops. No "OK", "Submit", "Yes/No" alone.
2. **A "+" starts a button that adds something new:** "+ Add to pantry", "+ New ingredient", "+ New list", "+ Staple", "+ Shop", "+ Add a size". (`pantry/+page.svelte`, `ListPicker.svelte`, `IngredientEditor.svelte`)
3. **The cancel choice is "Cancel"** in a sheet that was opened to add something, "Not now" in the Ask-once question, "Done" to close the ingredient editor, "Close" for a side panel. (`AddToPantry.svelte`, `AskOnce.svelte`, `IngredientEditor.svelte`, ingredients page)
4. **Retry is "Try again"** after a failure; **"Try now"** only in the offline bar (checks the connection); **"Try sending now"** only in the sign-out warning (sends the waiting changes). They mean different things, so they stay different. (spec "Signing out with unsent changes"; `ConnectionStatus.svelte`)
5. **Undo is always called "Undo"**, in the toast, in Recent changes, and in "Undo last change" / "Undo last tick". Never "Revert" or "Restore".
6. **The warning that loses data names what it loses:** "Sign out and lose them", "Carry on and lose them". Never "Sign out" alone in that warning. (spec "Signing out with unsent changes"; "A different login on a phone…")
7. **Switches, not checkboxes**, for every on/off, labelled in words that say the on state ("Remember this phone", "Remember for next time", "Staple") (spec principle 15).
8. **Choices with several options use buttons that say what they do**, in the order the spec gives: "Try sending now · Stay signed in · Sign out and lose them".
9. **Screen-reader names say what happens** ("Add Oil to the shopping list", "Tick Basmati rice", "Undo: Used 200 g spinach") and the visible name is part of them (WCAG "label in name").

## 6. Toasts and Undo

- A toast is one calm sentence about **what happened**, in the past tense, with the ingredient's name first or the verb first as the server words it: "Used 200 g spinach", "Binned Milk", "Toor dal moved to Fridge", "Basmati rice ticked", "Oil added to the shopping list", "Renamed to Toor dal", "Toor dal is a staple", "Removed Onion", "Salt restocked". Source: `pantry.svelte.ts`, `store.svelte.ts`, `IngredientEditor.svelte`, `foodEditor.svelte.ts`; spec "Tap a staple when it runs out".
- Every change has an **Undo** button in its toast (6 seconds; it waits while the pointer or keyboard focus is on it) and **Ctrl+Z** on desktop (spec principle 6; `toast.svelte.ts`).
- **After Undo: "Undone: " and the change's own words,** with the original capital letter: "Undone: Used 200 g spinach", "Undone: Removed Oil from Ingredients" (`undo.svelte.ts`, `client/changes.ts`). When only some could be put back, the server's own sentence is added: "Undone: Used about ½ tub Yogurt. Yogurt is back in Ingredients, with ½ tub in the Fridge." (api, "Remove a food").
- **A removed ingredient that comes back** by another way than undoing its removal (an Undo in Pantry that puts stock back into it, or an offline phone adding it) gets its own line in Ingredients → Recent changes: "Lemon is back in Ingredients" (its real name), with no Undo. The old "Removed Lemon from Ingredients" line then has no Undo either: only the newest removal of an ingredient has Undo, and only while it is still removed (`history.py` `record_back`, `can_undo`). Decided by cabledrawer: the words and both routes on 20 Oct ("when a removed ingredient comes back by any route (an Undo in Pantry, or an offline phone adding it), Ingredients' Recent changes gets a line "Lemon is back in Ingredients", and the old "Removed Lemon from Ingredients" line loses its Undo"); the Undo rule on 21 Oct ("No Undo on the "is back" line." and "only the newest removal line for that ingredient can have Undo, and only while the ingredient is still removed").
- **Already done is said, not repeated:** "Oil is already on the shopping list." (Pantry) and "Milk is already on the list · 2 L" (Shopping add box) (spec "Tap a staple…", "Adding something that's already on the list").
- **A note, not a pop-up, when two people clash:** "Wren ticked this too", "Wren added milk too", "Wren put coriander in the Freezer", each with Undo (spec "Offline shopping-list sync").
- **A problem toast** (for something that didn't work) uses the same calm voice and offers "Try again" (see section 7).

## 7. Error messages

**How one is built: what happened, then what to do.** Short, plain, no codes, no blame, no "Error". The server writes its own sentence in `detail` and the app shows it as it is (api, top).

Patterns in use:

- **Couldn’t + the verb + a way forward:** "Couldn’t load the pantry. Try again." · "Couldn’t load your ingredients. Try again." · "Couldn’t load this ingredient. Check your connection and try again." (`pantry.svelte.ts`, `ingredients.svelte.ts`, `foodEditor.svelte.ts`)
- **A problem toast:** "Couldn’t save. Try again." (ruling 4's own example) · "Couldn’t undo. Try again." · "Couldn’t add that shop. Try again." · "Couldn’t add it. Try again." (`save.ts`, `undo.svelte.ts`, `IngredientEditor.svelte`, `NewIngredient.svelte`; proposed, for cabledrawer: the old wording with a dash, made two sentences by ruling 4)
- **Connection:** "Can’t reach your Mealwright server. Check your connection." (`api.ts`). In an offline-capable place the offline wording of section 8 is used instead.
- **Anything else:** "Something went wrong. Try again." (`api.ts`)
- **Asking for the right thing in a field:** say what to type, with an example: "Enter your name." · "Choose a username." · "Use at least 10 characters." · "Use up to 50 lowercase letters, numbers, dots, dashes or underscores." · "Give the size a name, like tub or packet." · "Try something like ½ packet or 250 g." · "Use g, kg or one of its sizes, like packet." (`setup/+page.svelte`, `IngredientEditor.svelte`, `amountEdit.ts`)
- **Never a raw status code or a stack trace**; logs stay on the server and never hold what people cook, buy or type (spec section 7, Logs).

(Section 11, ruling 4: two short sentences, no dash, no "Please".) The server's own field messages follow it too: "Type a name." · "Type the shop’s name." · "Give the weight in grams." · "Enter your name." · "Too many tries. Wait 5 minutes." (proposed, for cabledrawer: the old wording without "Please"). "Please sign in again." on the sign-in page (section 9) is left as it is: it is the reason the page shows, not an error (proposed, for cabledrawer).

## 8. Offline and connection wording

All from spec principle 16 and "Offline shopping-list sync" (cabledrawer 17 to 18 Oct); built in `network.svelte.ts`, `ConnectionStatus.svelte`, `OfflineNote.svelte`, `shopping/view.ts`, `store.svelte.ts`.

- **Nothing extra while all is well.** A short blip shows nothing.
- **Bar, phone:** "Offline — 3 changes waiting" (singular "1 change waiting"), with "Try now". **Desktop:** "Offline", with "Try now", and under it "3 changes waiting. They’ll save when you’re back." In the collapsed sidebar a small dot that is also the "Try now" button.
- **Back:** the toast "Back online — all saved" (short, goes by itself).
- **Shopping subtitle:** "12 to buy · saved" when connected; offline "12 to buy · offline, saving on this phone" (on a computer "…on this computer"); extra lists "Extra list · 5 · offline".
- **A screen that needs the server:** "You’re offline." then "Pantry needs your Mealwright server. Your shopping list works offline." (ruling 4; naming Pantry, Ingredients or Settings), with a **Shopping** button. "+ Add to pantry" stays visible and says "Adding to the pantry needs your Mealwright server. Try again when you’re back online."
- **A phone that has never loaded the list:** "Your shopping list isn’t on this phone yet. It’ll be here after you’ve opened it once while connected."
- **"Changes", never "actions", "operations" or "mutations"; "waiting", never "queued" or "pending".**

## 9. Signing in and out

From spec "Sign in", "Sign-out warning", "Offline shopping-list sync" (cabledrawer 17 and 18 Oct); built in `sign-in/+page.svelte`, `setup/+page.svelte`, `settings/+page.svelte`, `offline/held.ts`.

- Sign in page: "Welcome back", "Sign in to your household’s kitchen", fields **Username**, **Password** (with **Show** / **Hide**), the switch "Remember this phone" / "Remember this computer", with "for 30 days" in small text (section 11, ruling 2), button **Sign in** ("Signing in…" while it works), "Forgot your password? Ask your household’s admin to reset it." (no email reset: nothing leaves the server), "Your own server · nothing is sent anywhere else".
- First run: "Welcome! First, your account", "You're the first person here, so you'll be the admin…", button **Create account**; "No default password and no account with us. This login lives only on your server."
- Password turned off by the admin: only the single-sign-on button and "Trouble signing in? Ask your household's admin."
- **Plain http:// connection:** "This connection isn't secure" with "Signing in needs a secure connection. Open Mealwright at its https:// address, through your reverse proxy." (refused) or the warning "This connection isn't secure. Passwords travel unencrypted. Use only for testing on a network you trust." (allowed) (spec section 7).
- **Sign out with nothing waiting:** just signs out. **With changes waiting:** "3 changes haven't been sent yet. If you sign out now, they're lost." (1: "1 change hasn't been sent yet. If you sign out now, it's lost.") Buttons: **Try sending now · Stay signed in · Sign out and lose them**.
- **Can't check what's waiting:** "This phone couldn't check for changes waiting to be sent. Nothing has been deleted." Buttons: Try again · Stay signed in · Sign out anyway. Anything waiting on this phone may be lost (proposed, for cabledrawer: ruling 4 took out the dash).
- **Another login on a phone holding changes:** "Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." If someone else signs in anyway: "Wren's 3 changes haven't been sent yet. If you carry on, they're lost." Buttons: Sign in as Wren instead · Carry on and lose them. After being signed out for this: "You were signed out because Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." (1 change: "…Wren's change is waiting… to send it.")
- **A phone that can't delete its offline copy:** "This phone couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again."
- **Expired session:** "Please sign in again." with the number of changes kept: "Please sign in again. Your 3 changes are kept on this phone."

## 10. Phone and computer

- **"this phone" / "this computer" is chosen by layout, not by device:** with the bottom tabs the app says "this phone"; with the sidebar it says "this computer", so a tablet held wide says "computer" (spec "This phone or this computer", cabledrawer 18 Oct). Used in offline subtitles, the sign-in messages and the held-changes messages.
- **Phone first** (spec principle 1): write for the phone and let the desktop add detail. The desktop never reads worse than the phone.
- **Tap on a phone, click on a computer:** screen text avoids both and says what happens ("Open", "Choose"). Where the two must differ, the phone word is tap and the computer word is click: "· tap for dates" / "· click for dates" in a pantry row (`PantryGroup.svelte`).
- **Keyboard:** names for keys are written as people say them: "Ctrl+Z" (Cmd+Z on a Mac), "Escape closes".
- **Same wording on both**, unless the space is very tight: shorter forms are for the phone only and are listed here ("Shop" under the tab, "Offline — 3 changes waiting" on the phone bar versus two lines on desktop).

## 11. Decisions on the differences (cabledrawer 19 Oct)

cabledrawer accepted all twelve recommendations on 19 Oct. Rulings 1 to 4 are on the screens from the 0.4 paper-cuts pull request; the rest already match what is built.

1. **"item(s)".** "Item" is only for lines on a shopping list ("Add an item…", "Cleared 2 ticked items", "ticked items still go to the pantry"). The Pantry count says "ingredients" ("17 ingredients · 3 use soon"). "Items" is removed from the checker's rejected list in `e2e/REVIEW.md` and noted there as allowed on the shopping list.
2. **The sign-in switch.** It reads "Remember this phone" or "Remember this computer", with "for 30 days" in small text. "Stay signed in" is only the name of the sign-out warning's button.
3. **Apostrophes.** Curly (’) everywhere on screen ("Couldn’t", "Can’t reach your Mealwright server", "You’re offline.").
4. **Errors** are two short sentences: what happened, then what to do. "Couldn’t save. Try again." No dash, no "Please".
5. **"on the list" and "on the shopping list".** Keep both: "on the list" on Shopping, "on the shopping list" everywhere else.
6. **Shopping subtitle online.** Keep the built wording: "10 to buy · saved", and "N to buy · synced with Wren" when someone else is on the list.
7. **"Recent changes"** everywhere, including Settings → Your data (not "change log").
8. **Three retry buttons stay:** "Try now" (reconnect), "Try sending now" (send waiting changes), "Try again" (repeat what failed).
9. **"Shop" on the phone tab, "Shopping" as the page name.**
10. **Empty states** have a short title for what is missing, one sentence on how things get there, and the button if there is one: "No recipes yet" · "+ New recipe".
11. **Keep the capital after "Undone:"** ("Undone: Used 200 g spinach").
12. **"Welcome!"** stays as the one exclamation mark on screen.

---

## 12. All recipes (0.4, PR 3a)

Written by Claude Code on 20 Oct from the mockups `Recipes-Phone` and `Dark-Recipes-Phone`, cabledrawer's answers of 19 and 20 Oct and the built screen (`frontend/src/routes/(app)/recipes/+page.svelte`, `frontend/src/lib/recipeLine.ts`). cabledrawer approved this section’s words (cabledrawer 20 Oct), and approves any change here.

- **Title and count:** "Recipes", with "48 recipes" above it ("1 recipe"). The count is every recipe, whatever is searched or filtered.
- **Buttons at the top:** "Ingredients" (phone) and "New recipe" (the editor, PR 5; section 17). Not there yet: "Drafts" (drafts only come with import in 0.5; cabledrawer 20 Oct), "Planned Sun" (0.6).
- **Search:** "Search recipes". It looks in recipe names, tags and ingredient names, other names included, never the method (cabledrawer 19 Oct, question 24).
- **Filter row:** "All" · "Can cook now" · "Use soon" (new, 0.4 PR 6: the recipes that use something about to go off; the mockups have no chip, and "Use soon" is Pantry's own word; kept, cabledrawer 20 Oct: "keep “Use soon”") · then the household's own tags, one chosen at a time. "Use soon" finding nothing: "No recipe uses anything that needs using up soon." (new).
- **A recipe's line,** each part only when known, with a no-break space inside "50 min" and "320 kcal": `50 min · 320 kcal · all in stock but 1`. Calories say "nutrition unknown", never 0.
- **Stock words:** "all in stock" · "all in stock but 1" (only when there is more than one ingredient) · "2 missing" ("1 missing" when its only ingredient is missing). Nothing when no ingredient has an amount. **When a recipe uses another recipe that isn’t made ahead** (it can’t be checked yet), neither "all in stock" nor "all in stock but 1" is ever shown: it says "1 missing", "2 missing" when something that was checked is missing, and no stock words otherwise; such a recipe is also left out of "Can cook now". New wording approved (cabledrawer 20 Oct).
- **Use soon:** "Uses spinach (today)", "Uses spinach and paneer (tomorrow)", "Uses spinach and 2 more (Mon)": ingredient names in lower case, the soonest day, in orange. If something is missing as well, it is said after: "Uses spinach (today) · all in stock but 1".
- **Empty:** the heading "No recipes yet" and "Recipes you add will show here." (no button until the editor).
- **Nothing found:** "No recipe matches “dal”." · "No recipe can be cooked with what is in stock right now." · "No recipes with that tag."
- **Loading and failing:** "Loading…" · "Couldn’t load your recipes. Try again." with the button "Try again" · "Couldn’t load more recipes. Try again." · the button "Show more" after 50.
- **Offline:** "You’re offline." and "Recipes needs your Mealwright server. Your shopping list works offline." (as Pantry and Ingredients).

---

## 13. The recipe page (0.4, PR 3b)

**Proposed, for cabledrawer** (written by Claude Code on 20 Oct from the mockups `Recipe` and `Dark-Phone-Recipe`, cabledrawer's answers of 19 and 20 Oct, and the built screen `frontend/src/routes/(app)/recipes/[id]/RecipeScreen.svelte`). Words that are new are marked "new"; the rest are in the mockups or the spec. cabledrawer approves any change here.

- **Page:** a "Recipes" link back (breadcrumb "Recipes › Sambar" on a computer); the name; one quiet line: the one-line description, the time ("50 min"), "Makes 1½ litres", each only when there is one, with " · " between.
- **Keep screen awake:** the switch is labelled "Keep screen awake" and is off every time the page opens. Not drawn where the browser can't do it. If the browser says no: "Couldn’t keep the screen awake." (new).
- **Nutrition:** "320 kcal · 16 g protein · 48 g carbs · 7 g fat · 11 g fibre" as five figures, with "per serving" under them. A figure nobody typed says "unknown", never 0; none at all says "Nutrition unknown" (cabledrawer 19 Oct).
- **Ingredients:** the heading "Ingredients"; "Serves 4" between "−" and "+" (screen readers: "Fewer servings", "More servings"); hidden when the recipe has neither Serves nor Makes (cabledrawer 19 Oct, question 42). A recipe with Makes and no Serves gets − / + in whole multiples, "Makes 200 g" → "Makes 400 g" → "Makes 600 g" (cabledrawer 20 Oct; built in 0.4 PR 7, until then "Makes …" is plain text with no − / +).
- **Makes − / +:** "Makes 200 g" between "−" and "+", in whole multiples (cabledrawer 20 Oct: "a recipe with Makes but no Serves gets − / +, in whole multiples (Makes 200 g → 400 g → 600 g)"), from 1× up to 99× (cabledrawer 21 Oct: "whole multiples from 1× up to 99× (same range as Serves)"). Proposed, for cabledrawer: the rest of this item, from here on; screen readers hear the group as "How much it makes" and the buttons as "Make less" and "Make more". "Makes …" then leaves the quiet line under the name, as "Serves" does; a recipe with no ingredient lines keeps "Makes …" there as plain text. The marks are for 1× (the server counts what it makes once), so at 2× and up the page shows no marks rather than wrong ones.
- **A line** shows its own words (the amount in bold); the ingredient's own name in small text only when different (question 14); the line's note after a comma. A line linked to nothing says "not linked" in small text, and one whose recipe was deleted says "recipe removed" (spec "Recipes", cabledrawer 19 Oct).
- **Where it is** (end of the line): the place ("Cupboard", "Fridge", "Freezer", "Spice rack", or the household's own name), "On list", "Staple", "Not enough" (new: some is in the pantry but less than the recipe needs), and nothing for an ingredient with none (a dashed ring; screen readers hear "Missing"). In stock or a staple wins over "On list". The marks follow the servings you chose with − / +: enough for the recipe at the chosen servings, or any stock when the amounts can't be compared (cabledrawer 19 Oct, Q22). With several places, the one holding most is named.
- **Amounts on screen:** the − / + scale amounts on screen only, whole servings 1 to 99; spoons and cups in quarters (¼ ½ ¾), counts and packets in halves, g and ml whole numbers (cabledrawer 19 Oct, question 26). Kilograms and litres to two decimals (new; the lead's note, for cabledrawer to confirm).
- **"1 missing" line:** under the ingredients, "1 missing" (or "3 missing") and the button "Add to the list". It counts ingredients that are not in stock and not already on the shopping list (as the mockup does), once each. When nothing is left to add the line is not shown at all, and the page never says "all in stock" (so a recipe using a recipe that isn't checked can't claim it). The toast says "Sambar powder added to the shopping list" for one, "3 ingredients added to the shopping list" for several, each with Undo; Undo says "Undone: 3 ingredients added to the shopping list".
- **Method:** the heading "Method", steps numbered through the headings. **Tags** as small chips. **Source:** "Source: Amma’s" (new; "From: <site>" comes with import in 0.5).
- **States:** "Loading…" · "Couldn’t load this recipe. Try again." with "Try again" · "Recipe not found" with "This recipe isn’t here any more. It may have been deleted." (new) · offline: "You’re offline." and "Recipes needs your Mealwright server. Your shopping list works offline." · a recipe with only a name: "Nothing written down yet." (new).
- **The photo** (0.4, photos PR): a screen reader hears "Photo of Sambar" (the recipe's name; approved, cabledrawer 21 Oct: ""Photo of {name}" is approved, cabledrawer 21 Oct."; the editor says "Cover for this recipe"). A recipe with no photo, or a photo that can't be fetched, has no box and says nothing (cabledrawer 21 Oct: "Keep the no-photo choice as built: a plain square in the list, no box on the recipe page."). In All recipes the photo is decorative (the row already says the name), so it has no words.
- **Not on this screen yet** (hidden, not stubbed): "Plan it" (0.6), "Start cooking" and "Cook once, eat for…" (0.7). "Edit" (top right) came with the editor, PR 5, and Delete is inside the editor (section 17).

---

## 14. Shopping rows (0.4, hand-test fixes)

Written by Claude Code on 21 Oct from cabledrawer's hand-test answers of 20 Oct and the mockups `ShopRows-Phone`, `ShopRows-Desktop`, their dark versions and the four state files `ShopRows-confirm`, `-editing`, `-removed`, `-swipe`. Words cabledrawer wrote himself are marked "cabledrawer 20 Oct" and are decided. Words Claude Code worded were proposed and are now approved (cabledrawer 21 Oct: "The proposed words in words.md section 14 are approved: “Add amount”, “(first amount)” and the screen-reader names."), marked "approved, cabledrawer 21 Oct". cabledrawer approves any change here.

**The row (cabledrawer 20 Oct)**

- Only the square ticks. The name and the amount both open the amount box. The amount is a pill with a small arrow; with no amount the pill says **Add amount** (approved, cabledrawer 21 Oct).
- Screen-reader names (approved, cabledrawer 21 Oct): the pill is "Change amount: Toor dal, 500 g" (or "Add amount for Toor dal"); the square is "Tick Toor dal" / "Untick Toor dal" (as before); the computer's bin is "Remove Toor dal from the list"; the swiped row's red button reads "Remove" and a screen reader adds the name ("Remove Toor dal from the list").

**The amount box (cabledrawer 20 Oct; the mockup's words)**

- The ingredient's name, **Done**; **−** and **+** (screen readers: "Less", "More") around the box that holds the real amount (screen readers: "Amount"); the unit choice (screen readers: "Unit"), which lists the ingredient's units and sizes the way the mockup does: "g", "kg", "packet (500 g)". It is left out when there is only one unit.
- Under it, in small text: **The box holds the real amount: edit it, or use − / +.**
- **Remove from list** (with a bin), which asks first.
- **Edit ingredient**, a small link beside Remove from list, opens the ingredient editor for that row’s ingredient (cabledrawer 21 Oct: "yes, the amount box gets a small "Edit ingredient" link to the ingredient editor."; proposed, for cabledrawer: it saves the box first, as Done does, and an amount it can’t read stops it with the usual message; it isn’t shown offline, like the recipe page’s Edit, because the editor needs the server).
- A box that can't be read says it in the existing words: "Type an amount, like 500 g or 2 packets." (section 4). Saving with Done or Enter makes one change with its Undo ("Toor dal amount changed"); Escape leaves the line as it was (approved, cabledrawer 21 Oct).

**Removing asks first (cabledrawer 20 Oct)**

cabledrawer 20 Oct: "there should be an are you sure - swiping can be by accident so important here", and for Remove in the amount box: "it should ask are you sure". This is the second justified exception to "Undo, not Are you sure?" (the first is signing out with unsent changes). It is for removing a line from the shopping list only.

- The question: **Remove Onion from the shopping list?** and under it **Nothing goes into the pantry.** The buttons: **Remove** (red) and **Keep it**. A sheet from the bottom on a phone, a dialog on a computer. "Keep it" has the focus when it opens, Escape and a tap outside also keep it.
- Afterwards the toast **Removed Onion** with **Undo** (then "Undone: Removed Onion").
- Swipe left on a phone row shows a red **Remove**; tapping it asks as above. A swipe alone never removes. On a computer a bin shows when the pointer is over the row (or the keyboard reaches it); it asks as above.

**Where a ticked row went (cabledrawer 20 Oct, option A)**

The line under a ticked row stays until the row is unticked or cleared. No ticked row shows "→ Fridge" or "→ Cupboard" any more.

| What was ticked | The line | Buttons |
|---|---|---|
| A line with an amount | **In the Fridge · 2 L** | **Change** (the places, and "Different pack?" under them; cabledrawer 21 Oct: "“Different pack?” under Change is OK") · **Undo** |
| A line with no amount | **Not in the pantry yet. No amount.** (amber) | **Add amount** (opens "How much?") |
| A staple | **Restocked · staples aren’t counted** | **Undo** |

- Toasts when ticking: "Milk → Fridge" with Change and Undo (as before); a staple says **Salt restocked** (cabledrawer 20 Oct); a line with no amount says "Drumsticks ticked".
- Screen-reader names for the buttons on the line (approved, cabledrawer 21 Oct): "Change where Milk went", "Undo ticking Milk", "Add amount for Drumsticks". The line itself is a group called "Where Milk went".
- Before the server has answered (offline), the line says where the tick will go, from the line's own amount and the ingredient's usual place. Once the server has answered, it says what really went in.
- **The Put away panel (desktop; cabledrawer 20 Oct):** "Ticked items with an amount go straight into the pantry. Each ticked row says where it went." The last tick still shows beneath it with Where and Undo last tick; for a staple or a line with no amount there is no Where.

**Recent changes: a first amount (approved, cabledrawer 21 Oct)**

Giving a ticked line with no amount its first amount ("How much?" → "Different pack?") used to read "Flour: bought 1 pack · 1 kg instead of 0 g". It now reads **Flour: bought 1 pack · 1 kg (first amount)**.

---

## 15. Recipes on a computer (0.4, PR 4)

**Approved by cabledrawer on 21 Oct, as written** (cabledrawer 21 Oct, word for word: "In PR 7, mark words.md section 15 (Recipes on a computer) as approved"). Every line below, including any marked "new, proposed", is approved.

Written by Claude Code on 20 Oct from the mockups `Desktop-Recipe` and `Dark-Recipe`, cabledrawer's answers of 19 and 20 Oct, and the built screens `frontend/src/routes/(app)/recipes/+layout.svelte`, `frontend/src/lib/components/RecipeListScreen.svelte` and `ChooseRecipe.svelte`). Everything from sections 12 and 13 is reused as it is; only what is new is listed. cabledrawer approves any change here.

- **The three panes:** the sidebar, then All recipes (title "Recipes", the count above it, search, the filter row and the rows as in section 12, no Ingredients button because the sidebar has it), then the recipe (section 13). The open recipe's row is marked. Screen readers hear the panes as "Recipe list" and "Recipe".
- **No recipe open (`/recipes` on a computer):** the heading "Choose a recipe" and "Pick one from the list to read it here." (new, proposed; an empty pane rather than the first recipe: cabledrawer 20 Oct). With no recipes at all the reading pane says nothing: the list already says "No recipes yet".
- **Offline:** one note for both panes: the title "Recipes", "You’re offline." and "Recipes needs your Mealwright server. Your shopping list works offline." (as section 12).
- **Where the three panes fit (cabledrawer 20 Oct):** from 1024 px wide with the sidebar open, or 848 px with it collapsed. Narrower (a tablet held upright), Recipes shows one page at a time with the sidebar, as before; under 768 px it is the phone's layout.
- **Not on these screens yet** (hidden, not stubbed): "+ New recipe" and Edit (the editor), "Import a recipe" (0.5), "Drafts · 3 unfinished imports" in the list (the sidebar's Drafts entry is hidden too, cabledrawer 20 Oct; done in PR 7), "Plan it", "Start cooking", "Cook once, eat for…", the photo.

---

## 16. Ingredients and the recipes that use them (0.4, PR 6)

**Approved by cabledrawer on 21 Oct, as written** (cabledrawer 21 Oct, word for word: "4. words.md section 16: approved as written, cabledrawer 21 Oct."). Every line below, including those marked "new" or "proposed", is approved.

Written by Claude Code on 20 Oct from the mockups `Ingredients-Phone` and `Ingredients-Desktop`, the spec's "Ingredients screen" and "Removing an ingredient", and cabledrawer's answers of 19 Oct, questions 20 and 30). Words that are new are marked "new". cabledrawer approves any change here.

cabledrawer 20 Oct (word for word): "7. #45: keep “Use soon”. Agreed: the filter and link, 5 recipes before “+ N more”, “Not in any recipe” on the phone." Those items are marked agreed below; the rest is still proposed. He added: "Note for the future: #45's filter and link were an addition beyond the plan. Next time, ask me before building something new."

- **A row in the Ingredients list:** "5 recipes" at its end on a phone ("1 recipe" for one), just the number under a "Recipes" heading on a computer, nothing when no recipe uses it. Screen readers hear "Used in 5 recipes". On a Maybe-the-same row the Merge button is there instead, as in the mockups.
- **The filter:** "Not in any recipe · 9" beside All and Staples, on the phone too (agreed, cabledrawer 20 Oct) (the count comes from the server). When there are none: "Every ingredient is in a recipe." (new).
- **In the editor:** the heading "Used in 5 recipes" ("Used in 1 recipe"), then each recipe's name as a link to its page. More than five: "+ 2 more" (five before "+ N more": agreed, cabledrawer 20 Oct) (screen readers: "+ 2 more recipes"), then "Show fewer". An ingredient no recipe uses: the heading "Used in recipes" and "Not in any recipe yet." (new).
- **"Remove from Ingredients"** says first, in small text above the button: "Used in 3 recipes. Their lines keep their words and show “not linked”." (one: "Used in 1 recipe. Its line keeps its words and shows “not linked”.") (new; the first sentence is the spec's, cabledrawer 19 Oct). The toast and Undo are as everywhere: "Removed Toor dal from Ingredients" · Undo · "Undone: Removed Toor dal from Ingredients".
- **A recipe's own made-ahead ingredient** has no remove button, and says "Made by the recipe Dosa batter. Turn off Made ahead there to remove it." with the recipe's name as a link (the spec's words, cabledrawer 19 Oct).
- **On Pantry's Use soon card** (the filter and link agreed, cabledrawer 20 Oct; built before he was asked, see above): on a computer the link "Recipes for these" beside the heading (the mockup's words); on a phone the link "Recipes that use them →" under the card (the mockup says "2 more · recipes that use them →"; the "2 more →" button stays its own button and opens the Use soon tab). Both open All recipes with the "Use soon" filter on (`/recipes?filter=use-soon`); on a computer that is the three panes. Shown only when something needs using up soon.
- **Hidden still** (hidden, not stubbed): tubs (0.6).

---

## 17. The recipe editor (0.4, PR 5)

**Approved by cabledrawer on 21 Oct, with one change** (cabledrawer 21 Oct, word for word: "3. words.md section 17: approved as written, cabledrawer 21 Oct, with one change: "What it makes, e.g. dosas" becomes "What it makes, like dosas"."). Every row below, including those marked "proposed, for cabledrawer", is approved.

Written by Claude Code on 20 Oct from the editor mockups (`RecipeEditor-*`, `NewRecipe-*`, `EditorState-*`), the editor brief and cabledrawer's decisions of 19 and 20 Oct. **"Decided"** means cabledrawer's own words or answer; **"mockup"** means it is drawn in cabledrawer's mockups; **"proposed, for cabledrawer"** means I wrote it because nothing covered it. Nothing here changes an earlier section.

| Where | Words | Source |
|---|---|---|
| Titles | New recipe · Edit recipe | mockup |
| Ways in | New recipe (a dark button with a +: All recipes, under the search on a phone and under the title on a computer, and under "No recipes yet") · Edit (the recipe page, top right) | mockup |
| Top bar | Cancel · Save (Saving… while it works; "Ctrl+S" shown beside Save on a computer) | mockup; "Saving…" proposed, for cabledrawer |
| Under the title (computer) | Nothing changes until you save. Only the name is needed. | mockup |
| Toasts | Saved · Changes not saved (with Undo, which opens the editor again as it was) · Deleted Sambar (with Undo) | decided (editor brief 1; spec "Cancel and offline"; "Saved" the editor brief) |
| Bars | You’re offline. Save when you’re back online. · Couldn’t save. Try again. (with Try again) · Wren changed this recipe after you opened it. (with See Wren’s version · Save mine anyway) | decided |
| Photo | Add a photo · Take one or choose from your photos · Uploading photo… · Change photo · Remove photo · Hidden details like location are removed before the photo is kept. | mockup |
| Photo errors | The server's own sentences, shown as they are: That photo is bigger than 15 MB. · That photo is too big to use (over 50 megapixels). Try a smaller copy. · That isn't a photo Mealwright can use. Try a JPEG, PNG or WebP. · Too many photos waiting to be saved. Save or cancel a recipe first. | decided (cabledrawer 19 and 20 Oct, spec "Photos") |
| Boxes | Name (hint "A name is all you need to save.") · Short description (optional) · Time (minutes) · Serves (Fewer servings · More servings · Clear (for a batter or a powder)) · Makes (optional) (litres · ml · g · kg · count) · Tags (optional) · Nutrition per serving (optional) (kcal · protein g · carbs g · fat g · fibre g) · Source (optional) | mockup |
| Makes, a count | "What it makes, like dosas" is asked when the unit is "count" | approved with this change, cabledrawer 21 Oct (it was "e.g. dosas"; the mockup has a unit list with "count" but no place for the word) |
| Hints | For a batter, a podi or anything made ahead: “Makes 200 g”. · Type a tag and press Enter. Tags you’ve used before are suggested. · Leave a box empty if you don’t know: it shows as unknown, never 0. · A web address shows as a link you can open yourself. Mealwright never visits it. (Hidden until 0.5, when links arrive: cabledrawer 21 Oct: "hide the “A web address shows as a link you can open yourself” hint until 0.5, when links arrive".) | mockup |
| Made ahead | Made ahead (keeps in the pantry) · For things you make once and use over days · Adds **Dosa batter** to Ingredients as homemade, so the pantry can keep it. · Add how much it makes, so the pantry can count it. · "Dosa batter is already in Ingredients. It will be linked to this recipe, and its pantry stock stays." (real names) | mockup; the "already in Ingredients" sentence decided (cabledrawer 19 Oct, word for word) |
| Made ahead, saved recipe | Kept in Ingredients as **Dosa batter**. · Dosa batter stays in Ingredients, no longer linked to this recipe. (when switched off) | proposed, for cabledrawer (the second says what "Decided 2" does) |
| Lines | Ingredients · "9 lines · drag to reorder" (phone) · "9 lines · drag, or Alt+↑ / Alt+↓ to move" (computer) · Amount · Unit (none · g · kg · ml · l · tsp · tbsp · cup · pinch, and the ingredient's own sizes) · Ingredient (your words) · Note (optional), e.g. rinsed · Linked to *Toor dal* · recipe · recipe removed · Not linked · Pick an ingredient · + Add ingredient · + Add heading | mockup; "recipe removed" decided (Q29) |
| Picker | Pick an ingredient · Search ingredients and recipes · Your words stay on the line. Other names count: “thuvaram” finds Toor dal. · Ingredients · Recipes · also called: small onions · recipe · makes 200 g · + New ingredient “sam” · A new ingredient opens “How do you count it?”, with packet sizes, as on Shopping. · Done · Close | mockup |
| Picking keeps your words | Typing "sam" and picking Sambar onions keeps the line's words "sam" and shows "Linked to Sambar onions". | decided (cabledrawer 20 Oct, word for word: "2. #43: right, typing never changes my words; only picking from the list links.") |
| Picker, nothing typed or failed | Type an ingredient or a recipe. · Couldn’t search. Try again. | proposed, for cabledrawer |
| Loop guard | The server's sentences: A recipe can’t use itself. · Sambar can’t use Sambar rice, because Sambar rice uses Sambar. | decided (Q19; API 2.3) |
| Taking out | Screen-reader names: Take out of this recipe (a line) · Take out this heading · Take out step 3 · Remove tag Quick. Toasts: Took out turmeric · Took out a step (with Undo) | "Take out of this recipe" from section 1; the rest proposed, for cabledrawer |
| Moving | Screen-reader names: Move ingredient 3. Alt and the up or down arrow moves it. · Said after a move: Moved to 3 of 12 | proposed, for cabledrawer |
| Method | Method · Plain text, one step per box · Describe this step · + Add step · + Add heading | mockup |
| Delete | Delete recipe · No “Are you sure?”: you can undo it for 7 days. | mockup |
| Wren's version | Wren’s version · Saved by Wren after you opened this recipe. Your edit is still here, underneath. (phone) / untouched. (computer) · Highlighted: what Wren changed. Nothing here can be edited. · Back to my edit · Save mine anyway · "· was 200 g" · "· added by Wren" · "· taken out by Wren" · "+ 7 more lines, unchanged" · The method is unchanged. · Wren also changed: time, tags. | mockup; "taken out", "unchanged" and the last two lines proposed, for cabledrawer (the mockup says "the same as yours", which is not right for a line you changed yourself) |
| Undo of Changes not saved | That editor is already open. · Those changes can’t be brought back any more. | proposed, for cabledrawer |
| Opening | Opening the recipe… · Couldn’t load this recipe. Check your connection and try again. · That recipe isn’t here any more. | proposed, for cabledrawer |
| Saving a recipe someone deleted | That recipe isn’t here any more. (under the photo when a new photo is waiting, otherwise in a bar at the top; everything typed stays, and the unsaved photo is deleted on Cancel) | decided (cabledrawer 20 Oct, word for word: "6. #43: your placement agreed, as long as nothing typed is lost and the unsaved photo is released.") |
| Full lists | A recipe can have up to 200 lines, headings included. · …up to 100 steps… · A recipe can have up to 20 tags. · A tag can have up to 40 characters. | proposed, for cabledrawer (limits are cabledrawer's) |
| Boxes the app marks | Use whole minutes, from 1 to 14,400. · Use a number like 320 or 14.5, or leave it empty. · Say what it makes, like dosas. · Type what it is, or pick an ingredient. The server's other sentences are shown as they are. | proposed, for cabledrawer |

---

## 18. Not covered yet (for later versions of this list)

Today (when built), Plan (0.6), cook mode, import review, onboarding beyond the first account, Settings sections not built, notifications (after 1.0), and any word an error from the server uses that the app doesn't build itself. Add each with its source when it is built (the gallery and this list change in the same pull request as the screen).

## 18. Recipe import, Drafts, Privacy and swipes (0.5)

Written by Claude Code on 22 Oct from the 0.5 mockups (`Import05-*`, `Drafts05-*`, `Network-*`, `PantrySwipe-Phone`, `ShopMove-*`) and cabledrawer's 0.5 kickoff. **Every line here is "proposed, for cabledrawer"** until he approves it; the 0.5 builders add their own lines, marked the same way. Words cabledrawer decided himself are marked with his date.

- **New ingredient**, never "New food" (proposed, for cabledrawer; the old Import mockups said "New food"; section 1 already says "ingredient").
- **A line that needs you** offers: Pick an ingredient · New ingredient · Treat as staple (proposed, for cabledrawer; "Treat as staple" does what cabledrawer decided on 22 Oct, question 5).
- **To confirm:** Same as “Onions” · New ingredient (mockup; "Same as Onions" is cabledrawer's own wording, 21 Oct).
- **The photo switch:** Download recipe photos · "The recipe's main photo, kept on this server. Off: imports come without a photo." (proposed, for cabledrawer; the spec's switch name was "recipe photos").
- **Import switched off:** Importing from links is switched off (cabledrawer 21 Oct).
- **Not a web page:** This link isn't a web page. (cabledrawer 21 Oct)
- **No photo:** Photo not downloaded (cabledrawer 21 Oct).
- **The same link twice:** You already have this recipe · Open it · Import again as a copy (cabledrawer 21 Oct).
- **A draft in the list:** From bbcgoodfood.com · started by Tess · 12 days left (cabledrawer 21 Oct).
- **Toasts with Undo:** Deleted the Rava dosa draft · Undo · Moved Coriander to Lidl · Undo · Binned 1 bunch Coriander · Undo (proposed, for cabledrawer).
- **Pasted text too long** (0.5 PR 2; approved by cabledrawer 23 Oct): That text is longer than 100,000 characters. Paste just the recipe: its title, ingredients and method. (The sentence is in `backend/src/mealwright/pasted_recipe.py`, `PASTED_TOO_LONG`.)
- **Fetching a recipe page** (0.5 PR 1, `page_fetch.MESSAGES`; kept by cabledrawer 23 Oct, question 16; “switched off”, “not a web page” and “Photo not downloaded” are the lines above):
  - Not a link: That doesn’t look like a web link. Check it, or paste the recipe’s text.
  - Always blocked: Mealwright never opens links to this server itself or to cloud “metadata” addresses.
  - On your own network: That link is on your own network. An admin can allow it in Settings → Privacy, under “Your own network”.
  - An unusual port: That link uses an unusual port. An admin can allow it in Settings → Privacy, under “Your own network”.
  - Too many redirects: That link sends you on too many times. Try the recipe’s own link.
  - Can’t reach it: Couldn’t reach that site. Check the link, or try again later.
  - Too slow: That site took too long to answer. Try again later.
  - An error page: That site didn’t send the page. Check the link, or try again later.
  - Too big: That page is bigger than 5 MB.
  - Over the reading budget (0.5 PR 1; proposed, for cabledrawer; `page_budget.CANT_READ`): Couldn’t read that page. Paste the recipe’s text instead.
  - The photo’s own refusals (not a photo, bigger than 15 MB, more than 50 megapixels) reuse the upload sentences from 0.4.
- **Adding to “Your own network”** (0.5 PR 1, `own_network`; the screen is 0.5 PR 4; kept by cabledrawer 23 Oct, question 16):
  - Not a name, address or range: Type a name (wiki.home.example), an address (192.168.1.20) or a range (192.168.1.0/24).
  - Always blocked: That can’t be added: this server itself (localhost), link-local and cloud “metadata” addresses are always blocked.
  - Too wide: That range is too wide. Add a smaller one, like 192.168.1.0/24.
  - Twice: That’s already on the list.
  - A full list (the limit of 100 is decided by cabledrawer, see spec; the words kept by cabledrawer 23 Oct, question 16): The list is full: it holds up to 100 entries. Remove one first.
- **Settings → Privacy** (0.5 PR 4; every line here is proposed, for cabledrawer. Most of the wording comes from the 0.5 mockups `Network-*`, named as a source only; the code is `frontend/src/lib/privacyWords.ts`):
  - On Settings, a row under “Privacy”: Outside connections · Recipe import, recipe photos and your own network (proposed, for cabledrawer).
  - The page: Privacy · Nothing leaves this server unless you switch it on. · OUTSIDE CONNECTIONS · Recipe import from links (Visits a website only when you paste its link) · Download recipe photos (The recipe’s main photo, kept on this server. Off: imports come without a photo.) · Imports: pages up to 5 MB, web pages only, up to 5 redirects, each address checked again. (proposed, for cabledrawer).
  - Your own network: Admins only · whole server · Links to your own network (your router, other home servers, this server) are blocked, to keep them safe. Add the ones Mealwright may visit, like a home wiki. · each entry “A name / An address / A range · 256 addresses · added by Tess, 22 Oct” · Nothing added yet. Every address on your own network is blocked. · Add a name or address · e.g. wiki.home.lan or 192.168.1.20 · Each entry is a name, one address, or a range like 192.168.1.0/24. The same list is used for notifications and single sign-on later. (proposed, for cabledrawer).
  - The “Always blocked” note on that card: Always blocked, even if listed: this server itself (localhost), link-local and cloud “metadata” addresses. (cabledrawer 23 Oct, question 26)
  - Buttons: Add · Adding… · Remove (the trash icon on a phone; the screen-reader name is “Remove wiki.home.example”) (proposed, for cabledrawer).
  - Toasts, each with Undo: Added wiki.home.example to Your own network · Removed wiki.home.example from Your own network (then “Undone: …”) (proposed, for cabledrawer).
  - A member: Only an admin can change these, because they decide what Mealwright may contact (proposed, for cabledrawer).
  - Offline: You’re offline. This is as it was when you last looked, and it can’t be changed until you’re back online. With nothing loaded: Privacy needs your Mealwright server. (the existing offline card) (proposed, for cabledrawer).
  - A switch or removal that didn’t go through: Couldn’t reach your Mealwright server. Nothing was changed. · otherwise the server’s own sentence. The server’s refusal for a member is the existing “Only the household’s admin can change this.” (proposed, for cabledrawer).
  - The five refusals when adding are the ones listed above under “Adding to ‘Your own network’”, shown as the server sends them (proposed, for cabledrawer).
  - Where the import screen’s “Photo not downloaded” and “switched off” links go: `/settings/privacy#outside-connections`; the “On your own network” and “unusual port” sentences can go to `/settings/privacy#your-own-network` (proposed, for cabledrawer).
