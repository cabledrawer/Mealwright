# The word list: how Mealwright talks

**Approved by cabledrawer on 19 Oct; sections 14 to 17 approved on 21 Oct. A line still marked "proposed, for cabledrawer" waits for his OK.** Written by Claude Code on 18 Oct from the spec and the screens as they are built (0.3). Every line says where it comes from. Where the built screens disagreed with each other or with the spec, cabledrawer ruled on all twelve on 19 Oct; the rulings are in section 11. cabledrawer approves any change to this list (spec: UX — CORE → Keeping the UI good, item 1). Rulings 1 to 4 ("item", the sign-in switch, curly apostrophes, error endings) are on the screens from the 0.4 paper-cuts pull request. Some quotes in this list still show a straight apostrophe; on screen it is always the curly one (ruling 3).

**Who uses this:** builders write on-screen text from it; the checker checks every pull request's on-screen text against it (`e2e/REVIEW.md`, "Keeping the UI good"). A test already scans the web app for the word "food" (`frontend/src/lib/plainWords.test.ts`).

**Where it comes from:** `spec` = `docs/spec.md` (section or heading named); `api` = `docs/dev/api-0.2.md`; `sync` = `docs/dev/sync-protocol.md`; `review` = `e2e/REVIEW.md`; a path like `frontend/src/lib/network.svelte.ts` is the built wording.


## The list on one page (read this, then grep)

Added 25 Oct at cabledrawer's request, so checkers and builders don't read the whole list: read this page, then find the PR's own words with `grep -n -i '<word>' docs/dev/words.md`, and the section you need with `grep -n '^## ' docs/dev/words.md`. This page only repeats the rules below; where they differ, the section wins.

**The rules that apply to every screen:**

1. **Plain words, never database words.** Say ingredient (never food), cupboard/fridge/freezer (never location), use soon (never expiring), amount (never quantity), the way it's sold: packet, tub, dozen (never units), other names (never aliases), waiting changes (never queue or sync). "Item" only for shopping-list lines. Section 1.
2. **Buttons** are a verb in sentence case, no full stop; "+" starts one that adds something new; Undo is always "Undo"; "Try again" (repeat), "Try now" (reconnect) and "Try sending now" (send waiting changes) stay different. Section 5, ruling 8.
3. **Toasts** say what happened, in the past tense, with Undo; after Undo: "Undone: " and the change's own words, capital kept. Section 6.
4. **Errors** are two short sentences, what happened then what to do: "Couldn’t save. Try again." No dash, no "Please", no codes. Section 7, ruling 4.
5. **No "Are you sure?"** except signing out with unsent changes and removing a shopping-list line. Clashes are a quiet note with Undo ("Wren ticked this too"). Section 1.
6. **Curly apostrophes** (’) on screen; a no-break space between a number and its unit ("750 g"); fractions ¼ ½ ¾; "about" for a best guess. Ruling 3, section 4.
7. **Dates:** Today, Tomorrow, a weekday for the next 6 days, then "12 Nov"; "use by Mon"; the household's time zone. Section 4.
8. **Offline:** "Offline — 3 changes waiting" with "Try now", then "Back online — all saved". Section 8.
9. **"this phone" / "this computer"** follows the layout (bottom tabs or sidebar), not the device. Section 10.
10. **Empty states:** a short title, one sentence on how things get there, and the button. Ruling 10.

**Where each screen's words are:**

| Section | What |
|---|---|
| 1 | words we use and never use; the rejected list |
| 2–3 | screen names; places, shops, lists, aisles |
| 4 | amounts and dates |
| 5–7 | buttons, toasts and Undo, error messages |
| 8–10 | offline, signing in and out, phone and computer |
| 11 | cabledrawer's 12 rulings (19 Oct) |
| 12–13 | All recipes, the recipe page |
| 14 | shopping rows |
| 15–17 | recipes on a computer, Ingredients and recipes, the recipe editor |
| 18 | recipe import, Drafts, Privacy and swipes (0.5) |

A line marked "proposed, for cabledrawer" still waits for his OK.

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
- **Shopping amounts, 0.7 (F60, F61; proposed, for cabledrawer):** the amount box's small line says "The box holds the real amount: edit it, or use − / +. You can type a unit too, like 250 g."; the empty box shows a small "500 g" (or "500 ml", or "6" for something counted one by one) and a counted ingredient with no sizes shows "items" beside the box; grams typed for something counted one by one say "This ingredient is counted one by one: type a number, or change how it is counted in Edit ingredient." (`AmountBox.svelte`, `amountBox.ts`, `amountEdit.ts`). The "You can type a unit too" sentence follows the ingredient ("like 500 g", "like 500 ml", none for something counted one by one). The Add an item match row shows the amount as it will be read: "Garlic · 2 g" (cabledrawer 29 Oct: "yes"). A zero amount ("0 g butter") is Butter with no amount: the toast says "Type an amount above 0" and nothing is added (cabledrawer's words, 29 Oct).

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

- **Couldn’t + the verb + a way forward:** "Couldn’t load the pantry. Try again." · "Couldn’t load your ingredients." with a **Try again** button beside it (0.5.1; the same for "Couldn’t load the recent changes.") · "Couldn’t load this ingredient. Check your connection and try again." (`pantry.svelte.ts`, `ingredients.svelte.ts`, `foodEditor.svelte.ts`)
- **A problem toast:** "Couldn’t save. Try again." (ruling 4's own example) · "Couldn’t undo. Try again." · "Couldn’t add that shop. Try again." · "Couldn’t add it. Try again." (`save.ts`, `undo.svelte.ts`, `IngredientEditor.svelte`, `NewIngredient.svelte`; proposed, for cabledrawer: the old wording with a dash, made two sentences by ruling 4)
- **Connection:** "Can’t reach your Mealwright server. Check your connection."; with no network on the device "You’re offline. Check your connection." (`api.ts`, `downWords.ts`, cabledrawer 30 Oct). In an offline-capable place the offline wording of section 8 is used instead.
- **Anything else:** "Something went wrong. Try again." (`api.ts`)
- **Asking for the right thing in a field:** say what to type, with an example: "Enter your name." · "Choose a username." · "Use at least 10 characters." · "Use up to 50 lowercase letters, numbers, dots, dashes or underscores." · "Give the size a name, like tub or packet." · "Try something like ½ packet or 250 g." · "Use g, kg or one of its sizes, like packet." (`setup/+page.svelte`, `IngredientEditor.svelte`, `amountEdit.ts`)
- **Never a raw status code or a stack trace**; logs stay on the server and never hold what people cook, buy or type (spec section 7, Logs).

(Section 11, ruling 4: two short sentences, no dash, no "Please".) The server's own field messages follow it too: "Type a name." · "Type the shop’s name." · "Give the weight in grams." · "Enter your name." · "Too many tries. Wait 5 minutes." (proposed, for cabledrawer: the old wording without "Please"). "Please sign in again." on the sign-in page (section 9) is left as it is: it is the reason the page shows, not an error (proposed, for cabledrawer).

## 8. Offline and connection wording

All from spec principle 16 and "Offline shopping-list sync" (cabledrawer 17 to 18 Oct); built in `network.svelte.ts`, `ConnectionStatus.svelte`, `OfflineNote.svelte`, `shopping/view.ts`, `store.svelte.ts`.

- **Nothing extra while all is well.** A short blip shows nothing.
- **Bar, phone:** "Offline — 3 changes waiting" (singular "1 change waiting"), with "Try now". **Desktop:** "Offline", with "Try now", and under it "3 changes waiting. They’ll save when you’re back." In the collapsed sidebar a small dot that is also the "Try now" button. **The word follows the cause** (cabledrawer 30 Oct: "Offline" vs "Can't reach server"): with a network but no answer it reads "Can’t reach server — 3 changes waiting", and on a desktop "3 changes waiting. They’ll save when it answers again." (the second line is the lead's, proposed, for cabledrawer).
- **Back:** the toast "Back online — all saved" (short, goes by itself).
- **Shopping subtitle:** "12 to buy · saved" when connected; offline "12 to buy · offline, saving on this phone" (on a computer "…on this computer"); extra lists "Extra list · 5 · offline".
- **Chosen by the cause, the same on every page (cabledrawer 30 Oct; `downWords.ts`):** no network on the device → "You’re offline…"; a network but no answer from the server → "Can’t reach your Mealwright server…". A screen that couldn't load says it from the first failure and keeps saying it until things change (no switch when the bar comes). The second sentence of each is OK'd (cabledrawer 30 Oct: "Second sentence: OK"). A switch that couldn't be sent: "You’re offline. Nothing was changed." / "Can’t reach your Mealwright server. Nothing was changed." (Settings, Privacy; proposed, for cabledrawer).
- **A screen that needs the server:** no network: "You’re offline." then "Pantry needs your Mealwright server. Your shopping list works offline." (ruling 4; naming Pantry, Ingredients or Settings). Server not answering: "Can’t reach your Mealwright server." then "Pantry comes back by itself when the server answers. Your shopping list works offline." Both with a **Shopping** button.
- **A screen that still shows (saved copy, a sheet):** "You’re offline. Plan changes when you’re back online." or "Can’t reach your Mealwright server. Plan changes when it answers again." The same for Today, Save, "Got it and + Add work…", and Privacy and Drafts ("…it can’t be changed until you’re back online" / "…until it answers again"). "+ Add to pantry" stays visible and says "Adding to the pantry needs your Mealwright server. Try again when you’re back online."
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
- **Use soon:** "Uses spinach (today)", "Uses spinach and paneer (tomorrow)", "Uses spinach and 2 more (Mon)": ingredient names in lower case (a name with another capital in it, like "Toor Dal" or "TVP", stays as written; 0.5.1), the soonest day, in orange. If something is missing as well, it is said after: "Uses spinach (today) · all in stock but 1".
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
- Swipe left on a phone row shows a red **Remove**; tapping it asks as above. A swipe alone never removes. **Changed (F77, cabledrawer 28 Oct):** Remove after a swipe goes at once, with the Undo toast above; this keeps 0.6.0's behaviour and replaces "asks first" for the swipe. Remove from list in the amount box still asks. On a computer a bin shows when the pointer is over the row (or the keyboard reaches it); it asks as above.

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
| Lines | Ingredients · "9 lines · drag to reorder" (phone) · "9 lines · drag, or Alt+↑ / Alt+↓ to move" (computer) · Amount · Unit (none · g · kg · ml · l · tsp · tbsp · cup · pinch, and the ingredient's own sizes) · Ingredient (your words) · Note (optional), e.g. rinsed · Linked to *Toor dal* · recipe · recipe removed · Not linked · Pick an ingredient · + Add line (was + Add ingredient; mockup RecipeLines, 0.6) · + Add heading | mockup; "recipe removed" decided (Q29) |
| Picker (before 0.6; the pick-list in section 24 replaces its words) | Pick an ingredient · Search ingredients and recipes · Your words stay on the line. Other names count: “thuvaram” finds Toor dal. · Ingredients · Recipes · also called: small onions · recipe · makes 200 g · + New ingredient “sam” · A new ingredient opens “How do you count it?”, with packet sizes, as on Shopping. · Done · Close | mockup |
| Picking keeps your words | Typing "fresh coriander" and picking Coriander keeps the line's words "fresh coriander" and shows "Linked to Coriander". Words that are only the start of the name, or of one of its other names ("sam", "thu"), become the ingredient's name ("Sambar onions", "Toor Dal"), and "Linked to" isn't shown. | decided (cabledrawer 20 Oct, word for word: "2. #43: right, typing never changes my words; only picking from the list links."; the start of a name, cabledrawer 25 Oct: "When a line is linked to an ingredient (automatically or because I chose it), the line shows the ingredient's full name ("thu" → "Toor Dal") in the editor and on the recipe page. Typing alone, with no link, never changes my words (my 20 Oct rule stands for plain typing).") |
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

## 19. Plan: Week and Month (0.6 PR 3; OK'd by cabledrawer 26 Oct, see spec "UX — CORE", "Decided for the 0.6 Week and Month screens")

Written by Claude Code on 26 Oct from the mockups `Plan`, `Desktop-Plan`, `Month-Desktop`, `Month-Phone` and the spec's "Meal planner interactions". cabledrawer's own words: Meals toggles, Week | Month, "2 recipes · 590 kcal" (spec, 17 Oct).

- Header and bar: Plan · Previous week / Next week · Previous month / Next month · Today · Meals (Breakfast · Lunch · Snack · Dinner, a switch each) · Week · Month · Cook day · Its tubs · Fresh (only once there are batch cooks).
- Days and cells: MON 12 … SUN 18 · SAT · TODAY · + Add (an empty meal on a computer) · + Add dinner (on a phone, the meal's own name in lower case) · "2 recipes · 590 kcal" · "1 ingredient" · "3 things · 80 kcal" (a mix of recipes and ingredients) · Tub 2 of 4 · COOK · Cook day (phone).
- The menu (long-press or click or Enter): the meal's or thing's name, then "Mon 19 October · Dinner"; Move to… · Copy to… · Leftovers on… · Remove; then a week with ‹ › (Earlier week, Later week), a day and a meal to pick; Move here · Copy here · Plan leftovers here · Plan it here (a recipe from the tray) · Back. "Whose tub?" and "To freezer" came with Cook once (section 20).
- Drop zones while dragging: Move · Copy (Alt) · Leftovers here · Drop here (a recipe) · Drop a recipe (a day in Month).
- Add: "Add to Dinner · Monday 19 October" · Find a recipe or an ingredient · Ingredient (beside a plain ingredient) · "Type to find an ingredient, such as Fruit." · "You have no recipes yet. Add one under Recipes." · Nothing matches. · Close.
- Tray: Recipes · drag up onto a day · Find a recipe · All · Can cook now · Use soon · Collapse recipe tray / Open recipe tray · "Uses spinach" (a recipe that uses what is about to go off) · "You have no recipes yet. Add one under Recipes." · No recipes match.
- Month side panel: Batches this month · No batch cooks this month. · Empty days ahead · Every day ahead has something planned. · +2 more.
- States: Loading the plan… · Couldn’t load the plan. Try again. · "Nothing planned this week. Drag a recipe up from the tray, or press + Add." (computer) · "Nothing planned this week. Tap + Add on a day to plan a meal." (phone) · "All meals are switched off. Turn one on under Meals to plan it." · "You’re offline. Plan changes when you’re back online." (and the screen note "Plan needs your Mealwright server. Your shopping list works offline." when it was never loaded).
- Toasts (the server's own sentence, with Undo): Planned Sambar for Dinner on Mon 19 Oct · Moved Sambar from Dinner on Mon 19 Oct to Lunch on Tue 20 Oct · Copied Sambar to Lunch on Tue 20 Oct · Planned leftovers of Sambar on Lunch on Tue 20 Oct · Removed Sambar from Dinner on Mon 19 Oct · Hid Snack in the plan · Showed Snack in the plan. After Undo: "Undone: " and the same words.
- Refusals (server, 422/409): That day is too far from today to plan. · Dinner is switched off. Turn it on under Meals to plan it. · A meal holds at most 20 things. · That meal is already there. · Nothing in that meal can be copied. · A tub can only be in one meal at a time. · Pick a recipe or an ingredient to plan. · That meal has already been dealt with, so it can’t be changed here.

## 20. Cook once, eat for… and tubs (0.6 PR 4; OK'd by cabledrawer 28 Oct, see spec section 6, "Decided for Cook once and Shopping from the plan")

Written by Claude Code on 26 Oct from the mockups `CookOnce-Desktop`, `CookOnce-Phone` and their dark twins, and the spec's "Cook once, eat for…" bullets. "Cook once, eat for…" is cabledrawer's own title (kickoff step 4); the pattern names Lunches · Lunch & dinner · Dinners · I'll pick, "+ Add a tub", "+ Add a tub too", ✕, "tubs left", "Whose tub?", "To freezer" and "Fill from freezer first" are the spec's (cabledrawer 17 Oct).

- The sheet: Cook once, eat for… · "Veg biryani · cooking Sun 18 Oct · Dinner" · How many tubs? · One tub fewer / One tub more · "Recipe serves 4 · amounts × 1.5" · Spread them over · Lunches · Lunch & dinner · Dinners · I’ll pick · Who’s eating? · Everyone (and each person's name; not asked when only one person signs in) · Extra tubs go to the freezer · Prep note ("Soak chickpeas Tue night" as the hint) · Per tub: "410 kcal · 12 g protein · 6 g fibre" · "Nutrition not known for this recipe".
- Where the tubs land: "Tap a meal to add a tub, ✕ to take one out, drag to move" · "Tap a meal to move tub 2 there" · Cook · Veg biryani · Tub 2 · Take tub 2 out of Dinner on Monday 19 October · + Add a tub · + Add a tub too · Move it here · "Upma · already planned" · Later days · "Tubs 5–6 → Freezer · they’ll show in tubs left" (or Fridge) · "The pattern skips meals that already have food; you can still add a tub to one yourself. 4 of 6 placed." · Add 6 tubs to the plan · Cancel.
- Tubs on the plan: Tub 2 of 4 · Tub 2 of 4 · Wren · the cook day shows the prep note, or "Cook once · 4 tubs".
- The menu of a tub: "In the fridge · 3 days left" / "In the freezer" · Whose tub? (each person · Nobody in particular · Back) · Move to… · To freezer · Back to tubs left. A tub has no Copy to… or Leftovers on…. A planned recipe also has Cook once, eat for….
- Tubs left: Tubs left (a group in the tray and in + Add) · "Veg biryani · tub 2 of 4" · "Fridge · 3 days left" · use by today · use by tomorrow · use by yesterday · 4 days past use-by.
- Month: Fill from freezer first · "Nothing to fill: no empty days ahead, or no tubs in the freezer."
- Toasts (the screen's own words until the server answers, then the server's sentence, with Undo): Cooked Veg biryani once for 4 tubs (3 in the plan) · Put Veg biryani tub in Lunch · Veg biryani tub is Wren’s · Veg biryani tub is nobody’s in particular · Veg biryani tub: use by Thu 22 Oct · Veg biryani tub to the freezer · Put Veg biryani tub back in tubs left from Dinner on Sun 18 Oct · Filled 3 empty days with tubs from the freezer · Took Veg biryani’s tubs off the plan.
- Refusals (server): A batch can have 1 to 12 tubs. · At most 10 batches can be cooked on one day. · Only a recipe that is still there can be cooked once for several meals. · Veg biryani already has tubs from this meal. Add or move them from the plan. · Veg biryani already has 12 tubs. · Say where each tub goes, or leave it to the pattern. · There’s no freezer in your places yet. · That tub is already in the freezer. · That tub has been eaten. · Say whose tub it is, or its use-by date. · Ask for 1 to 62 days at a time.
- A tub's use-by (0.7 B1, F48; the rule "not before the cook day" is cabledrawer's, 29 Oct; the words are proposed, for cabledrawer): in the tub's menu, Change use-by date; then the heading Use by, a date box (read aloud as "Use by"), Back · Save. Toast: Changed the use-by of Veg biryani tub 2 · Undo. Refusal (server, F50): Pick a meal after the cooking, today or later. A date before the cook day: the hint Pick the cook day or later. under the box, Save off; refusal (server): A tub’s use-by can’t be before the day it was cooked.

## 21. The shopping list from the plan (0.6 PR 5; OK'd by cabledrawer 28 Oct, see spec section 6, "Decided for Cook once and Shopping from the plan")

Written by Claude Code on 27 Oct from the mockups `Shop`, `Desktop-Shop` and their dark twins. "Check you have these", "Staples this week's recipes use", "Got it", "+ Add" and "built from this week's plan" are the mockups' words (the spec: "Got it / dismiss"); cabledrawer's kickoff answer 8 sets the look-ahead at 7 days by default.

- The line above Shopping: "12 to buy · built from this week’s plan · synced with Wren" (offline: "12 to buy · built from this week’s plan · offline, saving on this phone"). It shows only when the plan made some of the lines on the main list. With another look-ahead the plan is named by its days: "built from today’s plan" (1 day) · "built from the plan for the next 10 days". Before the server has said how far it looks (offline, a moment after opening) it says "built from the plan".
- The card: Check you have these · Staples this week’s recipes use (Staples today’s recipes use · Staples the next 10 days’ recipes use · Staples your planned recipes use, while the look-ahead isn’t known) · each staple's name with the recipes that use it under it ("Sambar and Dosa" · "Sambar, Dosa and Upma" · "Sambar, Dosa and 2 more") · Got it · + Add · Dismiss staples check (the ✕: Got it for every staple on the card).
- For screen readers: "Got it, Turmeric" · "+ Add Turmeric" · "Dismiss staples check".
- Toasts: "Turmeric: got it" with Undo (then "Undone: Turmeric: got it") · "Staples check dismissed" with Undo · "Turmeric added" with Undo (Shopping's own add).
- Offline (the card stays, its buttons are switched off): "You’re offline. Got it and + Add work when you’re back online."
- Not shown: nothing planned, everything in stock, or every staple answered: the card is not there, and the line above says nothing about the plan.

## 22. Today (0.6 PR 6; OK'd by cabledrawer 27 Oct, see spec section 6, "Decided for Today")

Written by Claude Code on 27 Oct from the mockups `Main`, `Desktop-Today`, `MoveIt-*`, `CookedMeal-*` and their dark twins. "Did you cook Sambar?", "Cooked it · Didn't · Move it", "Nothing changes in the pantry until you say." and "Your kitchen is ready" with its three steps are the spec's and the mockups' (cabledrawer 17 Oct).

- Page: Today · the date ("Saturday 25 October") · + Import a recipe (computer) · tubs left · use soon · to buy · Eating today · Use soon · Find a recipe · Next cook · Sunday · Shop list · This week · Open plan · "2 meals" · "1 meal" · "Nothing planned".
- Empty parts: "Nothing planned for today" with "Plan a meal and it shows here." and the button Plan a meal · "Nothing needs using up soon."
- The card: "Yesterday · dinner" · "Fri 23 · lunch" · "Did you cook Sambar?" · Cooked it · Didn’t · Move it · "1 more meal to answer" · "3 more meals to answer".
- Cooked it sheet: "Cooked Sambar" · "Made 4 portions · as planned" · "Your pantry isn’t changed by this yet." · Any left over? · "Optional · makes tubs for later" · None · 1 tub · 3 tubs · Fewer tubs · More tubs · Fridge · Freezer · "Use by Tue 27 Oct · 2 days left" · Change · Cancel · Cooked it.
- Move it sheet: "Move Sambar to…" · "was yesterday dinner" · Quick picks · Today · Dinner · Tomorrow · Dinner · Or pick a day · Day · Meal · free · adds alongside (with the first thing there) · already done · was here · "You can undo a move." · Move to today · Move to tomorrow · Move to Wed 28 · Cancel.
- Toasts (the server's sentence, with Undo): "Cooked Sambar (Dinner on Sat 24 Oct)" · "Cooked Sambar (…) and kept 2 tubs of leftovers" · "Didn’t cook Sambar (…)" · "Moved Sambar from Dinner on Sat 24 Oct to Lunch on Sun 25 Oct".
- Offline: "You’re offline. Today changes when you’re back online. This is what was saved last time." (the screen note when never loaded: "Today needs your Mealwright server. Your shopping list works offline.").
- Refusals (server): That meal has already been dealt with, so it can’t be changed here. · That meal hasn’t happened yet. · Only a recipe can have leftovers. · There’s no fridge in your places yet. · Sambar already has 11 tubs, and a batch holds at most 12.

## 18. Not covered yet (for later versions of this list)

Today (when built), Plan (0.6), cook mode, import review, onboarding beyond the first account, Settings sections not built, notifications (after 1.0), and any word an error from the server uses that the app doesn't build itself. Add each with its source when it is built (the gallery and this list change in the same pull request as the screen).

## 18. Recipe import, Drafts, Privacy and swipes (0.5)

Written by Claude Code on 22 Oct from the 0.5 mockups (`Import05-*`, `Drafts05-*`, `Network-*`, `PantrySwipe-Phone`, `ShopMove-*`) and cabledrawer's 0.5 kickoff. Words cabledrawer decided himself are marked with his date.

**Approved by cabledrawer on 24 Oct, with three changes** (cabledrawer 24 Oct, word for word: "0.5 wording: all 50 approved, except these changes: 15: "Photo not downloaded. Photo downloads are off in Settings → Privacy. You can add your own photo later." 22: "e.g." becomes "for example"; drop the sentence "The same list is used for notifications and single sign-on later." 25: add the full stop."). Every line below, including any still marked "proposed", is approved; the three changes are made below.

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
  - Over the reading budget (0.5 PR 1; approved by cabledrawer 23 Oct; `page_budget.CANT_READ`): Couldn’t read that page. Paste the recipe’s text instead.
  - Two other pages are being read and the wait ran out (0.5 PR 3; proposed, for cabledrawer; `page_budget.BUSY`): Mealwright is busy reading another page. Try again in a moment.
  - The photo’s own refusals (not a photo, bigger than 15 MB, more than 50 megapixels) reuse the upload sentences from 0.4.
- **The import's own sentences** (0.5 PR 3; every line here is proposed, for cabledrawer; the switched-off, not-a-web-page, already-have-this, Photo not downloaded and Save lines are the ones above):
  - Nothing in the box: Paste a link or the recipe’s text.
  - A member, with the link switch off: Importing from links is switched off. An admin can switch it on.
  - The switched-off card (admin): Nothing was fetched. Switch it on in Settings → Privacy, or paste the recipe’s text instead; pasted text never goes online. · Open Settings · Paste text instead. (Member: Nothing was fetched. An admin can switch it on in Settings → Privacy. You can paste the recipe’s text instead; pasted text never goes online.)
  - A page with no recipe: That page doesn’t have a recipe Mealwright can read. Paste the recipe’s text instead.
  - Pasted text with no recipe: Mealwright couldn’t find a recipe in that text. Paste its title, ingredients and method.
  - The box: Paste a link or the recipe’s text · A link · your server visits this page once · Pasted text · nothing goes online · Read the recipe · Reading… · How it works (from the mockup).
  - The photo note under the box (from the mockup, line “Recipe photos: not downloaded. Change in Settings → Privacy”; proposed, for cabledrawer): Recipe photos: not downloaded. · Change in Settings → Privacy. It is shown only while “Download recipe photos” is off, and not at all when the server hasn’t answered yet or couldn’t be reached.
  - Offline: Importing needs your Mealwright server. Try again when you’re back online.
  - The steps (from the mockups Import05-Phone and Import05-Desktop; “Text pasted ✓” is proposed, for cabledrawer): on a phone, “Step 1 of 3” under Import a recipe and “Step 2 of 3” under Check before saving · on a computer, beside the title: 1 · Paste · 2 · Check · 3 · Save, and on the review 1 · Link pasted ✓ (1 · Text pasted ✓ for pasted text) · 2 · Check · 3 · Save.
  - The review: Check before saving · N matched · N to confirm · N needs you (1 needs you, 2 need you) · N staples · Not in your ingredients · Couldn’t read this line · Same as “Onions” · Pick an ingredient · Pick another · New ingredient · Treat as staple · Change · New staple · Name · How it’s counted (By weight, By volume, One by one) · Usually kept in (Nowhere in particular) · Save recipe (mockup) · Cancel.
  - Under a choice: “Same as” adds “red onion” as another name for Onions when you save. · Adds “red onion” as another name for Onions when you save. · Made when you save. Nothing is added to the pantry. · Made a staple when you save. It never counts towards stock.
  - Lines with no choice (cabledrawer 24 Oct, question 28: Save always works; the sentence proposed): 2 lines will be saved without an ingredient. You can link them in the recipe.
  - Photo (cabledrawer 24 Oct): Photo not downloaded. Photo downloads are off in Settings → Privacy. You can add your own photo later. (When a download was refused: Photo not downloaded — and the reason from the lines above.)
  - Left out (cabledrawer 23 Oct, question 17, the sentence proposed): 4 lines after “Tips” were left out. You can add them by hand. · 1 line after “Notes” was left out.
  - Cuts: The page had more than 200 ingredient lines. The first 200 are here. · The page had more than 100 steps. The first 100 are here. · 1 step was shortened to 5,000 characters. (2 steps were shortened to 5,000 characters.)
  - A line as written, kept in the note when the amount was picked from several: as written: 2-3 green chillies, slit
  - A size word the ingredient has no size for: the note says "1 sprig" instead of an amount.
  - The recipe page: From: bbcgoodfood.com · by Meena Raman · Source: (a typed web address shows as a link).
  - The editor's Source hint (cabledrawer 21 Oct, the sentence): A web address shows as a link you can open yourself. Mealwright never visits it.
  - Recent changes: Imported Sambar, with 2 new ingredients and 1 other name.
- **Adding to “Your own network”** (0.5 PR 1, `own_network`; the screen is 0.5 PR 4; kept by cabledrawer 23 Oct, question 16):
  - Not a name, address or range: Type a name (wiki.home.example), an address (192.168.1.20) or a range (192.168.1.0/24).
  - Always blocked: That can’t be added: this server itself (localhost), link-local and cloud “metadata” addresses are always blocked.
  - Too wide: That range is too wide. Add a smaller one, like 192.168.1.0/24.
  - Twice: That’s already on the list.
  - A full list (the limit of 100 is decided by cabledrawer, see spec; the words kept by cabledrawer 23 Oct, question 16): The list is full: it holds up to 100 entries. Remove one first.
- **Settings → Privacy** (0.5 PR 4; every line here is proposed, for cabledrawer. Most of the wording comes from the 0.5 mockups `Network-*`, named as a source only; the code is `frontend/src/lib/privacyWords.ts`):
  - On Settings, a row under “Privacy”: Outside connections · Recipe import, recipe photos and your own network (proposed, for cabledrawer).
  - The page: Privacy · Nothing leaves this server unless you switch it on. · OUTSIDE CONNECTIONS · Recipe import from links (Visits a website only when you paste its link) · Download recipe photos (The recipe’s main photo, kept on this server. Off: imports come without a photo.) · Imports: pages up to 5 MB, web pages only, up to 5 redirects, each address checked again. (proposed, for cabledrawer).
  - Your own network: Admins only · whole server · Links to your own network (your router, other home servers, this server) are blocked, to keep them safe. Add the ones Mealwright may visit, like a home wiki. · each entry “A name / An address / A range · 256 addresses · added by Tess, 22 Oct” · Nothing added yet. Every address on your own network is blocked. · Add a name or address · for example wiki.home.lan or 192.168.1.20 · Each entry is a name, one address, or a range like 192.168.1.0/24. (cabledrawer 24 Oct: "for example", and no sentence about later uses; proposed, for cabledrawer).
  - The “Always blocked” note on that card: Always blocked, even if listed: this server itself (localhost), link-local and cloud “metadata” addresses. (cabledrawer 23 Oct, question 26)
  - Buttons: Add · Adding… · Remove (the trash icon on a phone; the screen-reader name is “Remove wiki.home.example”) (proposed, for cabledrawer).
  - Toasts, each with Undo: Added wiki.home.example to Your own network · Removed wiki.home.example from Your own network (then “Undone: …”) (proposed, for cabledrawer).
  - A member: Only an admin can change these, because they decide what Mealwright may contact. (full stop: cabledrawer 24 Oct; proposed, for cabledrawer).
  - Offline: You’re offline. This is as it was when you last looked, and it can’t be changed until you’re back online. With nothing loaded: Privacy needs your Mealwright server. (the existing offline card) (proposed, for cabledrawer).
  - A switch or removal that didn’t go through: Couldn’t reach your Mealwright server. Nothing was changed. · otherwise the server’s own sentence. The server’s refusal for a member is the existing “Only the household’s admin can change this.” (proposed, for cabledrawer).
  - The five refusals when adding are the ones listed above under “Adding to ‘Your own network’”, shown as the server sends them (proposed, for cabledrawer).
  - Where the import screen’s “Photo not downloaded” and “switched off” links go: `/settings/privacy#outside-connections`; the “On your own network” and “unusual port” sentences can go to `/settings/privacy#your-own-network` (proposed, for cabledrawer).
- **Drafts** (0.5 PR 5; every line here is proposed, for cabledrawer, except the ones marked with a date, which are his; the wording comes from the 0.5 mockups `Drafts05-*`, `DraftsDeleted-Phone` and the leave sheet in `Import05-*`, named as a source only; the code is `frontend/src/lib/draftWords.ts`, `LeaveSheet.svelte` and `DraftsScreen.svelte`):
  - The leave sheet (mockup; the title "Save as draft?" is cabledrawer's, 17 Oct, as the spec records it: the mockup's "Save as a draft?" was corrected to it, cabledrawer 24 Oct): Save as draft? · You haven’t finished checking Sambar. A draft keeps your choices so far for 15 days, in Recipes → Drafts. Anyone in your household can carry on. · Save draft (Saving…) · Keep checking · Discard.
  - The same sheet for a draft that was opened and changed (**not in the mockups, my words**): Save your changes? · You’ve changed Sambar since you opened this draft. Saving keeps your choices for another 15 days. Anyone in your household can carry on. · Save draft · Keep checking · Discard changes (leaves the draft as it was).
  - The screen: Drafts · Imports your household hasn’t finished · kept for 15 days (a computer: … kept for 15 days, then deleted quietly) · Import a recipe (a computer) · Carry on · Delete · Save recipe (only when every ingredient is checked).
  - A draft in the list (cabledrawer 21 Oct): From bbcgoodfood.com · started by Tess · 12 days left. Pasted text: Pasted text · started by Wren. A computer’s table: Recipe · From · Started by · Checked · Left, then 13 days, bbcgoodfood.com, Pasted text.
  - How far: 6 of 9 ingredients checked · 3 need you (1 needs you) · All checked · ready to save · a computer: 6 of 9 · 3 need you · **No ingredients found** (a draft with no ingredient lines; mine). The mockup shows no “need you” on the Rava dosa row; here every unchecked ingredient is counted.
  - The foot of the list: Nothing here is in your recipes yet. Drafts are deleted quietly after 15 days. A computer: Anyone in your household can carry on with a draft. Nothing here is in your recipes or ingredients until it’s saved.
  - Empty (from 0.4): No drafts · When you import a recipe and leave before saving it, it waits here for 15 days.
  - Phone swipes (0.5 PR 8; colours cabledrawer 24 Oct: "blue for "Carry on" and red for "Delete", the same as Shopping"): swipe right shows Carry on (blue), swipe left shows Delete (red) and deletes at once, with the toast below. Computers keep the buttons.
  - Toast with Undo (mockup `DraftsDeleted-Phone`): Deleted the Rava dosa draft · Undo. After Undo: Undone: Deleted the Rava dosa draft (or the server’s: The Rava dosa draft is back in Drafts.).
  - At 50 drafts (spec section 6, question 9): You have 50 drafts. Finish or delete one first. (Also the answer to an Undo that would make 51.)
  - Offline: Drafts needs your Mealwright server. Your shopping list works offline. (nothing loaded) · You’re offline. This is as it was when you last looked, and it can’t be changed until you’re back online. (something loaded) · Saving a draft needs your Mealwright server. Try again when you’re back online. (on the leave sheet)
  - A draft that can’t be had: That draft isn’t here any more. (the server’s sentence, 404) · Back to Drafts · Couldn’t open that draft. Try again. · Couldn’t load your drafts. Try again. · Couldn’t delete that draft. Try again.
  - Save recipe from the list with a line that still needs a choice: That draft has ingredients that still need you. Carry on to finish it.
  - A draft whose photo was deleted before it was kept: Photo not downloaded — The photo wasn’t kept. (the draft’s own sentence is “The photo wasn’t kept.”) · A draft’s photo can’t be deleted on its own: That photo is on a draft. Delete the draft, or save the recipe.
  - A draft with an empty Name box is listed as: Untitled recipe.
  - A draft that is too big to keep (the server’s sentence, 422; it replaces “That review is bigger than a recipe can be.”, which was wrong when the choices pushed it over): That draft is too big to keep. (proposed, for cabledrawer)
  - Undo of a Save from a draft (spec section 6, question 36; the sentences are proposed, for cabledrawer): the toast is the usual Undone: Imported Sambar. The server’s own answer adds the sentence the draft’s delete already uses: The Sambar draft is back in Drafts. At 50 drafts the Undo is refused with You have 50 drafts. Finish or delete one first. (the existing sentence). If the recipe’s photo was changed since, the draft comes back with The photo wasn’t kept. (the existing sentence).
- **Swipes and "Move"** (0.5 PR 7; every line here is proposed, for cabledrawer; the toasts "Moved Coriander to Lidl · Undo" and "Binned 1 bunch Coriander · Undo" are in the line above):
  - The buttons a swipe shows: Used… (swipe right on a Pantry row or Use soon item) · Binned (swipe left) · Move… (swipe right on a Shopping row) · Remove (swipe left on a Shopping row; it goes at once with Undo, F77, cabledrawer 28 Oct). The screen-reader name adds the ingredient: "Used… Spinach", "Move… Coriander to another shop or list".
  - The "Used…" sheet (mockup `PantrySwipe-Phone`): How much Spinach did you use? · Fridge · 200 g · use by Today · ¼ · ½ · ¾ · All · Or exactly · Used · Used all 200 g · Cancel. For an ingredient counted in items: How many Eggs are left? · Or type how many are left · Save. Nothing typed: Type how much you used. · Type how many are left.
  - The Move picker (mockups `ShopMovePicker-Phone`, `ShopMove-Desktop`): Move Coriander to… · Another shop (each shop, then Any shop, with "now" beside where it is) · Another list (each other list, "Main list · 5" or "Extra list · 5", the number being what is left to buy) · Cancel.
  - On a computer, the ⋯ menu on a Shopping row ("More for Coriander"): Change amount · Move to… · Remove from list… . In the amount box on a phone: Move to… beside Remove from list.
  - Toast: Moved Coriander to Lidl (when the shop changed) · Moved Coriander to Diwali party (when the list changed), each with Undo. Then "Undone: Moved Coriander to Lidl".
  - When a move was not made, a toast with the server's sentence: That list was removed, so Coriander wasn’t moved. · That shop was removed, so Coriander wasn’t moved.
  - Quiet notes on the row (sync protocol section 8): Wren had ticked Coriander, so it wasn’t moved. (no Undo) · Wren moved Coriander to Lidl (Undo puts it back where you had it) · Tess had moved Coriander, so your change wasn’t kept. · Tess had moved this. Your tick still went into the pantry.

## 23. Import fixes and pints (0.6 PR 7; OK'd by cabledrawer 27 Oct, see spec section 6, "Import fixes and pints, decided")

Written by Claude Code on 27 Oct. The card's words are from the mockups `ImportPints-*` (cabledrawer 24 Oct: "looks good"); the Settings row is not drawn in any mockup.

- The review's card: **This looks like a US recipe** · the switch **Read its pints as US pints (473 ml)** (on) · **For this recipe only. Your setting stays UK pints.**
- Under a line that says pints: **2 pints whole milk · US pints** (or **· UK pints**).
- The hint under the ingredients: **Switch it off and the whole milk reads 1.14 L (UK pints).** and **Switch it on and the whole milk reads 946 ml (US pints).**
- Settings, a new section **Amounts**, the row **Read pints as US pints** with **A pint is 568 ml (UK). Switch on for 473 ml (US).** (off) or **A pint is 473 ml (US).** (on); for a member, **Only an admin can change this.** added; when it can't be saved, **Only the household’s admin can change this.** or **Couldn’t reach your Mealwright server. Nothing was changed.**
- A site that said no to the page (401, 403 or 429): **That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead.**



## 24. Recipe wishes, paper cuts and follow-ups (0.6 PR 8; OK'd by cabledrawer 28 Oct, see spec section 6, "Recipe paper cuts, decided")

Written by Claude Code on 27 Oct from the mockups `RecipeDelete-*` and `RecipeLines-*` (cabledrawer 24 Oct: "looks good") and the 0.6 friction sort, items 15 to 22.

- **Delete on the recipe page (mockup RecipeDelete):** the ⋯ button beside Edit (screen readers: "More for Sambar") opens a menu with **Delete recipe** (red, after a divider when other choices come above it). It deletes at once with no question; the toast says **Deleted Sambar** with Undo, and the page is Recipes. Things not built yet (Cook mode, Add to plan…) are not in the menu.
- **The pick-list under a line's ingredient box (mockup RecipeLines):** a list named **Matching ingredients** that opens as you type, on the phone and the computer. Each ingredient: its name, then **also called murungakkai · in 2 recipes** (the matching other name, or the first one) with **in 1 recipe** and, new here, **in no recipes**. Recipes come after, with **recipe · makes 200 g** (as before). Last: **+ New ingredient “dru”**. Screen readers hear "3 matches", "1 match" or "No matches" as you type. The words are the person's own until one is picked (cabledrawer 20 and 25 Oct); picking an ingredient shows its full name and a green dot on the box. **Not linked** and **Pick an ingredient** stay under a line nothing was picked for. Keys: ↓ and ↑ move, Enter picks, Esc closes and keeps what was typed.
- **The hints under the old picker are gone** ("Your words stay on the line…", "A new ingredient opens…", "Type an ingredient or a recipe."): the list says it by showing.
- **+ Add line** (was "+ Add ingredient"; mockup). Under the lines the mockup says "Typing a name you already have links it (green dot). Enter on the last box adds a new line." Not used as it is: typing never links (cabledrawer 20 Oct), so: **Pick a name from the list to link it (green dot). Enter on the last box adds a line.** (on screen under the buttons).
- **How much? for a new ingredient (friction 21):** the choices are 250 g · 500 g · 1 kg (or 250 ml · 500 ml · 1 L) when the ingredient has no sizes of its own, then Other…. Nothing new is written. Items counted one by one have no ready-made choice (their count goes in Other…).
- **Undo after a bought joined line (follow-up 9):** instead of "Nothing to put back: it has all changed again since." the server says **Nothing to put back: the line it joined has been bought, so it stays as it is.** (all of it left alone) or **Put back what could be: the line it joined has been bought, so that part stays.** (some).
- **"for example"** replaces "e.g." in the boxes of the Used sheet, the amount box on Shopping, steps, the Pantry rows and the ingredient editor.
- **Already done before this PR, nothing new:** Today in the use-by quick picks (18 Oct), packet sizes up front in "How do you count it?" (18 Oct), "is back in Ingredients" after an Undo (the server's own sentence), a new staple with no stock ("+ Staple", 18 Oct), "bought 1 pack · 1 kg (first amount)" (section 14).

## 25. Small fixes (0.7 PR B5)

- **Undo that put nothing back names the thing (F44; cabledrawer's wish 28 Oct; proposed, for cabledrawer):** **Nothing to put back for Banana bread (Mon breakfast): it has changed again since.** On the Plan the thing is the meal item and where it was; for a pantry change it is the ingredient (**Nothing to put back for Spinach: it has changed again since.**). When the change touches no single item or ingredient (a slot, a whole batch, the shopping list), the old sentence stays: **Nothing to put back: it has all changed again since.** The two joined-line sentences (section 24) are unchanged.

## 26. Importer consistency (0.7 PR C1)

- **Notes the import writes into a line's note:** **or so** (from "3-or-so cups"), **optional** (for a line under "For serving", "To garnish" or "Optional", and for an "optional:" line), **made with …** and **and cut into …** (the words stay as written), **variety** words ("less spicy variety") and the other choice after "or" ("or butter").
- **Several links pasted (Import start):** **Several links · one link at a time: only the first is read**.
- **Quarts, gallons and fluid ounces** are read like pints, with the household's pint (and "Read its pints as US pints" for one recipe); nothing new on screen. Sizes: UK quart 1136 ml, US 946; UK gallon 4546, US 3785; UK fl oz 28.41, US 29.57.
