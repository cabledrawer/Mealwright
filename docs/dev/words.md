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
- **"+ Place" (0.7, F101; cabledrawer 31 Oct: "type a new place wherever a place is picked"):** the last choice of every place picker (Add to pantry's Where, the ingredient's Lives in, a recipe import line's Usually kept in, the Put away panel's Where, the Shopping tick's Change, a packet's Move to) reads **+ Place**. It opens a small box: **New place** · **Place’s name** · **Kept cold?** with **Cupboard · Fridge · Freezer** (Cupboard first) · **Add place** · **Cancel**. A name left empty: "Type a name."; a failed save: "Couldn’t add that place. Try again."; offline or the server not answering: "A new place needs your Mealwright server. Try again when it answers." A name the household already has (any capitals) just picks that place. The words in the box and the offline sentence: cabledrawer 1 Nov, "I accept the '+ Place' box wording as written" (`NewPlace.svelte`). Renaming, reordering and deleting places stay in Settings (0.8). At 50 places: "You have 50 places, the most Mealwright keeps. Rename or remove one in Settings." (the cap and the sentence: cabledrawer 1 Nov).
- **Shops in Recent changes (F225, cabledrawer 10 Nov: adding, renaming and removing a shop are all listed, with Undo; the sentences below are accepted, cabledrawer 11 Nov):** the change lines read **Added the shop Aldi** · **Renamed the shop Aldi to Lidl** · **Removed the shop Aldi** (this one built in 0.8). An Undo that can't go ahead says: "That can’t be undone: the shop is in use now." (the shop's adding, once an ingredient or a list line uses it) · "That can’t be undone: the shop has been renamed again." · "That can’t be undone: there’s already a shop called Lidl." (the old name is taken) · "That can’t be undone: the shop is gone." (`removals.py`, `api/v1/kitchen.py`).
- Where something goes: "In the Fridge · 2 L" (the line under a ticked row, section 14), "Milk → Fridge" (the toast), "Moved Milk → Freezer".

## 4. Amounts and dates

- **Amounts are shown the way they're sold** and the arithmetic stays behind the scenes: "about 750 g · 1½ packets", "about 1.5 L · 1½ bottles", eggs "9 left · bought as a dozen" (spec Pantry; "Measure stock the way it's sold"). The server makes these strings (`display`); the screen never rebuilds them (api, "Decision: the server returns structured numbers and a ready `display` string").
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
- **A recipe's line,** each part only when known, with a no-break space inside "50 min" and "320 kcal": `50 min · 320 kcal · all in stock but 1`. Calories say "nutrition unknown", never 0. A time over 59 minutes reads in hours and minutes, "1 h", "2 h 5 min", "12 h 25 min" (F114, cabledrawer 31 Oct; `timeWords.ts`).
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
- **Not on this screen yet** (hidden, not stubbed): "Cook once, eat for…" (0.7). "Plan it" came in 0.7 (section 31). "Edit" (top right) came with the editor, PR 5, and Delete is inside the editor (section 17).

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
| A line with an amount | **In the Fridge · 2 L** | **Change** (the places, and "Different pack?" under them; cabledrawer 21 Oct: "“Different pack?” under Change is OK") (the **Undo** link was dropped in 0.8.0, cabledrawer 8 Nov: undo with the toast or by unticking) |
| A line with no amount | **Not in the pantry yet. No amount.** (amber) | **Add amount** (opens "How much?") |
| A staple | **Restocked · staples aren’t counted** | **Undo** |

- Toasts when ticking: "Milk → Fridge" with Change and Undo (as before); a staple says **Salt restocked** (cabledrawer 20 Oct); a line with no amount says "Drumsticks ticked".
- Screen-reader names for the buttons on the line (approved, cabledrawer 21 Oct): "Change where Milk went", "Add amount for Drumsticks" ("Undo ticking Milk" went with the Undo link in 0.8.0, cabledrawer 8 Nov). The line itself is a group called "Where Milk went".
- Before the server has answered (offline), the line says where the tick will go, from the line's own amount and the ingredient's usual place. Once the server has answered, it says what really went in.
- **The Put away panel (desktop; cabledrawer 20 Oct):** "Ticked items with an amount go straight into the pantry. Each ticked row says where it went." The last tick still shows beneath it with Where and Undo last tick; for a staple or a line with no amount there is no Where.

**Recent changes: a first amount (approved, cabledrawer 21 Oct)**

Giving a ticked line with no amount its first amount ("How much?" → "Different pack?") used to read "Flour: bought 1 kg · 1 pack instead of 0 g". It now reads **Flour: bought 1 kg · 1 pack (first amount)**.

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
- Days and cells: MON 12 … SUN 18 · SAT · TODAY · + Add (an empty meal on a computer) · + Add dinner (on a phone, the meal's own name in lower case) · "2 recipes · 590 kcal each" (F116) · a recipe card's small line "serves 4 · 15 min · 123 kcal each" (F116, cabledrawer 31 Oct; the serves part follows the meal's own Serves) · "1 ingredient" · "3 things · 80 kcal each" (a mix of recipes and ingredients) · Tub 2 of 4 · COOK · Cook day (phone).
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
- Toasts (the screen's own words until the server answers, then the server's sentence, with Undo): Planned Veg biryani once for 4 tubs (3 in the plan) · Put Veg biryani tub in Lunch · Veg biryani tub is Wren’s · Veg biryani tub is nobody’s in particular · Veg biryani tub: use by Thu 22 Oct · Veg biryani tub to the freezer · Put Veg biryani tub back in tubs left from Dinner on Sun 18 Oct · Filled 3 empty days with tubs from the freezer · Took Veg biryani’s tubs off the plan.
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
  - Lines with no choice (cabledrawer 24 Oct, question 28: Save always works): ~~2 lines will be saved without an ingredient. You can link them in the recipe.~~ Removed (cabledrawer 5 Nov, F152): no note; Save still works as before.
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
- **Already done before this PR, nothing new:** Today in the use-by quick picks (18 Oct), packet sizes up front in "How do you count it?" (18 Oct), "is back in Ingredients" after an Undo (the server's own sentence), a new staple with no stock ("+ Staple", 18 Oct), "bought 1 kg · 1 pack (first amount)" (section 14).

## 25. Small fixes (0.7 PR B5)

- **Undo that put nothing back names the thing (F44; cabledrawer's wish 28 Oct; proposed, for cabledrawer):** **Nothing to put back for Banana bread (Mon breakfast): it has changed again since.** On the Plan the thing is the meal item and where it was; for a pantry change it is the ingredient (**Nothing to put back for Spinach: it has changed again since.**). When the change touches no single item or ingredient (a slot, a whole batch, the shopping list), the old sentence stays: **Nothing to put back: it has all changed again since.** The two joined-line sentences (section 24) are unchanged.
- **A page that can't be opened (F86; proposed, for cabledrawer):** inside the normal frame, with the menu, never a bare "500 Internal Error". Server not answering: **Can’t reach your Mealwright server.** then **This page isn’t on this device yet. Try again when it answers. Your shopping list works offline.** No network on the device: **You’re offline.** then **This page isn’t on this device yet. Try again when you’re back online. Your shopping list works offline.** The server answers and the page still failed: **Something went wrong.** then **This page didn’t open. Try again.** Buttons: **Try again** (opens the page again) and **Shopping**.
- **Undo of a move names the thing and where it was (F81; proposed, for cabledrawer):** **Nothing to put back for Banana bread (Sun breakfast): it has changed again since.** The place is the one the meal or item was moved from. A whole meal with more than one thing is named like its Undo line (**Banana bread and 1 more**).

## 26. Importer consistency (0.7 PR C1)

cabledrawer OK'd the C1 readings on 31 Oct ("C1 readings: OK"). The UK/US quart, gallon and fl oz sizes below are the lead's numbers (proposed, for cabledrawer).

- **Notes the import writes into a line's note:** **or so** (from "3-or-so cups"), **optional** (for a line under "For serving", "To garnish" or "Optional", and for an "optional:" line), **made with …** and **and cut into …** (the words stay as written), **variety** words ("less spicy variety") and the other choice after "or" ("or butter").
- **Several links pasted (Import start):** was **Several links · one link at a time: only the first is read**; since 0.8 W4a (cabledrawer 31 Oct) see section 50.
- **Quarts, gallons and fluid ounces** are read like pints, with the household's pint (and "Read its pints as US pints" for one recipe); nothing new on screen. Sizes: UK quart 1136 ml, US 946; UK gallon 4546, US 3785; UK fl oz 28.41, US 29.57.

## 19. Check before saving, 0.7.0 (C2; proposed, for cabledrawer unless the mockup has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

From the mockups `Dark-ImportCheck07-Desktop` and `Dark-ImportSave07-Phone` (cabledrawer, 30 Oct). Words not in a mockup are marked proposed.

- **Status dot** (screen readers): Ready · To confirm · Needs you · Staple.
- **A line that is not in your ingredients:** `milk · 2 tbsp · not in your ingredients`. A line with no amount shows a chip `No amount`.
- **Chips:** the amount (`200 g`) and the note (`softened`) open **Amount · Unit · Note** and **Done**; under them: "Tap the amount or note on any line to fix what was read." A bad amount: "Type a number, like 2 or ½." (proposed).
- **Choices:** Same as “Ghee” · Pick another · New ingredient · Treat as staple (to confirm); New ingredient “Milk” · Pick an ingredient · Treat as staple (needs you).
- **Pantry keeps it by (F119, cabledrawer 31 Oct):** the choice By weight · By volume · One by one is asked as **Pantry keeps it by**, with the hint "The way you buy it: a 500 g jar → by weight. Recipes can still use spoons or cups; Mealwright converts." (the New ingredient question that was "How do you count it?", the ingredient editor's "Counted", Check's "How it’s counted"; one source, `keptByWords.ts`). cabledrawer 1 Nov: the Ingredients column heading "Counted as" becomes "Kept by"; the Undo toast "Changed how it’s counted" becomes "Changed what the pantry keeps it by". The summaries say it back the same way (cabledrawer 1 Nov): **Pantry keeps it by weight** · **by volume** · **one by one**, on a settled Check line ("… · kept in Fridge.") and on the Save sheet's New ingredient button.
- **New ingredient form:** Name · Pantry keeps it by (F119) · Usually kept in · Treat as staple (never counted) · Cancel · Done; Type a name. (cabledrawer 1 Nov); a settled line: `New ingredient: Icing sugar` with Edit and Change.
- **Shared choice (F6):** Also used for 1 more line: “icing sugar, to decorate” · Same choice as “…” above (proposed).
- **Save with unlinked lines (F4):** 2 lines aren’t linked yet · Unlinked lines can’t be counted in your pantry or added to the shopping list properly. Sort them now, or save anyway and link them later in the recipe. · LINE 1 OF 2 · New ingredient “Milk” (Counted by volume · Fridge) · Pick another · Treat as staple · Skip this line · Back to Check · Save anyway.
- **Last card of the sheet (proposed, for cabledrawer):** 2 lines left unlinked · You can save now and link them later in the recipe, or go back to Check and sort them there. · Save anyway · Back to Check.
- **Long steps (F13):** A long step (5 sentences) · Split into shorter steps · Preview: this step as 3 steps · Keep the split · Keep as one · Put the steps back as they were (proposed) · Some long steps were split into shorter ones. (proposed).
- **Photo (F29):** Show the photo of Sambar full size (screen readers; proposed, for cabledrawer) · Full size (on the photo) · Close.
- **Tab titles of that page (F86; proposed, for cabledrawer):** **Can’t reach your server · Mealwright** while the server doesn't answer, **Something went wrong · Mealwright** when it does. Until the first answer the title is just **Mealwright** and the page says nothing.
- **Method headings (F112):** a heading in the method has no number; the steps are numbered 1, 2, 3 through the whole method. Nothing new on screen.
- **A site that refused (F115; steps in cabledrawer's words, the sentences proposed, for cabledrawer):** after "That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead." three numbered steps: **Open the recipe in your browser. Tip: the page’s “Print recipe” button gives a cleaner copy.** · **Select from the title to the end of the method, and copy it.** · **Paste it here, in place of the link. Pasted text never goes online.** (screen readers: How to paste the recipe instead). The box is empty and has the cursor. No other refusal shows the steps.
- **Remove line (F105; the button is cabledrawer's word, the toast proposed, for cabledrawer):** the button **Remove line** on each ingredient line (screen readers: **Remove line: 1 cup basmati rice**); the toast **Removed “1 cup basmati rice”** with Undo, then **Undone: Removed “1 cup basmati rice”**. A long line is cut at 40 characters with “…”.
- **Split into two (F109; button cabledrawer's, the rest proposed, for cabledrawer):** the button **Split into two** on each ingredient line (screen readers: **Split into two: 4 1/2 cups water and broth**); **First ingredient** · **Second ingredient** · **Split** · **Cancel**; the hint **Each gets no amount: “4½ cups together” goes in its note.** (**Two lines, one for each.** when the line has no amount); the error **Type two different names.**; the toast **Split “4 1/2 cups water and broth” into two** with Undo. The note the reader writes on each of the two lines: **4½ cups together** (a no-break space between the number and the unit; one cup is “1 cup”, “2 cans”, “100 g”).
- **Made in this recipe (F108; the choice's name is cabledrawer's, the rest proposed, for cabledrawer):** the button **Made in this recipe** on a line that needs a choice (first, filled, when the note says “from the …” or the name is a section heading of the recipe; otherwise between Pick an ingredient and Treat as staple); on the settled line **Made in this recipe:** before the name, the right-hand label **Made here**, and the hint **Made in this recipe: saved as words only, never taken from your pantry.** with Change.
- **A lot bigger than one packet (F122, review round 3; cabledrawer 1 Nov):** "That’s more than one jar: type an amount." (the size’s own name; the answer when a ¼ ½ ¾ Full pick can’t be worked out). A packet with no size that holds more than the ingredient’s Usual size shows no ¼ ½ ¾ Full picks: only “Used some” and “type it instead”. This also covers older lots, e.g. 2 kg of rice added in grams with a 1 kg bag: no ¾ any more.

## 27. "Cooked it" deductions: API messages (0.7 K2; proposed, for cabledrawer)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

These are the sentences the server sends back (`detail`); the review screen in K3 shows them or words of its own. The ask-once questions are the existing ones (section 7).

- Cooked change in Recent changes: **Cooked Sambar (2 portions)** · **Cooked Sambar (1 portion)**.
- Cooked already: **This was already cooked on Mon 2 Nov. Undo “Cooked it” first.**
- A batch's own meal: **This meal is cooked once for several. Cook the batch instead.**
- A recipe that is gone: **Only a recipe that is still there can be cooked.**
- A choice for an ingredient that isn't in the recipe: **That ingredient isn’t in this recipe.** · chosen twice: **An ingredient can be chosen only once.** · an amount for a row with no ingredient: **There’s no ingredient to take that from.** · for a staple: **Staples aren’t counted, so nothing is taken.** · more left than there is: **That’s more than there is.**
- Eating a tub: **Ate Sambar tub** · **Ate ½ of Sambar tub** · **That tub is all eaten.** · **There’s only ¾ of that tub left.**
- A meal cooked together, in Recent changes: **Cooked Sambar and Rasam** (three or more: **Cooked Sambar, Rasam and Dosa**).
- A meal's recipes: **There’s no recipe in this meal to cook.** · **A recipe can be chosen only once.**
- Running low after cooking (the review's wording is K3's): the offer to add is not ticked; it adds one of the smallest size, else the running-low level.

## 28. "Cooked it", the review (0.7 K3; proposed, for cabledrawer unless the mockup has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

The mockups `Cooked-Desktop`, `Cooked-Phone`, `CookedMeal-Desktop`, `CookedMeal-Phone` and their dark twins have most of the words; the rest are proposed. This replaces the 0.6 sheet's "Your pantry isn’t changed by this yet." (section 22): the review is where the pantry changes.

- **Header:** *Thu 15 Oct · dinner* · **Cooked Sambar** (a meal with several recipes: **Cooked Dosa and Chutney**) · *Check what comes out of the pantry* · Cancel.
- **Tabs** (a meal with several recipes): one for each recipe, by its name; the screen reads them as *Recipes in this meal*.
- **Portions:** **Portions cooked** · *as planned* (or *recipe × 1.5*) · Fewer portions · More portions. A recipe with no Serves has no Portions cooked (nothing to scale by): **Add Serves to the recipe to scale it.** (F170, cabledrawer 7 Nov).
- **The table:** Ingredient · From · Before → after · Take · Use. A row: the ingredient, where it is (*Fridge, Cupboard*, or **Not in pantry**), *800 g → 600 g*, *−200 g*, the switch (*Take Toor dal from the pantry*). A recipe line in another unit than the pantry shows both: *Recipe says 1½ tbsp jaggery*. Instead of the ingredient: *Instead: Butter*. *nothing to take*.
- **Estimate (F106, proposed):** a small tag **estimate** on a take that was worked out by changing units (title: *Worked out by changing units*).
- **Used / Left:** **Used** · **Left** · Fewer Onions · More Onions; for an amount in g or ml, tap the amount (*Change how much*) for the box (*How much was used* / *How much is left*, in g or ml) and **As worked out**.
- **Not in the pantry:** **Not in pantry** · **Bought some — used them** (the mockup's words; the switch is off and cannot be turned on).
- **The question in the pantry's unit (F106, proposed):** **How much Jaggery did you use?** · box with *g* (or *ml*) · **Use this** · **About half** · **Skip** · **Remember for next time** (on). Too far off to be a real weight: **That doesn’t look right. Try another amount.** After Skip: *Skipped* · **Ask again**. When one number cannot settle it (cups against a count) the question is the existing one (section 7) with **Answer** · **Skip**.
- **A line with "2 cloves" in its note and no amount (F89, proposed):** **How much Garlic is 2 cloves?** with the same buttons; the answer is kept as the ingredient's size *clove*.
- **Freezer, list and recipes:** *Take from the freezer too (2 tubs)* · *Short by 200 g. Add 200 g to the shopping list* · *Running low. Add 1 packet to the shopping list* · *Make Sambar powder first?*.
- **Footer:** *3 ingredients will change* (*1 ingredient will change*, *Nothing will be taken from the pantry*) · *1 tub → Fridge* · *Nothing changes until you confirm. You can undo it from the message that follows, or from Pantry → Recent changes.* · Cancel · **Confirm · update pantry** (**Saving…**).
- **Other:** *Working out what to take…* · *Nothing in this recipe comes from the pantry.* · *Nothing in this meal comes from the pantry.* · *Staples · not counted*.
- **Where it opens:** **Cooked it** on Today's "Did you cook…?" card, on a meal eaten today that is still planned, and in the Plan's menu for a meal whose day has come.
- **Toast** (after Confirm, one Undo for the pantry and the meal): the server's sentence, e.g. *Cooked Sambar (Dinner on Sat 24 Oct)*, with Undo.
- **Refusal (server):** taking a cooked batch off the plan: **This was cooked on Mon 2 Nov. Undo “Cooked it” first.**

**K3 fix round 1 (all proposed, for cabledrawer):**
- **A confirm that fails:** **Couldn’t save “Cooked it”. Nothing was changed. Try again.** (what the first call or the meal's answer took is put back, the screen stays open). If the server goes away so that it can't be put back, each change that stayed has its normal Undo message (*Cooked Sambar (2 portions)* · Undo).
- **Too many answers:** **Too many questions at once. Answer these first, then Confirm.**
- **Counted garlic (F89):** **2 cloves is how many bulbs of Garlic?** (no count word: *…how many Garlic?*), the box says *bulbs*; ¼, ½, ¾, 1½ and 1/2 are read.
- **Refusal (server), API message:** **Bought some means Use is off, with no amount.**
- **About half** of a counted packet with no size is half of what is left (3 onions → 1½).

**K3 fix round 2 (all proposed, for cabledrawer):**
- **Undo of an older cook** leaves a size that a later cook changed, and says (with the usual "partly" words): **A later cook changed the size of a clove, so it was left as it is.**
- **A reply that was lost:** **Couldn’t reach the server. Some of “Cooked it” may be saved: check Recent changes.** Nothing is taken back then; each change that worked keeps its Undo.

## 29. Cook mode (0.7 K4; proposed, for cabledrawer unless the spec or mockup has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

The mockups `CookMode-Phone`, `CookMode-Desktop`, their dark twins and `Dark-Experimental07` have most of the words. Spec: section 6, "Cook mode timers", "Cook mode ingredients" and "Cook mode (K4)". The words marked (spec) are cabledrawer's; the rest are proposed.

- **Recipe page:** **Cook now** (spec: a main button above the ingredients). The recipe page no longer has Keep screen awake.
- **Top of Cook mode:** the cross (*Leave Cook mode*) · the recipe's name · *Step 2 of 4* (*No steps* when the method has none) · **Awake** while the screen is kept on.
- **A step:** the heading of its section above it, as a title; the step's number, big; its words.
- **Buttons:** **← Back** · **Next →** · **Show ingredients** · on the last step **← Back** and **Cooked it** (spec) when there is a meal, only **← Back** when there is none (cabledrawer 6 Nov, F155 + F156; **Not now**, then **Not cooked yet** / **Close**, are gone: the X at the top left leaves). Cook now plans the recipe first (cabledrawer 1 Nov), so it usually shows **Cooked it** too; only **← Back** shows when that planning was undone or couldn't be written, or the address names no meal. **Cooked it** is shown whenever there is a meal (it was not shown with Cook now before cabledrawer's 1 Nov decision).
- **Ingredients sheet:** **All ingredients** · **Done**.
- **A recipe with no steps:** **This recipe has no steps yet.**
- **Timers:** the words found ("10 minutes") · **Start timer** · while it runs, **Stop** · when it ends **Time’s up** and **Done** · for the screen reader *Timer finished: 10 minutes.* · on the other steps a button *Step 2 · 04:32* or *Step 2 · time’s up* · **No alarm if the phone is locked or Mealwright is in the background.** (the spec says Cook mode says so; these are the words).
- **Keep screen awake:** the switch is **Keep screen awake**; where the browser can't, it is greyed with **This browser can’t keep the screen on** (spec); when the browser says no: *Couldn’t keep the screen awake.* (from 0.4); from 0.8 on its own amber line under the progress bar, with a moon (mockup `Dark-CookStep08-Phone`, cabledrawer 6 Nov).
- **Experimental per-step ingredients:** the switch **Ingredients for each step** with the badge **Experimental** and the pink flask · under a step, below a thin divider, the guessed chips and **Guessed from the step, so it may be wrong. Fix it when you edit the recipe.** (0.8 mockup `Dark-CookStep08-Phone`, cabledrawer 6 Nov; replaces 0.7's "For this step", "Experimental · guessed" and "Wrong? Fix it when you edit the recipe.") · nothing guessed: **No ingredient guessed for this step.**
- **Leaving with a timer running:** **Stop the timer and leave?** with **Stay** and **Leave** (spec).
- **Page title:** *Cooking Sambar · Mealwright*.

**Decisions for K4 (proposed, for cabledrawer; the lead's safest choices while the maintainer is away):**
- ~~**Ingredients for each step** is remembered on this device.~~ Replaced by cabledrawer's 1 Nov decision: it is a household setting (see below).
- ~~**Cooked it** is not shown at the end of Cook mode when it was opened with Cook now (no meal in the plan to cook); only **Not now** is.~~ Replaced by cabledrawer's 1 Nov decision: Cook now plans the recipe first (see below); **Cooked it** is shown when the recipe was planned.
- Cook mode shows the recipe's own amounts, not the servings chosen on the recipe page.
- The per-step guess is made on the screen only; nothing is written when a recipe is saved.

**K4 fix round 1 (proposed, for cabledrawer):**
- **Escape** leaves Cook mode, asking **Stop the timer and leave?** first when a timer is running.
- Screen-reader names: the row of timers started on other steps is **Timers on other steps**; the row with Keep screen awake and Ingredients for each step is **Options**.

**K4 decisions of 1 Nov (cabledrawer's decisions; the words are proposed, for cabledrawer):**
- **Ingredients for each step** is a household setting: once on, it stays on for the household. Another phone sees the change the next time it opens Cook mode.
- **Member rule (cabledrawer 1 Nov: "anyone in the household can flip the per-step switch"):** any signed-in person of the household may change this one switch (it changes only what Cook mode shows); the pint in Settings stays for admins only.
- **Cook now plans first:** the notice **Planned for today’s Dinner** with **Undo** (the meal's name is the slot's; proposed), shown at the top of Cook mode (the usual toast would sit under it). After Undo the notice says **Taken out of today’s plan.** and Cook mode's last step shows only **← Back** (cabledrawer 6 Nov, F156; was **Not now**, then **Close**). When the recipe was already planned today, nothing is added and there is no notice.
- **Which meal (cabledrawer 1 Nov: "today's next meal"; the order below, changed 1 Nov after review, cabledrawer accepted on 1 Nov):** the meal today that already has this recipe and isn't cooked yet (nothing new is planned, and **Cooked it** reviews only this recipe there, not the others in that meal; cabledrawer 1 Nov); else the first meal slot that is on today, in order, with no meal at all; else the first that is on whose meal is still planned (the recipe is added to it, and **Cooked it** then reviews only this recipe); else nothing is open (every meal is cooked, "didn't cook" or moved): nothing is planned, Cook mode opens without **Cooked it**, with the line *This recipe wasn’t planned.*
- **When the plan can't be written** (offline or an error): Cook mode still opens, and one line says **This recipe wasn’t planned.**
- **When the switch can't be saved** (offline or an error): it goes back to what it was and says the existing words for a change put back: **You’re offline. Nothing was changed.** or **Can’t reach your Mealwright server. Nothing was changed.** (nothing new).

## 30. Portions, Serves, who's eating and Notes (0.7 P1; proposed, for cabledrawer unless the mockup or spec has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

Written by Claude Code on 1 Nov from the mockup `Leftovers07-Phone` (and its dark twin) and the spec's "The Plan redesign, 0.7.0" and "A "Note" plan item". cabledrawer's own words (spec, 28 Oct): "Portions", "Leftovers on…", "No portions left", "Cook more", "Add anyway", "Serves − N +", and the Note examples "eating out", "takeaway", "at Amma's".

- **Leftovers on… (a recipe with one thing in its meal):** heading "Leftovers of Veg biryani"; subtitle "Cooked Sun 18 · dinner · keeps in the fridge until Wed 21"; the portions line "Makes 6 · 2 eaten Sun · 3 tubs planned · 2 picked, only 1 left" (also "· 1 left", "· 1 picked, 0 left", "· 1 picked, none left"); the bar is read aloud as "6 portions: 2 eaten on the cook day, 3 tubs planned, 1 left"; a row is "Mon 19 · Lunch" with "tub 1 · planned" (a tub of this batch is there already), "tub 4" (picked), "last day" (the use-by day) or what else is in that meal; the hint "Only meals after the cook and before the use-by are shown. To keep it longer, send a tub to the freezer."; the button "Plan 2 tubs" (or "Plan 1 tub"; it counts tubs only, so when every ticked meal is an Add anyway it reads "Plan 1 meal" / "Plan 2 meals"); Back. Loading and failure: "Loading the leftovers…" · "Couldn’t load the leftovers. Try again." · Try again.
- **No portions left (the mockup's words):** the alert "No portions left for Wed 21 lunch." (several: "No portions left for 2 of these meals."); two choices: **Cook more** with "Makes 7 · list updates" (the mockup also says "amounts × 1.75"; that waits for the recipe's Serves in the plan answer) and **Add anyway** with "Plans it; the batch stays at 6" ("Plans them; …" for several). The picked rows then say "no portion left", "new tub" (Cook more) or "recipe for 1" (Add anyway). The button stays off until one is chosen.
- **The drop zone and the one-day picker ask too:** the dialog "No portions left" with the meal's name, the same alert ("No portions left for Wed 21 lunch."), Cook more ("A bigger batch · list updates"), Add anyway ("Plans it; the batch stays the same") and Cancel.
- **Proposed, for cabledrawer, as built:** Add anyway plans the recipe in that meal for 1 serving. A batch's cook meal with no number set shows Serves 1 (how Cook once and the shopping list count it), while other meals planned before this version show the recipe's own Serves.
- **The meal's menu:** Serves (a row with "One fewer" and "One more", and the number; with several recipes in the meal, "Sambar serves"); Who’s eating? (Everyone · each person's name; not asked when only one person signs in, as in Cook once).
- **Notes:** "+ Note" (in + Add, beside the search box); the box is read aloud as "Note" with the hint "Eating out, takeaway, at Amma’s"; quick notes "Eating out" · "Takeaway"; Add note · Back; a note's card says "Note" under its text, and "1 note" / "2 notes" in the meal's total. A note has Move to… · Copy to… · Remove; no Serves, no Leftovers on….
- **Toasts (the server's own sentence, with Undo):** Planned leftovers of Veg biryani on Lunch on Wed 21 Oct, … · Set Sambar for 6 on Dinner on Mon 19 Oct · Changed who is eating Sambar (Mon dinner) · Planned At Amma’s for Dinner on Sat 24 Oct.
- **Refusals (server):** No portions left. (shown by the sheet itself, not as a toast) · That’s after this batch’s use-by date. (cabledrawer 2 Nov) · Tick at least one meal. · A meal is ticked twice. · Only a recipe can have leftovers. · A note has no leftovers. · Only a recipe has a number of servings. · A note can be up to 200 letters. (cabledrawer 2 Nov) · Pick a recipe, an ingredient or a note to plan.

## 31. The Plan: Both · Eat · Cook, Plan it, earlier days (0.7 P2; proposed, for cabledrawer unless the spec or mockup has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

Written by Claude Code on 1 Nov from the mockups `PlanEat07-Phone`, `PlanCook07-Desktop` and `PlanCook07-Phone` (and their dark twins) and the spec's "The Plan redesign, 0.7.0". cabledrawer's own words (spec, 28 Oct): the switch **Both · Eat · Cook**; "2 tubs from Thu · Tess, Wren"; **You cook today →**; "fresh meals and batches, how much (× scale, makes N, eat N now, where each tub goes, spare tubs), prep ahead, still to buy"; **Start cooking**; **Plan it** ("pick the day and the meal").

- **The switch:** a group read aloud as "Show" with **Both** · **Eat** · **Cook** (spec order, on the phone and the computer; the phone mockup draws Eat · Cook · Both). Both opens first on a computer, Eat first on a phone; the choice is kept on this device. It is there in the Week, not the Month.
- **Eat:** each day's card heads **Today · Sat 17** or **Sun 18**, with **1,730 kcal each** (the mockup says "1,730 kcal"; "each" follows F116, proposed) or, on a day with a cook, **You cook today →** (cabledrawer's words, on today) / **You cook this day →** (proposed, on any other day; the mockup says "today" on a Sunday). A row is the meal's name (**Breakfast**, **Lunch**…), the dish, and under it where it comes from: **fresh** (at the right, for a recipe cooked for that meal) · **Freshly made · Tess, Wren** (the cook day of a batch) · **Tub from Sun · Tess** · **2 tubs from Thu · Tess, Wren**. Names are the people ticked as eating (or the tub's own person); nobody is named when the meal is for everyone. An empty meal is **+ Add dinner**. The row opens the usual menu (read aloud as "Dinner: Veg biryani. Open menu").
- **Cook:** a day's card heads **Today · Sat 17** / **Sun 18** with **1 thing to cook · 30 min** / **2 things to cook · 2 h 5 min** (the mockup's words). An entry has a tag, **Fresh · Breakfast** or **Cook · Batch · Dinner**; the dish; **Serves 2 · 30 min** (fresh) or **Makes 6 · cook × 1.5 · 1 h 35 min** (a batch; "cook ×" is the mockup's); for a batch the chips **Eat 2 now** · **Tub → Mon lunch** (the desktop mockup's words) · **+ 1 spare tub** / **+ 2 spare tubs** (the phone mockup's; it opens the meal's menu, which has Leftovers on…); then **Prep ahead: soak the rice** (the batch's prep note; the mockup says "Prep tonight:", proposed) and **Still to buy: saffron, mint** (the mockup's words; what the recipe still needs that isn't in the pantry). The button is **Start cooking**, read aloud as "Start cooking Veg biryani". A meal already cooked says **Cooked** instead. A week with nothing to cook: **Nothing to cook in these days.** (proposed).
- **Beside the days (wide windows):** **This week’s cooking** with **batches** (or **batch**) · **N portions**, **fresh meals** (or **fresh meal**) and **at the stove** with the time (proposed; the mockup also lists "Tubs left over", which waits for the Leftovers screens).
- **Earlier days:** on a list (the phone, Eat, Cook, and any window under 1100 px) the days before today are folded behind **Earlier this week (3 days)** (cabledrawer's words, 31 Oct, spec: Plan views and cards, for **Earlier this week (3 days)**; the singular **1 day** is proposed, for cabledrawer), and **Hide earlier days** when they are open (proposed). The week's dates are said once, in the arrows (**12 – 18 October**), not again above the title.
- **Plan it** (recipe page): the button **Plan it** beside **Cook now**; it opens the Plan's own picker (**Plan it on…**; the next 14 days from today in two rows of seven, no week arrows; the meals, **Plan it here**, **Back**), and cabledrawer's words (spec, 31 Oct) are "offers the next 14 days and shows what's already planned at each meal". Each meal button for the chosen day shows what is in it (the names joined with ·) or **Nothing yet** (proposed); a day with something planned has a dot and is read aloud with **Something planned** (proposed), then the toast the server words, **Planned Sambar for Dinner** with **Undo**. When the plan can't be read: **Couldn’t load the plan. Try again.** (existing).

## 32. The Plan's cards: COOK and EAT, moving by keyboard, tray, F49, F65 (0.7 P3; proposed, for cabledrawer unless the spec or mockup has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

Written by Claude Code on 1 Nov from the mockup `PlanCards07-Desktop` (and its dark twin) and the spec's "The Plan redesign, 0.7.0" and "Moving plan cards with the keyboard". cabledrawer's own words (spec, 28 Oct): **COOK** and **EAT** cards, "Take off this meal (keep the tub)", "Eat it on… [the next free meal]", **Before the cook day**.

- **Cards in Both:** a COOK card says **Cook · 1 h** (the recipe's time; **Cook** alone with none) and, under the name, **Makes 6 · 4 tubs** (the mockup's words). An EAT card says **Eat**, **Eat · tub 2 of 4** or **Eat · last tub** (the mockup's), with the people's names in white chips. A fresh meal says **Fresh · 15 min** (the mockup's) with the usual small line after "Fresh · " (serves, time, kcal each: F116). The card is read aloud as "Chana masala (cooking), Thu 15 October · Dinner. Open menu" / "(eating)" (proposed); a tub as "Chana masala tub, …".
- **Before the cook day:** an EAT card of a tub that now comes before its batch is cooked has an amber outline and the line **Before the cook day** (cabledrawer's words); read aloud as ", before the cook day".
- **Cooking can only move to an empty meal.** (toast and the server's own refusal; cabledrawer 1 Nov): shown when a COOK card is dropped on a meal that is already planned. **A COOK card in a meal with several things moves the whole meal** (cabledrawer 1 Nov).
- **Moving with the keyboard:** under **Move to…** / **Copy to…** the picked place is said as **Move to Tue 20 October · Dinner** / **Copy to …** (proposed), and on a computer a hint line: **Arrow keys pick the day, Shift and arrow keys pick the meal, Enter confirms, Esc cancels.** (proposed; the spec's own words are the keys). The box is read aloud as "Pick the day and the meal with the arrow keys".
- **F49:** the tub's button **Take off this meal (keep the tub)** (cabledrawer's example), not red, with the line **The tub stays in the fridge, in Tubs left.** / **… in the freezer, …** (proposed). The toast stays "Put Chana masala tub back in tubs left from …" (the server's words).
- **F65:** in "Any left over?" with tubs picked: **Eat it on…** with **Not planned yet** first and then the next free meals, as **Sun 18 · Breakfast** (proposed); a tub that was chosen goes to that meal when Confirm is pressed.
- **P3 follow-up (proposed, for cabledrawer, apart from cabledrawer's 2 Nov sentence at the end):** the three gaps use words that already exist: Undo of a cook-meal move after the batch was cooked says **This was cooked on … Undo “Cooked it” first.** (as the forward move does), and a tub moved, or chosen by hand in Cook once, after its use-by says **That’s after this batch’s use-by date. (cabledrawer 2 Nov)** Moving the cooking earlier, when a tub planned later would then be past its use-by, is refused with **Can’t move it earlier: a tub planned later would be past its use-by.** (cabledrawer 2 Nov).

## 33. Month and day: up to 3 a day, a click on any day, Fill from freezer first (0.7 P4; proposed, for cabledrawer unless the spec or mockup has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

Written by Claude Code on 1 Nov from the mockup `Month07-Desktop` (and its dark twin) and the spec's "The Plan redesign, 0.7.0" (Month and day, P4). cabledrawer's own words (spec, 28 Oct): "A full Month day shows up to 3 items, then "+N more"", "Filled Tue dinner, Thu lunch from freezer tubs (they run out soonest)", "The day sheet lists the oldest freezer tub first", "fridge tubs past their use-by aren't offered", **Cook once here**.

- **A day in Month:** its number, **Today** and **COOK** (existing), up to three chips (the cooking first), then **+2 more** (cabledrawer's words; it opens the day). A day always shows up to three (cabledrawer 2 Nov); on a short screen the month scrolls. The whole day is one button, read aloud as **Add to Thursday 5 November** (the existing words). The tray under the Month is gone (the day's sheet offers recipes and tubs).
- **The day's sheet** (the existing **Add to the plan**, headed **Dinner · Thursday 5 November**, or **a meal · Thursday 5 November** before a meal is picked): the meals, the search **Find a recipe or an ingredient** (existing), **+ Note** (existing) and, new, **Cook once here…** (the mockup's words).
- **Use a tub** (the mockup's heading; it was "Tubs left"): the freezer tub that runs out soonest first (cabledrawer 2 Nov: "oldest" means use-by order), then the fridge tubs; every fridge tub still in date is always listed; when more than twelve, **+4 more tubs** (proposed) lists the rest; each as **Palak paneer · tub 1 of 2** with **Freezer · 4 months left** (existing words). When a fridge tub was left out: **Fridge tubs that are past their use-by by then aren’t offered.** (the mockup's words, with a curly apostrophe).
- **Cook once here…:** pressing it shows **Pick the recipe to cook once here.** (proposed) and the recipes only (no tubs, no ingredients, no note); the button now reads **Back** (proposed). Picking a recipe plans it in the chosen meal and opens **Cook once, eat for…** (existing); if it cannot be planned the toast says why, and if Cook once cannot open: **Planned Pongal, but Cook once didn’t open. Open its menu to try again.** (proposed).
- **Fill from freezer first** (existing button), its Undo toast now says which meals and why: **Filled Tue 3 dinner, Thu 5 lunch from freezer tubs (they run out soonest)** (cabledrawer 2 Nov: it names the dates); for one tub **Filled Tue 3 dinner from a freezer tub (it runs out soonest)** (proposed); with more than six meals the first six are named and the rest counted: **Filled Mon 2 dinner, Tue 3 dinner, … 6 more from freezer tubs (they run out soonest)** (proposed). The toast's button says **Undo all** (cabledrawer 2 Nov, the mockup) and takes back every meal it filled; after it, "Undone: " and the same words.

## 34. Paper cuts (0.7 PC1, PC2; proposed, for cabledrawer unless the spec has the words)

**OK'd by cabledrawer 2 Nov** (with his two changes: "That’s after this batch’s use-by date." and "A note can be up to 200 letters.").

Written by Claude Code on 2 Nov from the spec's "Paper cuts" (cabledrawer 28 Oct) and "Server down (F67)" (cabledrawer 30 Oct). cabledrawer's own words are marked.

- **The editor's draft line (cabledrawer 28 Oct: "Carrying on where you left off", with a **Start over** link):** the line **Carrying on where you left off** and the link **Start over**, at the top of New recipe and Edit recipe after a reload, in the calm grey note (not a warning).
- **Duplicate:** the menu choice **Duplicate**, first in the recipe page's ⋯ menu, above **Delete recipe** (proposed). The copy is named **Sambar (copy)** (cabledrawer 28 Oct) and opens in the editor; a name already taken (by a recipe, or the made-ahead ingredient) gives **Sambar (copy 2)**, **Sambar (copy 3)** and so on (proposed). If it can't be made, the toast is the server's sentence, or **Couldn’t duplicate. Try again.** (proposed).
- **Server down, in "+ Add to pantry" and on the import screens (cabledrawer 30 Oct: "Server down → "Can't reach your Mealwright server. Try again when it's back."; device offline → keep the offline wording."):** with a network but no answer from the server: **Can’t reach your Mealwright server. Try again when it’s back.** With no network on the device the old sentences stay: **Adding to the pantry needs your Mealwright server. Try again when you’re back online.**, **Importing needs your Mealwright server. Try again when you’re back online.** and **Saving a draft needs your Mealwright server. Try again when you’re back online.** In the "+ Add to pantry" sheet, an ingredient that can't be loaded says **You’re offline. Check your connection.** (device offline, the existing sentence) or the server-down sentence above (proposed).
- **Unchanged:** "Try now" (the bar), "Back online — all saved", **Couldn’t save. Try again.**
- **SECURITY.md** (not on screen): says the database and backups are not encrypted in 0.7, and that disk encryption on the server is the owner's choice (cabledrawer 28 Oct).

## 35. Check screen: change the method (0.7 F111; proposed, for cabledrawer unless the spec has the words)

Written by Claude Code on 2 Nov from the spec's "Import Check (PR A4)" (F111, cabledrawer 31 Oct: "tap a step to change its text, remove a step or heading, with Undo; nothing saved until he chooses"). Every word below is proposed, for cabledrawer.

- **A step or a heading is a button** (tap, click, Enter or Space). Screen readers: **Change step 3: Fry the onion.** for a step; a heading keeps its own words as its name and has the hint **Change heading** (its tooltip). It opens a text box (screen readers: **Words of step 3**, **Words of heading**) with **Done** and **Cancel**. Enter is Done, Escape is Cancel (Shift+Enter makes a new line in a step).
- **An empty step or heading can't be kept:** **A step can’t be empty. Write something, or remove it.** (heading: **A heading can’t be empty. …**), with **Remove step** (or **Remove heading**) beside Done and Cancel.
- **Remove** on each step and heading (screen readers: **Remove step 3**, **Remove heading: For the filling**). The toast **Removed step 3** or **Removed “For the filling”** (a long heading is cut at 40 characters with “…”) with Undo, then **Undone: Removed step 3**. Undo puts it back in its place. The step numbers follow, and a heading takes no number (F112).
- **Unchanged:** **Nothing is saved until you choose.**, **Split into shorter steps**, **Put the steps back as they were**.
- **Put the steps back as they were** (after Split into shorter steps) is a reset: it also drops any step edits and removals made since (cabledrawer 2 Nov).
- **An open box stays open** when another step is removed, split or put back by Undo: the words typed are kept, and Done changes the step the box was opened for. The box closes only when its own step is gone (removed, split, or Put the steps back as they were) (cabledrawer 2 Nov).
- **Done keeps the change with no Undo toast** (Cancel is the way back before Done); Remove has Undo (cabledrawer 2 Nov).
- **An Undo that can't find where the step was** (the steps around it are gone) puts nothing back and says **Couldn’t put it back: the steps have changed.** (cabledrawer 2 Nov). Put the steps back as they were also drops the Undo of steps taken out before it.

## 36. Restock dates, "How much?" and navigation (0.7 K5, N1, F113; proposed, for cabledrawer unless the spec has the words)

Written by Claude Code on 2 Nov from the spec's "Restock dates, "How much?", navigation (K5, N1)" and F113 (cabledrawer 28 Oct and 31 Oct). cabledrawer's own words are marked; everything else is proposed, for cabledrawer.

- **The staple's chip on Pantry (cabledrawer 28 Oct: "Restocked 12 Oct"):** a second small line under the name, **Restocked 12 Oct** (day and month, the household's own day). The one case the spec doesn't say: on the day itself it reads **Restocked today** (cabledrawer 2 Nov). A staple never restocked has no line.
- **The Ingredients column (cabledrawer 28 Oct: "Restocked 3 weeks ago", with the date on hover or tap):** under **Staple**, **Restocked 3 weeks ago**. The steps (proposed): **today**, **yesterday**, **2 days ago** to **6 days ago**, **1 week ago** to **4 weeks ago**, **1 month ago** to **12 months ago**, then **1 year ago**, **2 years ago**. Hover shows the whole date (**12 Oct 2026**); a tap on the words shows it in their place (**Restocked 12 Oct 2026**), a second tap puts them back. On the phone the row's quiet line reads **Staple · Restocked 3 weeks ago · Cupboard**, and the date is in the editor.
- **The ingredient editor, for a staple only (proposed):** a heading **Restocked**, a date field (read out as **Date restocked**; it stops at today), and a button **Restocked** (cabledrawer 28 Oct: "tapped "Restocked""; it sets today as the day, the same save as the date field). A typed date is saved when the field is left or Enter is pressed; one that is not a whole day, from before 2000 or after today is put back unchanged. Both are off while offline. Under them: **Restocked 3 weeks ago · 12 Oct 2026**, or **Not restocked yet. Ticking it off the shopping list or tapping Restocked sets the date.** The Restocked tap's toast, and Undo's, say **Salt restocked** (as the shopping tick's already does). The date field's toast says **Salt restocked 12 Oct**.
- **Refusals (proposed, for cabledrawer; two short sentences each):** **That date is in the future. Pick today or an earlier day.** · **Salt isn’t a staple. Make it a staple first.** · **Pick a date.** · **That date is too long ago. Pick a day in 2000 or later.** (refusing a date before 2000: cabledrawer 2 Nov)
- A typed date is shown even when a Shopping tick is newer; a tick made after it wins again (cabledrawer 2 Nov).
- **"How much?" (cabledrawer 28 Oct):** the ingredient's own sizes first; with none, weight **100 g · 250 g · 500 g · 1 kg**, liquid **250 ml · 500 ml · 1 L**, counted **1 · 2 · 6 · 12**, then **Type an amount**; for counted things the sheet says **Pantry gets 6 items.** (cabledrawer 2 Nov: picking 6 adds 6 and makes no new "pack of 6" size) (the old last choice **Other…** stays on "What did you buy?" / **Different pack?**, where the line has an amount). The spec writes the litre as "1 l"; the screens already write **L** (**2 L**, section 4), so these do too (proposed).
- **"+ New recipe" (cabledrawer 28 Oct: "Add by hand · Import from a link"):** the button keeps its name **New recipe**; it opens a small choice with two items, **Add by hand** and **Import recipe** (cabledrawer 5 Nov, F146: was **Import from a link**; the page takes pasted text too).
- **Import in the Recipes section (cabledrawer 31 Oct, F113: "All recipes · Import · Drafts · Ingredients"):** the sidebar item and the phone button are both **Import**. The page it opens is still called **Import a recipe**. The **Import a recipe** link on the Recipes list is gone.
- **Settings (cabledrawer 28 Oct, F2):** a cog after the name (sidebar foot) and beside the avatar (phone page header). The link's name is unchanged (**Tess · Settings**); the cog has no words of its own.
- **The version (cabledrawer 28 Oct: "Mealwright 0.7.0"):** small grey text **Mealwright 0.7.0** at the foot of the sidebar (not when it is collapsed) and at the bottom of Settings on the phone. **cabledrawer 7 Nov:** the version is shown exactly as the tag, **Mealwright v0.8.0-alpha.1** (then v0.8.0-beta.1, v0.8.0-rc.1, v0.8.0), not Python's 0.8.0a1; the server's own version is unchanged.
- **The phone's switch (cabledrawer 28 Oct, F76: "Pantry · Ingredients"):** two links at the top of the Pantry tab, **Pantry** and **Ingredients**, in a box named (for screen readers) **Pantry or Ingredients**. The Pantry tab opens the one chosen last.

## 37. After the v0.7.0-beta.2 re-test (cabledrawer 5 Nov)

All cabledrawer's (5 Nov); no longer proposed.

- **Check on the phone (F141, 0.7 PR #126):** (1) Settings → Appearance: **Checking a recipe on the phone** on every screen size, with "On a computer, Check always shows the whole list."; kept on this device. (2) The Focus heading **Check before saving**. (3) Focus puts the ingredients first, the method after. (4) A line that matched shows **ok**. (5) **See all** (One at a time) switches to Focus. (6) When nothing needs you and there's no method: **Nothing to check here. Press Save recipe, or See all to look at the whole recipe.** (7) The X's spoken label **Close (kept in Drafts)**. (8) When the draft can't be kept, Close offers the leave sheet's **Discard** / **Discard changes**.
- **Check waits for an open step box (F143):** on Focus, One at a time and the computer, Save recipe, Close, See all, Back, Next and Discard (Cancel on the computer) wait while a method step's edit box is open. No new words.
- **No "without an ingredient" note (F152):** removed from Focus, One at a time and the computer.
- **"+ New recipe" (F146):** **Add by hand** · **Import recipe**. The import page keeps its heading **Import a recipe** (cabledrawer 5 Nov: "agreed"; it doesn't name links).
- ~~**Cook mode's last step (F147):** **← Back** · **Not cooked yet** · **Cooked it** when opened from a meal; **← Back** · **Close** when there is no meal.~~ Replaced by cabledrawer's 6 Nov decision (section 38).
- **"Cooked it" and a tub (F125):** **Cooked it is saved, but the tub isn't planned. {reason} It stays in Tubs left.** A folded Recent changes row names only the first dish. When another login moved the tub, Undo's message stays the general one.

## 38. After the v0.7.0-beta.3 re-test (cabledrawer 6 Nov)

All cabledrawer's (6 Nov); no longer proposed.

- **Cook mode's last step (F155, F156):** **← Back** · **Cooked it** (the wide one) when opened from a meal; only **← Back** when there is no meal (Cook now's planning undone or not written, or nothing open). No **Not cooked yet** and no **Close**: the X at the top left (**Leave Cook mode**) leaves, nothing marked, nothing taken, and still asks **Stop the timer and leave?** (Stay · Leave) while a timer runs. The two buttons share one row on every screen size.

## 39. A meal with several recipes, cooked one at a time (F157, cabledrawer 6 Nov)

All cabledrawer's (6 Nov); no longer proposed.

- The toast and Pantry → Recent changes name only what that press cooked. Toast: **Cooked Beta3 Test Lentil Soup (Breakfast on Fri 6 Nov)**; Recent changes, as for any cook (line in section on the Cooked change): **Cooked Beta3 Test Lentil Soup (2 portions)**. Never **Cooked Khichdi and 1 more (…)** when only the soup was cooked. Two recipes cooked in one press: **Cooked Sambar and Rasam (…)**; three: **Cooked Sambar, Rasam and Rice (…)**.
- The Plan and Today show **Cooked** on each recipe that has been cooked; the other recipes of the meal keep **Start cooking**. The meal itself reads as cooked only once every recipe in it has been.
- A cooked recipe in a meal not yet all cooked can't be moved, removed or have its servings changed (F157 security pass; also when it was cooked as a Cook once batch). Plan sheet hint: **This was cooked. Undo “Cooked it” to move or remove it.** Dragging it on the Plan: **This was cooked. Undo “Cooked it” first.** (both proposed, for cabledrawer). The server's answer is the batch one: **This was cooked on Fri 6 Nov. Undo “Cooked it” first.**
- Today, a meal cooked in parts: a quiet line under it naming what is done, **Cooked Lentil Soup** (the same wording as the toast's start). Replaced in 0.8 by F160 (cabledrawer 6 Nov): one line per recipe, a tick and **Cooked** on each cooked one, a filled **Cooked it** on each one still to cook.
- Today's "Did you cook Khichdi and 1 more?" card still names the whole meal when part of it is cooked; the review it opens lists only what is left. cabledrawer 6 Nov: yes, leave as is.

## 40. Settings: the section list, Meal slots, Shops & places, Recent changes (0.8 S1; cabledrawer 7 Nov)

- **Section list (mockup Dark-Settings08-Desktop):** **Appearance · Amounts · Meal slots · Shops & places · Recent changes · Privacy · Sign-in**, and under it **Household, Your data and About come in 0.9.** (the mockup's line). Meal slots is hidden from everyone but admins.
- **Shops (mockup):** **Shops** · *In the order you visit them. Shopping groups the list by shop in this order.* · **+ New shop** · **Add** · *Removing a shop moves its ingredients to “Any shop”, with Undo.* (the mockup uses straight quotes; curly here, rule 6). Toast: **Removed the shop Supermarket** with **Undo**.
- **Places at home (mockup):** **Places at home** · *Where things are kept. Each kind tells Mealwright how long things last there.* · the kinds **Fridge**, **Freezer**, **Cupboard** · **+ New place** · *A place with things in it can’t be removed until they’re moved: Mealwright says how many and offers “Move them to…”.* · Toast: **Removed the place Cupboard** with **Undo**.
- **A place with things in it (cabledrawer 7 Nov):** **Cupboard has 14 things in it. Move them to…** (one thing: **has 1 thing in it**) with a picker named **Move them to** and the button **Move and remove** and **Cancel**.
- **The last Fridge and the last Freezer (cabledrawer 7 Nov):** the Remove button is greyed out, with the note **Mealwright needs at least one Fridge and one Freezer.**; the server's own words if it refuses anyway: **Mealwright needs a fridge, and Fridge is your last one, so it stays.**.
- **Meal slots:** a line **Switch a meal off to hide it from the plan. Hidden meals keep what’s planned.**; **+ New meal** · **Add**; the switch is named **Show Lunch in the plan**. Toasts: **Renamed Lunch to Midday meal** · **Changed the order of the meals** · **Hid Snack in the plan** / **Showed Snack in the plan**, each with **Undo**. Server words: **There’s already a meal called Dinner.** · **A household can have at most 12 meals.** · **Only the household’s admin can change this.**.
- **Moving and renaming rows:** the buttons are named **Move Aldi up**, **Move Aldi down**, **Rename Aldi** and **Remove Aldi**; the rename box is **Name of Aldi** with **Save**. Server words: **There’s already a shop called Aldi.** · **There’s already a place called Cupboard.** (the last is the existing 0.7 wording).
- **Recent changes (F172, cabledrawer 7 Nov):** one list of every kind of change, newest first, each with **Undo** while it can be undone. **Show more** for older ones. Empty: **Nothing yet. Changes show here, with Undo for 7 days.**. **Couldn’t load the recent changes.** · **Couldn’t load more changes. Try again.** · **Try again**. Pantry and Ingredients no longer have a Recent changes list or button.
- **Loading failures in Settings:** **Couldn’t load your meals.** · **Couldn’t load your shops and places.** each with **Try again**; when the server can’t be reached, the usual **Can’t reach your Mealwright server. Check your connection.** with no button, and the list loads again once the connection is back.

## 41. Pack sizes and where to buy (0.8 S2, F120, F121; cabledrawer 7 Nov)

- **Shopping line, Usual size known** (mockups Dark-ShopInShop08-Phone, Dark-ShopPlan08-Desktop): **1 jar (500 g) · 120 g needed**; several packs: **2 tins (400 ml) · 600 ml needed**. Number and word with a no-break space.
- **Shopping line, no size:** **60 g needed · no pack size yet**; the quick picks are headed **Usual pack?** (desktop: **Usual pack for Tamarind?**) and read **200 g**, **500 g**, **1 kg** (the screens come in S3 and S4).
- **Ingredients, Pack column** (mockup Dark-IngredientsPack08-Desktop): heading **Pack**; the Usual size **jar · 500 g**; another size **+1** (title and tap: **Also: tin · 1 kg**); none **Add a pack**, then **Common sizes:** with the sizes and **Other…** (opens the editor). Phone: the same, on a line under the name. A staple shows its pack the same way (**bag · 5 kg**), and nothing when it has none.
- **Toast after a tap:** **Tamarind: added Pack = 500 g** (the server's own words), with Undo.
- The table's word is the size's name (jar, bag); with no table row the size is named **pack**.

## 42. Plan shopping (0.8 S3, F59; proposed, for cabledrawer unless the mockup or spec has the words)

- **Title (1100 px and wider):** **Plan shopping** (under 1100 px: **Shopping**, as before). The line above is today's: "14 to buy · built from this week's plan".
- **Row, why it is there:** the planned recipes and their days, **Sambar (Tue, Thu) · Rasam (Fri)**; **Added by you** for a typed item; **120 g needed** first when the pack bought is bigger than the need; **no pack size** last on a planned item with no Usual size; **From the plan** when the plan no longer explains a line (proposed). Days are Mon, Tue, Wed, Thu, Fri, Sat, Sun.
- **Quick picks:** **Usual pack for Tamarind?** then **200 g**, **500 g**, **1 kg** (mockup).
- **Right column:** panels **Shops** (link **Manage**; chips **All · 14**, **Supermarket · 9**, **+ New shop**; hint **⋯ on a row moves it to another shop.**), **Check you have these · 4** with **Show** / **Fold**, **In the trolley · 2** with **Clear ticked** and a ✕ on each row (**Clear Yoghurt**). New shop box (proposed): field **Shop name**, button **Add shop**.
- **Make it a staple?** (cabledrawer 7 Nov): a small button on a row; after the tap the toast says **Cornmeal is now a staple** (proposed) with Undo.

## 43. Shopping on the phone, in the shop (0.8 S4, F117, F134, F173; proposed, for cabledrawer unless the mockup or spec has the words)

- **Add box (mockup Dark-ShopInShop08-Phone):** under the best match, **Add as bought** with the line **Straight into the pantry · 1 jar (500 g) → Cupboard** (the pack is left out when none is known; the place is the ingredient's usual one, else the household's first cupboard place, whatever it is called; no place shown if it has none). Not offered for an ingredient already on the list (its own row has the tick). The toast after it says where it went (**Ghee → Cupboard**) with Change and Undo; one Undo takes back the tick and the add.
- **How many? (F134, proposed):** a counted ingredient with no usual size asks **How many mangos?** (plural, lower case; F197, cabledrawer 8 Nov: "How many lemons?") with **1 · 2 · 6 · 12**, **Another number**, **Add** and **Cancel**, before it is added (also before **Add as bought**).
- **Swipe right on a row (mockup):** **Already have it** and **Move…**. Swipe left on a row: **Remove** (as before); on a line in the trolley: **Clear**. The amount box has **Already have it** beside **Move to…** for a keyboard and a screen reader.
- **The sheet (mockup):** **How much Ghee is at home?** · **It comes off the list and goes into the pantry as found at home, not bought.** · choices **1 jar (500 g)** (the list's amount, or the pack) · **½ jar** · **¼ jar** · **Other…** (a box: **How much is at home**, hint **250 g**; unreadable: **Type how much, like 250 g.**, proposed) · **Where** · **Put 1 jar in the pantry** · **Cancel**. With no amount on the line: the ingredient's own sizes, else **100 g · 250 g · 500 g · 1 kg**, **250 ml · 500 ml · 1 L**, **1 · 2 · 6 · 12**.
- **The change (cabledrawer 7 Nov, in the brief):** the toast and Pantry's Recent changes say **Found Ghee at home: 1 jar → Cupboard** (a Recent changes row starts with the verb **Found**).
- **In the trolley, one line (mockup):** tick mark · name with its amount under it (**2 × 200 g**, **6 · found at home**, **Planned 6**) · the place as a button, **→ Fridge ▾** (tap to choose another place). A line with no amount has **Add amount** in the button's place; a staple says **Restocked · staples aren’t counted**. Most recently ticked first (F173). On the phone the line ends with a ✕ button, spoken as **Clear Ghee**, that clears just that line (as swipe left does). The line's old **Undo** link is gone: unticking the box takes the tick back, and the toast keeps its Undo.
- **Row under a name with no pack size:** **60 g needed · no pack size yet** (mockup), then **Usual pack for Tamarind?** with **200 g · 500 g · 1 kg** (S3's words), on the phone too. **Make it a staple?** on the phone too.
- **Amount box, no amount yet (F60, proposed):** a row of quick amounts (**1 packet** and the other own sizes first, then **250 g · 500 g · 1 kg**, **250 ml · 500 ml · 1 L**, **1 · 2 · 6 · 12**) that fill the box.
- **Different pack? (F153):** the choice that is what was bought starts selected, so the planned amount can be chosen again; nothing new on screen.
- **N1 also covers Already have it (proposed, for cabledrawer):** when someone else removed or moved the line before the find was sent, the finder gets the same note as for a tick: **Wren had removed this. Your tick still went into the pantry.** And the note **Paneer is counted differently now, so nothing went into the pantry.** (N8) is sent when the ingredient is now counted another way.

## 44. Starter ingredient packs (0.8 R4; proposed, for cabledrawer unless the spec has the words)

- **Button on Ingredients (phone and computer):** **Add a starter pack**. The dialog is headed **Add a starter pack**, then **{Pack} starter pack** (**Indian starter pack**) once one is picked.
- **The seven packs:** Everyday basics · Indian · Chinese · Japanese · Middle Eastern · Household · Baking. Each button: the name, then **123 ingredients · 12 already here**.
- **First line:** "Pick a pack. You’ll see its ingredients first and can untick any. Only ingredients are added, never anything in your pantry or on your list." The Household pack adds: "These are added as “Don’t count it”: always assumed to be in stock."
- **The list:** every ingredient ticked; **3 of 120 ticked** with **Untick all** / **Tick all**; a row already in the household is greyed, unticked and says **Already have** (**Already have as “Thuvaram paruppu”** when it has it under another name).
- **Buttons:** **Back**, **Cancel**, and **Add 41 ingredients** (**Add 1 ingredient**); off when none is ticked.
- **Toast and Recent changes** (the server's words): **Added the Indian starter pack: 41 ingredients**, with Undo (one Undo for all of them).
- **Nothing new:** "There’s nothing new to add: you already have these ingredients."
- **A pack where every row is Already have:** "You already have every ingredient in this pack." (cabledrawer 7 Nov)
- **While loading and if it fails:** **Loading…**; "Couldn’t load the starter packs." (or the server's own words), with **Close** and **Try again** (cabledrawer 7 Nov)

## 45. Pantry and Use soon (0.8 S5, F64, F66, F78, F79, F131; proposed, for cabledrawer unless the mockups or spec have the words)

- **Use soon (both screens):** **Use soon · 6**, **Recipes that use them** (phone: **Recipes that use them →**), **Show all 6** / **Show fewer**; the phone shows 3 rows, the computer 4 cards. Rows say the place and amount: **Fridge · 2 packets**. The phone's hint: "Swipe a row: right for Used, left for Binned." (the mockup's words).
- **Dates on a row** (mockups): **Use by Sun** (phone), **use by 12 Nov** (a place card), **best before 1 Nov**; a passed Use by is red, **Use by passed: don't eat**; a passed Best before is grey, **Best before passed · probably fine** (spec line, cabledrawer 7 Nov). Under either, how long ago: **Passed 3 days ago** (the mockup), and, proposed, **Passed yesterday** for one day.
- **Buttons:** **Used…**, **Binned**, **To freezer**. A passed Use by lists Binned first.
- **Too late to freeze (cabledrawer 7 Nov):** once a Use by date has passed (from the day after), **To freezer** is greyed out, with the note "Too late to freeze: the use by date has passed." (on a Use soon row and in a packet's menu); on the Use by day it works, and Best before food can always be frozen. The server's refusal says the same words. A leftover tub past its date is the same (cabledrawer 8 Nov): **To freezer** greyed out with the same note, in the Plan's tub menu.
- **A tub in Use soon (cabledrawer 7 Nov: "Leftover tubs: yes, add them to Use soon as the mockup's “Eat it on…” card"):** **Lemon rice** · **Fridge · 2 tubs** · **Use by Tue**, one button **Eat it on…**. Its sheet (proposed, for cabledrawer): title **Eat Lemon rice on…**, one button per free meal, as in "Any left over?" (**Today · Lunch**, **Tomorrow · Dinner**, **Monday · Dinner**), only up to the tub's use-by day; **Cancel**; "Looking for free meals…" while loading; "Couldn’t load the plan. Try again."; "No free meal before its use-by day." (all proposed, for cabledrawer). The Undo toast says **Put Lemon rice in Dinner** (proposed). A passed tub shows **Use by passed: don’t eat** (the same words as a packet) and has one button, **Binned** (cabledrawer 8 Nov), not Eat it on…. It throws away the card's soonest tub; the toast and the Recent changes line say **Binned <recipe> tub**, e.g. **Binned Lemon rice tub** (cabledrawer 8 Nov), with Undo. Refused: "That tub is all eaten." (nothing left; proposed, for cabledrawer); "That tub is planned for a meal. Take it out of the meal first." (in a meal; cabledrawer 8 Nov).
- **How much is left (cabledrawer 8 Nov; replaces every "under …" wording):** counts to the nearest ½, packs to the nearest ¼, as before. **less than half an onion** ("less than half a/an <word>"), **less than half left**, **½ onion** stays; with a weight or volume the amount comes first: **about 50 g · less than ¼ packet**, **about 63 g · ¼ packet**, **about 100 g · less than ¼ bag**, a whole number of packs **1 kg · 2 packets** (cabledrawer 8 Nov: yes, amount first there too; the shopping sheet's **Pantry gets 1 pack · 400 g.** stays pack first, cabledrawer 8 Nov); **a tiny amount** for under 0.1 g; **3 ml** stays. Short forms (pack part only): **less than ¼ packet**. On a Shopping line with no count word, **less than half needed** (cabledrawer 8 Nov).
- **A tub that went into a meal meanwhile (Eat it on… refused):** "That tub is already planned for another meal." (cabledrawer 8 Nov; replaces "That tub is already in a meal. Look again."). It shows as a toast and the card is looked at again.
- **Pantry place cards:** one line per ingredient; **3 more** under a card (proposed; the mockup has "3 more"); tubs show as **Lemon rice · 2 tubs · use by Tue**, or **¾ tub** for one part-eaten tub.
- **The ingredient editor:** **Date on the packet** with **Use by** / **Best before**; for meat, fish and chilled dairy (milk, cream, yoghurt, cheese, paneer) the choice is off and says "Meat, fish and chilled dairy are always Use by." (cabledrawer 7 Nov); every other ingredient can be switched. Recent changes: **Homemade pickle is now Use by** (proposed). Refused: "Homemade pickle is always Use by: it can't be switched to Best before." (proposed). After a switch, the toast says **Date is Use by** or **Date is Best before** (proposed).
- **How much?** (mockup): **¼ · ½ · ¾ · All**, nothing chosen until one is tapped; the one main button says **Choose how much** (off; proposed), then **Used ¾ bag**, **Used all of it**, or, with no pack name, **Used ¾ of it** (proposed); **Or exactly … g** turns it into **Used 120 g**; **Cancel**.
- **A packet with no date in its menu** says **no date** (was "no use-by date"; proposed).
- **A row with no use-by date (F201; "found at home today" is cabledrawer's, 8 Nov; the other days follow "bought", proposed, for cabledrawer):** it says how the stock got there and when: **bought today / bought yesterday / bought Mon / bought 20 Oct** for stock from Shopping, and **found at home today / found at home yesterday / found at home Mon / found at home 20 Oct** for stock found at home while shopping, typed in with Add to pantry, or counted in a stocktake.

## 46. Stocktake (0.8 S6, F118; proposed, for cabledrawer unless the mockup or spec has the words)

- **The button** on Pantry's header (phone and computer): **Stocktake**.
- **The screen** (mockup Dark-Stocktake08-Phone): **Stop, carry on later**; **Place 3 of 5**; title **Stocktake · Cupboard**; under it, **How much is there? A best guess is fine. 4 of 9 done here.**
- **Per ingredient:** the picks **None · ¼ · ½ · ¾ · Full**; a staple says **A staple: not counted. Restocked 3 Nov.** (just "A staple: not counted." when it was never restocked); the button **It’s a staple** (the mockup's straight apostrophe is curly on screen); a counted ingredient has **−** and **+** (read out as "One fewer" and "One more").
- **Pack size asked once** (mockup): **no pack size yet**, **What does it come in? Asked once.**, the common sizes (**200 g**, **500 g**, **1 kg**), **Other…**; proposed: **Use this size** for the typed one. Once there is one, the ¼ ½ ¾ Full picks work.
- **More packets** (proposed): with a pick chosen, **More bags besides this one** with − and + (the pack's own plural: "More packets besides this one").
- **Something else** (mockup): **+ Something else in the Cupboard**; the box is "Find an ingredient to count in the Cupboard" (proposed).
- **Moving on** (mockup): **← Fridge** and **Next: Spice rack →**; on the last place **Finish** (proposed).
- **The end** (proposed): **Stocktake finished**, "Every place is counted. The pantry shows what you said.", **Back to Pantry**, **Start a new stocktake**. A load that fails: "Couldn’t open the stocktake. Try again."
- **Recent changes** (spec, cabledrawer 7 Nov: "recorded as stocktake"; the words proposed): **Stocktake: Toor dal ½ bag in the Cupboard**, **Stocktake: no Toor dal in the Cupboard** (None), **Stocktake: Sambar powder is a staple in the Cupboard**, **Stocktake: Tamarind pack is 500 g** (the pack size asked once). After Undo: "Undone: " and those words.
- **Round 1 additions (proposed):** a counted row reads **2 tins** (the ingredient's own word; just the number when it has none). Screen-reader names: **Common sizes for Tamarind**, **Tamarind: size of one pack**, **One more bag** / **One fewer bag**, **Tamarind: more packets**, **Tamarind: how many**, **¼ left**, **Ingredients in the Cupboard**. The "+ Something else" box says **e.g. toor dal**. When adding, going back or going on cannot be saved: **Couldn’t save. Try again.** (the app's usual words).
- **Round 2 (cabledrawer 7 Nov; words proposed):** a row whose pack word is "tin" is counted whole, with − and + and **2 tins** (**1 tin**), and its small line reads **tin · 400 g · counted**; no new sentence. **Next** (and **Finish**) records the rows not answered as checked and correct, with no words and no entry in Recent changes.

## 47. Undo of added ingredients (0.8 U1; cabledrawer 7 Nov)

- **Some stay** (cabledrawer 7 Nov): **Took out what could be: 3 ingredients are already in use, so they stay.** One: **Took out what could be: 1 ingredient is already in use, so it stays.**
- **All stay** (cabledrawer 7 Nov): **Nothing to take out: these ingredients are already in use.**
- Shown in the Undo toast and after Undo in Recent changes. "In use" is a recipe line, the plan, the shopping list, the pantry, or a staple someone has checked or restocked. Nothing in use: the usual **Undone.** The same for the ingredient made with a new shopping-list item when its add is undone (the list item still goes).

## 48. Counts of an ingredient counted one by one (0.8 FR2, F197; cabledrawer 8 Nov: "How many lemons?", "Bought 2 lemons")

- **After its number the ingredient's name is lower case and plural when there is more than one** (cabledrawer 9 Nov: the app's own plural rule for size names and count words, "packet" → "packets"): **Bought 2 lemons → Cupboard**, **Used 2 onions**, **Binned 1 onion**, **Used ½ onion**, **Added 5 onions → Cupboard**; the question **How many lemons?**. A name that already ends in "s" (Eggs, Chickpeas) is left as it is. An ingredient with its own count word keeps it (**5 slices of Bread**), and a pack keeps its own words (**1 box Eggs**).
- The sentences are made by the server, so Recent changes and the Undo toast ("Undone: …") say the same.
- **Add as bought for a brand-new name (F196, cabledrawer 9 Nov):** under **+ New ingredient: “name”** a second line, **+ New ingredient, as bought: “name”**; it asks the same questions (**Pantry keeps it by**, **How many name?**), then the ingredient is added and ticked at once. It never joins a line still to buy: it goes into the trolley as its own line (cabledrawer 9 Nov).
- **One trolley row per ingredient (F198, cabledrawer 9 Nov):** lines of the same ingredient are one row; the line under the name joins their amounts (plain numbers add up: **2**; otherwise **200 g + 1 packet**). Unticking, Change place and Clear act on every line of the row, with one toast and one Undo for the whole row, the same as Clear (cabledrawer 9 Nov); Clearing one joined row says **Cleared 1 ticked item** (the rows the person saw, not the lines; the wording is the existing Clear one).

## 49. Settings on the phone, the count line, and small fixes (0.8 FR3: F177–F181, F191–F195; cabledrawer 8–9 Nov; the row values are proposed, for cabledrawer)

- **Phone Settings, grouped list (F193; words from the mockups `Dark-Settings08-Phone` and `Dark-SettingsSlots08-Phone`):** group names **You · Kitchen · Household**; rows **Appearance · Amounts** (You), **Meal slots · Shops & places · Recent changes** (Kitchen), **Privacy · Sign-in** (Household); under the list **Household, Your data and About come in 0.9.**; a section's page has **‹ Settings** above its title. The Settings screen itself stays "Settings".
- **The value on each row (proposed, for cabledrawer):** Appearance shows the theme choice (**Auto**, **Light** or **Dark**); Amounts shows **UK pints** or **US pints** (the mockup said "As written", which is not a setting that exists); Meal slots shows **3 on**; Shops & places shows **2 shops · 4 places** (**1 shop · 1 place**); Privacy shows **All off**, or **2 on** for how many outside connections are switched on; Recent changes and Sign-in show none. A value is left out until the server has answered.
- **The count line (F194):** unchanged words, on their own line under the title on the phone: **121 ingredients · shared by recipes, pantry and shopping** (Ingredients), **23 ingredients · 8 use soon** with "8 use soon" in the use-soon colour and the **Stocktake** button at its right (Pantry).
- **Pack toast (F179):** keeps the pack cell's own words for the whole time it shows: **Butter: added block · 250 g**, after Undo **Undone: Butter: added block · 250 g**. Recent changes keeps the server's own sentence ("added Block = 250 g").
- **Spaces (F181, F192):** **134 ingredients · 31 already here**; **…offers “Move them to…”. Mealwright needs at least one Fridge and one Freezer.**

## 50. Import, several links (0.8 W4a, F110; cabledrawer 31 Oct)

The words marked agreed are from the mockup `Dark-ImportLinks08-Phone` (cabledrawer); the rest are proposed, for cabledrawer.

- **Over the box and the list (agreed):** **N links · one after another** (N is the number of links; on the box's chip and as the list's heading).
- **Each row (agreed):** the recipe's name (the last word of the link until it is read), the site, then **· in Drafts** once kept; **✓ All matched** · **Needs checking** (cabledrawer 11 Nov; was ✓ Ready to check) · **Reading…**; a failed link shows the server's own sentence and **Paste text**.
- **Waiting row (proposed, for cabledrawer):** **Waiting** for a link not yet reached.
- **Under the list (agreed):** **Each recipe goes to Drafts to check and save later. If one link can’t be read, the rest carry on. You can leave this screen.** and **Only Mealwright’s server fetches these pages, and only because Recipe import is switched on in Settings.** (curly apostrophes on screen) · button **Go to Drafts**.
- **The box's button (proposed, for cabledrawer):** **Read the recipes** for several links (**Read the recipe** for one); **Reading…** while it works.
- **A link already imported (proposed, for cabledrawer):** **You already have this recipe. It was not read again.**
- **Close with no connection, in Check (F174; cabledrawer 7 Nov, spec "Decided for 0.8.0"):** a toast, **You’re offline: changes since then won’t be kept** (curly apostrophes on screen), then Close leaves for Recipes.
- **Several links, round 1 (proposed, for cabledrawer):** a paste reads up to **20** links and no more than Drafts has room for (50 in all). Under the list, **3 more links were left out. A paste reads up to 20 links, and Drafts has room for 2 more.** (the last part only when Drafts' room is under 20). When Drafts fills up part-way the rest say **Not read: Drafts is full. Finish or delete a draft first.**; when importing from links is switched off they say **Not read: importing from links is switched off.** The same page typed two ways (capitals in the address, a trailing slash, a "#" part) is read once.
- **The limit, before pasting (F208; cabledrawer 10 Nov: the screen says how many links can be pasted at once; the sentence is accepted, cabledrawer 11 Nov):** under the box, **You can paste up to 20 links at once. Mealwright reads them one after another.** (20 is `MOST_LINKS` in `importLinks.svelte.ts`; `ImportStart.svelte`).
- **Round 2 (proposed, for cabledrawer):** when Drafts has no room at all, nothing is read and the box says **Drafts is full: none of the 3 links were read. Finish or delete a draft first.** (one link: **Drafts is full: the link was not read. Finish or delete a draft first.**). When the Check screen's code can't be fetched (a dropped connection), the page keeps its heading and says **Couldn’t open the Check screen. Try again.** with **Try again**.

## 51. Tags: one row and Manage tags (0.8 W4b; cabledrawer 9 Nov)

Words from the mockup `Dark-RecipesTags08-Phone` are agreed; the rest are proposed, for cabledrawer.

- **Sheet title and count (agreed):** **Manage tags** · **9 tags** (**1 tag**).
- **Each row (agreed):** the tag, then **14 recipes** (**1 recipe**); a tag that is spelt like another also says **· looks like South Indian**. Buttons **Rename** and **Merge into…** (Merge into… is the main button on a look-alike row).
- **Asking before a merge (agreed):** **Merge “south-indian” into “South Indian”? Its 3 recipes get “South Indian”, and “south-indian” goes. You can Undo.** · **Cancel** · **Merge**.
- **The button on Recipes (proposed, for cabledrawer):** **Manage tags**. In the sheet: **Save** and **Cancel** when renaming, **Close**, **Merge “x” into** over the choice of tag, **No tags yet. Add one to a recipe and it shows here.**
- **Refused rename (proposed, for cabledrawer):** **There’s already a tag called South Indian. Use Merge into… to join them.** The rename is refused, not turned into a merge.
- **After a merge (agreed in the mockup's note; the toast is the app's usual one):** **Merged tag south-indian into South Indian** with **Undo**; the same line is in Settings → Recent changes. After Undo: **Undone: Merged tag south-indian into South Indian** (the server's own message: **south-indian is back, on the recipes that had it.**). Undo refused when a tag with the old name exists again: **There’s already a tag called south-indian. Rename or merge it first.**
- **A rename is not in Recent changes (proposed, for cabledrawer),** as a shop's or a place's rename isn't.
- **Undo of a merge (proposed, for cabledrawer):** it takes the other tag off exactly the recipes that only got it from the merge, even if someone has since added it to them by hand. A tag that no shown recipe has never blocks a rename or this Undo; it is folded in without a message.

## 52. Optional ingredients and steps (0.8 R3, F151; cabledrawer 6 and 9 Nov; the mockup words `Dark-RecipeOptional08-Phone` and `Dark-PlanOptional08-Phone` are agreed, the rest is proposed, for cabledrawer)

- **On the recipe page (mockup):** a line has an **Optional** pill beside its amount; a step has **Optional step** on its own line above its words. Nothing else about a line or step changes.
- **The nutrition note (mockup, link renamed):** **Nutrition possibly out of date: the ingredients changed since it was worked out.** with the link **Update nutrition** (cabledrawer 10 Nov; it was "Work it out again" in the mockup). It shows only when an ingredient line changed after the figures were typed or read from a page, and never for a recipe with no figures. *Proposed, for cabledrawer:* the link opens the recipe's editor with the nutrition boxes first (Mealwright doesn't work nutrition out from ingredients: "Nutrition calculated from ingredients" is under "Not in v1"); Save there clears the note. In the editor, under the five boxes: **The ingredients changed after these were worked out. Check them, change what is wrong, then Save: that clears the note.**
- **The recipe editor and Check (proposed, for cabledrawer):** an **Optional** switch under each ingredient line (its accessible name **Optional: ingredient 3**) and **Optional step** under each step (**Optional: step 2**); on Check, a line's switch is **Optional** and a step's is **Optional step**, and a step that is Optional shows the **Optional step** pill in the list. "(optional)", ", optional" and "optional: " in a line, and a line under "For serving", "To garnish" or "Optional", switch the line on and the word is taken out of its note; "(optional)" or an "Optional:" label in a step does the same for the step.
- **The question when a recipe is added to the plan (mockup):** title **Mutton biryani · Sat dinner** with **Serves 6** under it; **This recipe has 2 optional ingredients. Will you use them?**; each line is its name with **2 tbsp · not in the pantry** or **½ tsp · in the cupboard** under it and a box to tick; **Ticked ones go on the shopping list if you need them and come out of the pantry when you cook. You can change this from the meal later.**; buttons **Add to plan** and **Cancel**. *Proposed, for cabledrawer:* with one: **This recipe has 1 optional ingredient. Will you use it?**; the other pantry words **in the pantry** (no place), **a staple**, **not enough in the pantry**; every line starts ticked; changing it from the meal: the meal's menu has **Optional ingredients…** (with the recipe's name when the menu holds several), the same sheet opens with the button **Save**, the toast says **Changed the optional ingredients of Mutton biryani on Sat dinner**.
- **Refusals (proposed, for cabledrawer):** **That ingredient isn’t optional in this recipe.** and **Only a recipe has optional ingredients.**

## 53. Steps that wait (0.8 M1, F124; cabledrawer 31 Oct and 9 Nov; the mockup words `Dark-CheckWait08-Phone` and `Dark-RecipeMethods08-Phone` are agreed, the rest is proposed, for cabledrawer)

- **The time (mockup):** **45 min active · plus 4 h – overnight marinating** (the recipe page says "45 min active" beside Serves and the wait after it; lists and cards say it in their line; Check shows it under the Minutes box). Without active time: **4 h – overnight marinating**. A recipe whose steps wait for different things says **waiting** ("plus 3 h waiting"). A recipe that has no wait, including every recipe made before this, keeps its single time ("12 h 25 min"). On a plan card and in the tray and the Add sheet the short form: **45 min + 4 h – overnight**.
- **The length (mockup):** "4 h – overnight", "overnight", "8 h – 12 h", "90 min" (the same time words as everywhere: no-break space, "1 h 30 min").
- **A step that waits (mockup):** on the recipe page a chip under the step, **Marinate · 4 h – overnight**; on Check the same chip with **To confirm** beside it and the three answers **Yes, it waits · Change · No wait**.
- **The kinds (proposed, for cabledrawer):** Marinate · Soak · Ferment · Rest · Chill · Prove; in the time line: marinating, soaking, fermenting, resting, chilling, proving.
- **Change (proposed, for cabledrawer):** boxes **Waiting for** (the kind), **Length** (**Shortest** when a longest is typed), **Longest (if it varies)**, **In** (minutes, hours, days) and the switch **Ends overnight**, then **Done**, which keeps the wait as confirmed. Refusals: **Type how long it waits, such as 4 hours.** and **The longest can’t be shorter than the shortest.**
- **No wait (proposed, for cabledrawer):** takes the wait off with the toast **Took off the wait** and Undo.
- **The recipe editor (proposed, for cabledrawer):** under each step a line **Waits** with **+ Add a wait** (accessible name **Add a wait to step 2**); once there is one, the boxes above and **Take off the wait**. The boxes' accessible names are **Shortest wait for step 2** and **Longest wait for step 2**.
- **What the reader suggests (proposed, for cabledrawer):** from the step's own words: marinate, soak, ferment, rest, chill/refrigerate, prove, with a length after the word of 30 minutes or more or "overnight" ("marinate for 4 hours or overnight", "ferment 8–12 hours", "soak overnight"). Shorter ones are part of the step ("rest 5 minutes").
- **Heading:** a heading never waits (`422`: A heading has only words.).

## 54. Whole packs and another size (0.8 W4c, F183 + F204; cabledrawer 8 and 9 Nov; the mockups Dark-ShopPacks08-Phone and Dark-ShopPackAlt08-Phone are agreed, everything else is accepted as built, cabledrawer 10 Nov)

- **Row, usual size known (mockup):** **1 packet · 1 kg · Sambar needs 2 tsp**; on the list itself the pack line is as since 0.8: **1 pack (750 g) · 12 g needed** (number and word with a no-break space).
- **Row, no usual size (as before, marked):** **12 g needed · no pack size yet** with **Usual pack for Salt?** and the common sizes.
- **Another size under the row (mockup):** **Or 3 tins · 200 ml: nothing left over** with **Use this**; with some left over, **Or 2 cartons · 1 L: 500 ml left over**. Read aloud as the group **Another size for Coconut milk**. Suggested only when it leaves at most half as much over as the usual size, saves at least a tenth of the need and is no more than 6 packs.
- **The sizes sheet (mockup):** heading **Coconut milk · 600 ml needed**, **Sizes sold in UK shops**, a choice per size with its name line **2 tins · 400 ml** and under it **Your usual · 200 ml over** / **400 ml over** / **Nothing over**, tags **On the list** and **Least left over**, the switch **Make the one I pick my usual size**, **Use this**, **Cancel**. Opened by **Which size?** in the amount box (opened by tapping the amount, phone and computer) or **Which size?…** in the row's ⋯ menu (*cabledrawer 10 Nov*: the mockup taps the row, but the row's name already opens the ingredient, and a separate button keeps the touch target).
- **Problems:** **Couldn’t load the sizes. Try again.** · **Couldn’t change the size. Try again.** · offline with a size to be made: **A new size needs your Mealwright server. Try again when it answers.**
- **A quarter or half of an amount in Already have it:** two figures with "about" when that changed it: **about 63 g** (never 62.5 g), as the "How much is left" rule.


## 55. Two cooking methods (0.8 M2, F107; cabledrawer 31 Oct and 9 Nov; the mockup words `Dark-CheckWait08-Phone`, `Dark-RecipeMethods08-Phone`, `Dark-CookMethod08-Phone` and `Dark-CookNextA08-Phone` are agreed, the rest is accepted as built, cabledrawer 10 Nov)

- **Cook mode's question (mockup, cabledrawer's):** **How are you cooking it today?**, each way with its name and **45 min active · 3 steps · last time** (the way used last says "last time"), the note **Steps, timers and the time follow your pick. You can switch on the first step.**, and the main button **Start · Stovetop**.
- **On the first step (cabledrawer 10 Nov):** under the step count the way picked and **· switch** (**Instant Pot · switch**), which opens the question again; on later steps the way's name is shown quietly.
- **NEXT (mockup, option A, cabledrawer 9 Nov):** a quiet line at the bottom of a step, **NEXT** over the next step's words, with the next step's wait chip (**Marinate · 4 h – overnight**) when it has one. None on the last step.
- **The recipe page (mockup):** a switch of two buttons, **Stovetop · 45 min** and **Instant Pot · 30 min**, under the title; the ingredients, the steps and the time follow the one pressed.
- **The recipe editor (cabledrawer 10 Nov):** **+ Add a second way of cooking it**; then a switch between the two, **Name of this way of cooking it**, the note **The time, ingredients and steps below are for this way of cooking it.** and **Remove this way of cooking it**. Refusals: **Name this way of cooking it, like Stovetop.** / **…like Instant Pot.**, **The two ways of cooking it need different names.**
- **When a recipe is added to the plan (cabledrawer 10 Nov):** the sheet **Chicken curry · Sat dinner** asks **Which way will you cook it?** with each way and its time (**· last time** on the one used last, pre-picked), the note **The shopping list and Cooked it follow it. You can change it from the meal later.** and **Add to plan** (**Save** when the meal's way is changed). The meal's menu has **How it’s cooked…** (**How it’s cooked: Chicken curry…** when several).
- **Refusals from the server (cabledrawer 10 Nov):** **That isn’t one of this recipe’s ways of cooking it.**, **Only a recipe has a way of cooking it.**, **This recipe has only one way of cooking it.**, and when Cook mode can't change the meal: **Couldn’t change how the meal is cooked. Try again from the Plan.**
- **The editor's switch before a way has a name (cabledrawer 10 Nov):** **First way** and **Second way**, in place of the name, until the name is typed.
- **Saving a second way when the first has no name (cabledrawer 10 Nov; the server's refusal):** **Name the first way of cooking it too, so Cook mode can ask which.**
- **The recipe page with one way and no name for it (cabledrawer 10 Nov):** no switch and no name: it reads as any recipe always did. The switch shows only when there are two ways, and then both have names.
- **Changing the way from a meal that had optional ingredients left out (cabledrawer 10 Nov):** the toast says so after the change: **Changed how Dal on Sat dinner is cooked to Instant Pot. Its optional ingredients start again** (no full stop at the end, like the other toasts; with **Undo**, which puts them back). A meal with none left out says only the first part.
- **Cooked it when the way picked in Cook mode could not be saved before (cabledrawer 10 Nov):** Cooked it sets the meal to the way cooked first, and if it still can't, it doesn't open and says **Couldn’t tell the Plan which way you cooked it. Check the connection and try again.**
- **Check (mockup, proposed for the rest):** **Two ways to cook this: Stovetop and Instant Pot. They’re kept as two methods, and Cook mode asks which one on the day.**, then **Steps · Instant Pot** with the second way's steps (their waits are confirmed like the first way's, with **Yes, it waits**, **Change** and **No wait**; otherwise read only: the ingredients and the time are the page's, shared by both ways, and can be changed in the editor).

## 56. Lines on Check (0.8 W4d, F187 to F189; cabledrawer 8 and 9 Nov; the mockup words `Dark-CheckSections08-Phone`, `Dark-CheckPick08-Phone` and `Dark-NewIngredient08-Phone` are agreed, the rest is accepted as built, cabledrawer 10 Nov)

- **Add a line (mockup):** a dashed button at the end of each section, in See all and One at a time: **Add a line to the batter** (from "For the batter"), **Add a line to the dosa**; a section whose heading doesn't start "For the" / "To make" is named in quotes, **Add a line to “To assemble”**; no headings, **Add a line**.
- **The new line (cabledrawer 10 Nov):** **Added by you** where "As written" goes; **What is it?** (the name box); **The amount and note can be left empty.**; **Cancel** and **Add line**; **Type a name.** An ingredient with exactly that name is the line's ingredient; otherwise it asks like any line (New ingredient · Pick an ingredient · Made in this recipe · Made in another recipe · Treat as staple). A line never named is not saved and not counted.
- **The pick-list for a line (mockup):** **What is “Dosa batter”?**, **As written: Dosa batter, as above · 4 cups**, a **Search** box, rows with the name and a line under it (**Made ahead · makes 1.5 l**; an ingredient says where it is kept), **Recipe** and **Ingredient** beside two rows with the same name, **When a recipe and an ingredient share a name, the recipe comes first.**, **New ingredient**, **Made in another recipe…**, **Cancel**. Recipes only: **No recipe has that name. Import or write it first, then come back.** (cabledrawer 10 Nov).
- **Made in another recipe (mockup):** a choice on a line that needs you (**Made in another recipe**); once chosen the line reads **Made in another recipe: Dosa batter**, its state **Recipe**, and **Uses the recipe “Dosa batter” when you save, kept in Fridge.** (cabledrawer 10 Nov).
- **The New ingredient box (mockup):** **Where does it come from?** **Bought** · **Made in another recipe**; then **Which recipe makes it?** with the recipe and **Change**, **Made ahead · that recipe says how long it keeps**, **Pantry keeps it in** with the household's places (Fridge, Freezer, Cupboard…), and **No recipe for it yet? Choose Bought for now, or save this one and import the other.** The button stays **Done** (the box's own word, F10; the mockup's sheet says "Add ingredient"). When the recipe is not made ahead: **That recipe isn’t made ahead, so nothing is kept in the pantry.** and, with no recipe picked, **Pick the recipe that makes it.** (both cabledrawer 10 Nov).
- **The Check header (cabledrawer 9 Nov):** no new words: the title sits a little in from the edge, and **Step 2 of 3 · nothing saved yet** drops under it when the two don't fit.

## 57. A section as its own recipe (0.8 W4e, F190; cabledrawer 8 Nov; the mockup words `Dark-CheckSections08-Phone` and `Dark-CheckOwnRecipe08-Phone` are agreed, the rest is accepted as built, cabledrawer 10 Nov)

- **The button (mockup):** **Make this its own recipe**, under a section heading in See all and above the line in One at a time. Chosen by hand, never automatic.
- **The sheet (mockup):** **Make “For the batter” its own recipe?**; **It becomes a new recipe, Dosa batter, with its 5 lines and 3 steps, kept as Made ahead. Masala dosa then uses it as one line: “Dosa batter · 4 cups”.**; **Name of the new recipe**; **It makes** (an amount and a unit: cups, litres, ml, g, kg); **Both recipes are checked here and saved together.**; **Make it its own recipe**; **Cancel**. A section with no steps says "with its 5 lines".
- **After it is made (cabledrawer 10 Nov):** the heading says **Its own recipe: Dosa batter · 4 cups** with **Change** (the same sheet, its button **Done**) and **Keep in this recipe**. A line that already stands for it ("Dosa batter, as above") reads **Made in its own recipe: Dosa batter**.
- **Toasts, each with Undo (cabledrawer 10 Nov):** **Made “For the batter” its own recipe**; **Changed the recipe made from “For the batter”**; **Kept “For the batter” in this recipe**. An Undo that finds its heading gone says **Couldn’t put it back: the section has changed.**
- **Errors (cabledrawer 10 Nov):** **Type a name.** and **Type how much it makes.** in the sheet. A refusal on Save is the server's own sentence (two short sentences) and shows where it belongs.
- **Save:** one **Recent changes** line, **Imported Masala dosa and Dosa batter**, with one Undo that takes both back.
- **Server sentences on Save (cabledrawer 10 Nov):** **That section’s recipe isn’t in this save.** (a line uses a section recipe the save doesn't hold); **A section’s own recipe can’t use another one.**; **A section made its own recipe needs the line that uses it.** The name box also refuses a name with a hidden character, with the app's usual sentence for names.
- **The sheet's stand-ins while the names are still empty (cabledrawer 10 Nov):** **the new recipe** (in the sentence and the preview line, until a name is typed) and **This recipe** (for the main recipe's name, until it has one).

## 58. The plan works backwards (0.8 M3, F124; cabledrawer 31 Oct and 9 Nov; the mockup words `Dark-PlanStart08-Phone`, `Dark-TodayTonight08-Phone` and `Dark-CookDay2-08-Phone` are agreed, the rest is accepted as built, cabledrawer 10 Nov)

- **The question when a recipe with a long wait is added to the plan (mockup):** the sheet **Masala dosa · Sat breakfast** over **Breakfast at 08:00**, the wait's pill (**8–12 h**), **When will you …?** and the times, each **Fri 21:00** over **ready by 08:00**, then **Another time…**, the note **The day before, Today and the Cook view say “Start tonight at 21:00”. You can change the time from the meal.**, **Add to plan** and **Cancel**.
- **Proposed, for cabledrawer:** the mockup's **The batter has to ferment first.** is **It has to ferment first.** (**marinate**, **soak**, **rest**, **chill**, **prove** the same way), and **When will you soak and grind it?** is **When will you start it?**, because Mealwright does not know which words the recipe's step uses. **Another time…** shows **Day** and **Time**; a time that is not before the meal says **Pick a time before the meal.**, and a missing one **Pick a day and a time.** When the meal's time is changed the button says **Save**, and a time that is not one of the suggestions shows first, **as it is now**.
- **Which waits ask (cabledrawer 10 Nov):** a wait whose shortest length is **4 hours or more** (marinate 4–24 h, soak overnight, ferment 8–12 h). An hour's rest is part of the cooking day and asks nothing.
- **The times offered (cabledrawer 10 Nov):** one that puts the wait in the middle of its range (the meal's time, minus half-way between the shortest and the longest wait, minus the recipe's working time, in whole hours), **ready by** the meal's time; and an earlier one that is ready even if the wait is the longest, **ready by** the time it would be. None that has gone by; when both have, one starting at once (**ready by** the earliest it could be).
- **The time a meal is eaten (cabledrawer 10 Nov):** there is no setting for it yet, so by the slot's name: Breakfast 08:00, Brunch 10:30, Lunch and Tiffin 12:30, Snack 16:00, Tea 17:30, Dinner and Supper 19:00, any other slot 12:00.
- **No time yet (cabledrawer 10 Nov):** a quiet button on the question when a recipe is being added, above **Cancel**: it adds the meal with no start time (the meal's menu then says **Set when to start…**). A meal whose time has already gone by does not ask at all. **Cook once** (from the Add sheet) does not ask either. **Copy to…** of a planned recipe with a long wait asks, like the other ways of adding it. **Moving** a planned meal that has a start time asks **When will you start it?** again for the new day (cabledrawer 10 Nov), once for each recipe in it that had a time; the main button is **Move** (cabledrawer 10 Nov), **No time yet** moves it with no time, and **Cancel** moves nothing. The note under the times says **The day before, Today and the Cook view say “Start tonight at 21:00”…** for an evening time and **Today and the Cook view say “Start at 07:00”…** for an earlier one (the mockup's words, with the first part left out when it would not be true). The pale purple colours for the light theme (Today's card and its border) are cabledrawer 10 Nov.
- **Today's Move it (FX5; cabledrawer 10 Nov: it asks for a start time for a meal that has a wait, as the plan's Move does):** on the **Did you cook…?** card, **Move it** → pick the day and meal → **Move to …**, then, for each recipe in the meal that had a start time, **When will you start it?** with **Move**, **No time yet** and **Cancel** (Cancel moves nothing). No new words.
- **From the meal (cabledrawer 10 Nov):** the meal's menu has **Starts Fri 21:00…** (**Set when to start…** when it has no time; **Starts Fri 21:00: Masala dosa…** when several recipes wait).
- **Today (mockup):** the card **Start tonight** with the wait's pill (**Ferment · 8–12 h**), the step (**Soak and grind the dosa batter**), **For Sat breakfast · Masala dosa**, and two buttons, **Start it in Cook mode** and **Done already**. **Proposed, for cabledrawer:** the heading says the time, **Start tonight at 21:00** (**Start at 07:00** before five in the evening); the mockup's **30 min now** is **30 min of work** (the recipe's working time, not the wait); the mockup's **Grind by 22:00 so it's ready by 08:00.** is **Start by 21:00 so it’s ready by 08:00.**; a start that has gone by without being marked says **Start now** with **You planned to start Thu 21:00.**
- **Done already (cabledrawer 10 Nov):** it records that the wait has begun, at the moment you press it, and nothing else: the pantry, the shopping list and the meal do not change. The toast says **Marked Masala dosa as started**, with Undo. Cook mode does the same, without a toast, the first time you go past the step that waits.
- **The Plan's Cook view (brief; cabledrawer 10 Nov):** on the day to start, **Start tonight at 21:00: soak and grind the dosa batter (for Sat breakfast)** with **Start it in Cook mode** and **Done already**.
- **Cook mode on day two (mockup):** the header **Day 2 · Step 4 of 6**, the folded steps **1–3 · Soak, grind and leave the batter** with **Done yesterday 21:40**, and **Fermented 10 h 20 min** with **needed 8–12 h**. **Proposed, for cabledrawer:** the folded title is the first sentence of the step that waits, **Done today 21:40** or **Done Thu 21:40** on other days, **Marinated**, **Soaked**, **Rested**, **Chilled**, **Proved** for the other kinds, a wait shorter than the shortest it needs is outlined, and on the step that waits (before it is begun) **Then it waits (8–12 h). Cook mode picks up after this step when you come back.**
- **Refusals from the server (cabledrawer 10 Nov):** **Only a recipe has a start time.**, **This recipe has no long wait to start ahead.**, **Pick a time before the meal.** Sent with a move (cabledrawer 10 Nov, the words too): **Leftovers have no start time.** (a start time sent with leftovers), **That isn’t in what is being moved.** (a start time for a recipe not in the meal moved) and **One start time for each recipe.** (the same recipe named twice).
- **Recent changes (cabledrawer 10 Nov):** **Changed when to start Masala dosa for Breakfast on Sat 14 Nov**, **Took away the start time of Masala dosa for …**, **Started the wait for Masala dosa for …**, **Took away the started mark of …**; the toast for a change from the meal says **Changed when to start Masala dosa**.

## 59. Beta 1 faults (0.8 FX4; cabledrawer 10 Nov; the line below is accepted, cabledrawer 11 Nov)

| Where | Words | Where it comes from |
|---|---|---|
| A date box (Cook review "Any left over? → Change", Change use-by date, Add to pantry's date, Another time, a tub's use by, Restocked) given a date that can't be a day (a stray six-digit year, year 6, 31 February) | **That date doesn’t look right. Pick another.** (two short sentences, error style) | accepted, cabledrawer 11 Nov; `BAD_DATE` in `frontend/src/lib/dates.ts`; F220 |
| Manage tags, the merge question for a tag with one recipe | Its 1 recipe **gets** “middle eastern” (plural: “Its 3 recipes get …”) | F221 (cabledrawer 10 Nov) |

## 60. Reading "or" lines (0.8 IM1, F217; cabledrawer 10 Nov; the wording of the button is cabledrawer's own, "Use this instead"; the rest is accepted, cabledrawer 11 Nov)

- **On a Check row whose line says "or" (cabledrawer 10 Nov):** under the ingredient the row shows the other choice, **or 2 flat bread**, with the button **Use this instead**. (The button's words are cabledrawer's; "or" and the amount and name after it are accepted, cabledrawer 11 Nov.)
- **Its toast, with Undo (accepted, cabledrawer 11 Nov):** **Used “flat bread” instead of “shrak”**. Using the other choice again swaps back.
- The saved line keeps the other choice as its note (**or 2 medium size flat bread or tortillas**): no new word, no database change.

## 61. Check and Import screens (0.8 IM2, F211, F212, F214, F209, F216; cabledrawer 10 Nov; only the button names Back to drafts, Discard draft, Change and Next draft are cabledrawer's; every other word here is accepted, cabledrawer 11 Nov)

- **Leaving Check (F211):** **Back to drafts** (computer: replaces Cancel; phone Focus: replaces Close, with the small line **Kept in Drafts**; One at a time: the X's spoken label **Back to drafts (kept in Drafts)**, was **Close (kept in Drafts)**) and **Discard draft**.
- **Discard draft asks once:** **Discard this draft?** · **Sambar will be deleted from Drafts, with its waiting photo. You can undo it from Recent changes.** (a review not kept yet: **Sambar isn’t kept in Drafts yet, so nothing of it is kept. Its waiting photo is deleted.**) · **Discard draft** (**Discarding…**) · **Keep checking**. The toast is the Drafts list's own: **Deleted the Sambar draft** with Undo. A delete that fails says the server's sentence under the buttons.
- **A draft that couldn't be kept (F141, unchanged for a changed draft):** **Discard changes**; for a review never kept the old **Discard** is **Discard draft**.
- **After Save recipe (F212):** the recipe's page shows **Next draft** and, under it, the draft's name.
- **Change on a row (F214):** the row's **Change** (spoken **Change: 1 red onion, sliced**) opens a sheet named **Change Onions** (the row's bold name): **Pick an ingredient** · **Edit the name read** · **New ingredient** · **Back to how it was read** (only when the row has a choice) · **Cancel**. **Edit the name read** has the box **Name read**, the hint **Mealwright looks for an ingredient with this name.**, **Cancel**, **Done**, and **Type a name.** when it is empty.
- **After several links (F209, F216):** each read row says **✓ All matched** (every ingredient matched) or **Needs checking** (cabledrawer 11 Nov; it was ✓ Ready to check), and both have **Check** (spoken **Check Masala dosa**); **Save 3 ready recipes** (**Save 1 ready recipe**; **Saving…**) with **Ready means every ingredient matched. The others stay in Drafts for you to check.**; the toast **Saved 3 recipes** (**Saved 1 recipe**; with a failure **Saved 2 recipes. 1 stays in Drafts**; none saved **Couldn’t save those recipes. They stay in Drafts.**) with Undo; a saved row says **✓ Saved** with **Open** (spoken **Open Masala dosa**).
- **Quick import, after the fact (review round 1, accepted, cabledrawer 11 Nov):** when one save can't be undone the toast says **Undid 2 of 3**; a row whose draft was saved or discarded elsewhere says **No longer in Drafts** (no Check link, not counted); focus goes to the **N links · one after another** heading when **Save N ready recipes** finishes.
- **Edit the name read with no connection (accepted, cabledrawer 11 Nov):** the toast **Name changed. Looking for an ingredient with that name needs a connection, so the row keeps its match.**

## 62. Batch cook: step timings and your kitchen (0.8 wave 6, B1, F142; cabledrawer 28 Oct, 6 Nov and 11 Nov; the mockup words `Dark-BatchSteps08-Phone` and `Dark-BatchKit08-Phone` are agreed, the rest is proposed, for cabledrawer)

- **In the recipe editor, each step (mockup):** **Hands-on** · **Waiting** (the two choices), **Minutes**, **Uses** with **Hob ring** · **Pressure cooker** · **Oven** · **Nothing**; the tags **Hands-on · 8 min** and **Waiting · 15 min** (the time as everywhere: 45 min, 1 h 30 min), the equipment's name as a tag (none for Nothing), and **guessed** (the pink Experimental flask) until changed by hand, then **set by you**. The note: **Guessed from the step. Change anything that’s wrong; Batch cook uses it to fit steps around each other.** The Method heading carries the **Experimental** badge.
- **Proposed, for cabledrawer (editor):** the button that opens a step's boxes is **Change** (spoken **Change the timing of step 2**) and closes with **Done** (spoken **Done with the timing of step 2**); **Guess again** puts the guess back after a hand-set timing; **partly guessed** is the mark when only some of the three were set by hand (the first change in the editor takes all three as yours when the guess is known; on a new step, or one whose words changed, only what you set is yours and the rest is guessed when you save); **Guessed when you save** stands in for the tags of a new step, or one whose words changed, until the server has guessed again; a minutes box that isn’t a whole number says **Type the minutes as a whole number, such as 10.** and Save waits.
- **Your kitchen (mockup, a sheet):** **Your kitchen** · **Batch cook never plans more at once than your kitchen has. Asked once; change it any time in Settings › Kitchen.** · **Hob rings** (**Burners on the cooker**) · **Pressure cookers** (**Including an Instant Pot**) · **Oven** **Yes** · **No** · **Save** · the steppers' spoken names **Fewer hob rings**, **More hob rings**, **Fewer pressure cookers**, **More pressure cookers**; Close.
- **Proposed, for cabledrawer (Settings):** the row **Your kitchen** under Kitchen (phone: its value is **4 hob rings**); its section shows **Hob rings**, **Pressure cookers**, **Oven** (**Yes** or **No**) with the line **Batch cook never plans more at once than your kitchen has.**, **Not asked yet: Batch cook asks the first time you use it.** until it has been saved once, and the button **Change** that opens the sheet. Any person of the household may change it, like Cook mode's per-step switch.
- **Ingredients for each step (F142, no new words):** the guesses no longer put "coriander leaves" on the step that says "coriander seeds", find "red chillies" when the line says "dried red chilies", and an ingredient that several steps use (2 cups water on six steps) is listed in a step's own list without its full amount (proposed, for cabledrawer; **Show ingredients** still has the amount).

## 63. Batch cook: suggestions and the Plan (0.8 wave 6, B2; cabledrawer 28 Oct, 6 Nov and 11 Nov; the mockup words `Dark-BatchPick08-Phone`, `Dark-BatchPick08-Desktop` and `Dark-PlanBatch08-Phone` are agreed, the rest is proposed, for cabledrawer)

- **Where (spec, mockups):** the computer's sidebar entry **Batch cook** with the pink flask (spoken **Batch cook, Experimental** when the sidebar is folded); the phone's Plan tabs **Week · Month · Batch cook** (the flask beside the third); the page title **Batch cook** on a computer (with **Experimental** and **Picks come only from your own recipes.**) and **Plan** on a phone.
- **The screen (mockups):** the note **The picks and timings are guesses. Swap a recipe if it’s wrong, and fix a step’s timing when you edit the recipe.** with **Got it**; **Cook day** (chips such as **Sun 15 Nov**, **Mon 16**, **Other…**), **How many recipes** (2 · 3 · 4), **About 1 h 50 min together** and **2 h 55 min one by one**, on a computer also **hob 4 · pressure cooker 1 · oven yes** with **Change**; each pick's name, its time, its why line, the tag **Use soon · spinach, 2 days**, **Swap** and **Open recipe**; **Show me others** and **Plan this batch**. The why lines are written by the server from the recipes. **Pressure cooker runs while you chop for the others** is the mockup's own. **Shares onion, tomato and curry leaf prep with Sambar** and **uses your Use soon spinach** come from the spec's example ("Shares onion, tomato and coriander prep with Rasam; uses your Use soon spinach"), not the mockup, and **not cooked in the last 14 days** is the spec's third preference said in words. The first letter is a capital, the clauses are joined with a semicolon.
- **The Plan (mockup):** the card **Batch cook · 3 recipes**, **About 1 h 50 min · from 10:00**, **Experimental**, each recipe with its batch colour and **· 4 tubs**, **Start batch cook**, **Change**; each meal from it says **Batch · Sun**.
- **Proposed, for cabledrawer:** the why line's other clauses **the oven does the work while you cook the others**, **simmers while you work on the others**, **waits while you work on the others** and, with nothing to say, **Fits your kitchen.**; **Use soon · spinach, today** and **, 1 day** (the mockup shows **2 days**); the card's third button **Remove** (cabledrawer 11 Nov: with Batch cook hidden the card has no buttons at all, and taking a session off is refused like every other Batch cook route) (one Undo for the whole session; the toast says **Took the batch cook off the plan**); the change summaries **Planned a batch cook of 3 recipes for Sun 15 Nov**, **Changed the batch cook to 3 recipes for Sun 15 Nov** and **Took the batch cook of 3 recipes for Sun 15 Nov off the plan**; the sheets that follow each other, titled **Cook once, eat for… 1 of 3**, with the button **Next recipe** and, on the last, **Plan this batch** (Cancel on any stops and plans nothing); **Start batch cook** opens the first recipe's Cook mode until batch cook mode is built (B3); when there is nothing to pick: **No recipes to batch yet** · **Batch cook picks from your own recipes that have steps. Add a recipe, or add steps to one.** · **Go to recipes**; with fewer than asked: **Only 2 of your recipes have steps, so this batch has 2.** and **Only 1 recipe has steps, so there is nothing to batch with. Add steps to another recipe.**; while it works: **Finding recipes…**; when it can't: **Couldn’t find recipes. Try again.**; offline: **Batch cook changes …** like the Plan's; **Changing the batch cook on Sun 15.**; **Batch cook is switched off** · **An admin can switch it on in Settings.**; the Settings row **Show Batch cook** · **Experimental. Switched off, it leaves the sidebar and the Plan.** · **Only an admin can change this.**; the server's refusals **Switch a meal on first.** (no meal is on to plan in), **Batch cook is switched off. An admin can switch it on in Settings.**, **A batch cook has 2 to 4 recipes.** and **Each recipe can be in a batch cook once.**

## 64. Batch cook mode and the one Cooked it (0.8 wave 6, B3; cabledrawer 28 Oct and 11 Nov; the mockup words `Dark-BatchSession08-Phone` and `Dark-BatchCooked08-Phone` are agreed, the rest is proposed, for cabledrawer)

- **The screen (mockup):** **Batch cook · 3 recipes** · **Task 6 of 19 · about 1 h 20 min left** (the time is the hands-on time still to give) · **Now** with the tag **Hands-on · ~8 min** · for shared prep **Shared prep · both recipes** · a line for each recipe with its timer (**Pressure cooker · waiting** and the time left, as 11:40) or **Starts in about 35 min** and **—** · **In use: hob 1 of 4 · pressure cooker 1 of 1** · **NEXT** and its line (**Chicken chettinad: fry the onions with the curry leaves (hob ring 2).**) · **Show ingredients** · **Done, next →**. The cross is **Leave Batch cook** (spoken). A shared task reads **Chop 3 onions: 2 for Chicken chettinad, 1 for Sambar** (the amounts come from the ingredient lines).
- **Proposed, for cabledrawer (the screen):** tags **On the hob · waiting**, **Oven · waiting**, **Waiting** · **Start timer** (spoken **Start timer for Sambar**) on a recipe whose wait is ready to start · **Time’s up** (the timer ran out; it stays until that recipe's next task is done; a chime plays once) · **Starts next** · **Nothing in use right now** · **All 19 done** · **Nothing for your hands right now.** with **The next timer is below.** · the footer button **Waiting for a timer** (greyed) when only timers are going · **All done** with **Everything is cooked.** and **Cooked it takes the ingredients out of the pantry for every recipe.**, the footer button **Cooked it** · **Done: Chop 3 onions** with **Undo** after Done, next · **The night before: Soak the rice overnight.** (soaking and overnight steps at the start of a recipe are not part of the day; Today shows them as Start tonight) · **Your kitchen has no oven. Do this on its own, however you manage it.** (a step that needs equipment the kitchen has none of is done on its own) · the sheet **Ingredients** with **Done**, each recipe's ingredients under its name · **Couldn’t read every recipe. Try again when you’re online.**
- **Proposed, for cabledrawer (changes since it was planned):** **A recipe or your kitchen changed since this was planned.** with **Plan again** (it starts the schedule over; what was done is cleared).
- **Proposed, for cabledrawer (offline):** **You’re offline. Timers and Done, next keep working.** · **Saved on this phone, sent when you’re back online.** Starting for the first time and Cooked it need the connection.
- **The one Cooked it (mockup):** **Cooked it · Sun 15 Nov** · **Check what came out of the pantry and where the tubs go. One entry in Recent changes, with Undo.** · each recipe's name with **Change**, its ingredients with the amount, and its tubs (**4 tubs · 2 Freezer, 2 Fridge**, **3 tubs · Fridge**; a recipe with no tubs shows no tubs line: the mockup's **Eaten today · no tubs** was dropped, cabledrawer 11 Nov) · **Cooked it**. Proposed, for cabledrawer: **Change** opens the recipe's own rows (as in Cooked it) with **Portions cooked**; **Not taken** for a row switched off; **Not in pantry**; tubs in a meal count as **2 in meals**; **Working out what to take…**; the Back cross is spoken **Back to Batch cook**.
- **Proposed, for cabledrawer (the API's sentences, not on a screen):** **Batch cook mode hasn't been started for this batch cook.** · **None of this batch cook's recipes has a step to cook.** · **That task isn’t in this schedule.** · **Only a waiting step has a timer.** · **There’s no recipe in this batch cook to cook.**
- **Proposed, for cabledrawer (review round 1 of B3, words that were missing above):** **Shared prep · Sambar and Rasam** (when the shared task is not for both of exactly two recipes) · **Your kitchen has no pressure cooker. Do this on its own, however you manage it.** and the same with **hob ring** (the oven's is above) · in the NEXT line, where the step uses a place: **(pressure cooker 1)** and **(oven)** after the **(hob ring 2)** of the mockup · **Done** on the row of a recipe that has nothing left · **A recipe can be chosen only once.** (the API, when a session's Cooked it names a recipe twice).
- **Proposed, for cabledrawer (review round 1 of B3, new):** the API's sentence for a timer that has to wait for the step before it or for the cooker, ring or oven to be free: **This has to wait: the step before it, or the equipment it needs, isn’t free yet.** · in the one Cooked it, a recipe cooked on its own already or taken out of the recipe list is left out and said so under the others: **Sambar · already cooked**, **Sambar · removed**; when every recipe is like that, the toast **Everything in this batch cook was already cooked.** (the API: **Everything in this batch cook was already cooked or removed.**).

## 66. Whole-0.8 review fixes: shopping (RF2; cabledrawer 11 Nov)

- **Already have it, twice (Sh2; cabledrawer 11 Nov):** a quiet note (a toast, no Undo, because nothing was changed) on the second phone that said "Already have it" for a row the other phone had already found at home: **Already found at home by the other phone.** It comes from the server's answer (`ignored`, reason `already_found`, sync-protocol 7.6), so it reads the same offline and online.
- **cabledrawer 11 Nov (Sh5, the API's sentence, seen only if a phone ever sends an amount with more than 3 decimal places):** **That amount has too many decimal places. Use at most 3.** It replaces "That change isn’t valid (found_at_home.amount: Decimal input should have no more than 3 decimal places)." for that one case; the Already have it sheet now rounds its half and quarter to 3 decimals, so it should not be reached.
- **cabledrawer 11 Nov (Sh6, a quiet note, no Undo):** when a phone changes or moves a line the plan had taken off (the meal was taken off the plan): **Ghee isn’t needed by the plan any more, so your change wasn’t kept.** It no longer says "Your other phone had removed Ghee…" or names a person. When a person did remove the line, the note is unchanged.
- **No new words (Sh1, Sh3, Sh4):** a tick carries the amount its line showed, so the pantry and Recent changes say what was bought ("Bought 1 jar Ghee → Cupboard") and the rest of a line that grew stays on the list as its own line; "Already have it" for part of an amount leaves the rest on the list; and Add as bought with no amount typed now makes the row read like the hint ("Paneer 1 pack → Cupboard"), with no "Not in the pantry yet. No amount." and no "How much?".

## 67. Whole-0.8 review fixes: pantry and Batch cook (RF3; cabledrawer 11 Nov; every word here accepted, cabledrawer 11 Nov)

- **Batch cook mode (cabledrawer 11 Nov):** on a recipe's running timer the button **End timer** (spoken **End timer early for Sambar**); on a wait that has not been started, beside **Start timer**, the button **Skip wait** (spoken **Skip wait for Sambar**). cabledrawer 11 Nov: "a timer can be ended early and a wait skipped".
- **Plan this batch (cabledrawer 11 Nov: "'Plan this batch' asks, per recipe, which optional ingredients and (for two methods) which method, as adding to the plan does (last used pre-picked); batch cook mode and Cooked it follow the answers."):** before each recipe's Cook once sheet, the same two sheets adding to the plan shows (**Which way will you cook it?** and **Which optional ingredients will you use?**, as in sections 52 and 55), with the main button **Next** instead of **Add to plan**, and, after the recipe's name, the cook day as **Sun 15** instead of a meal (the meal is picked by the server). Cancel on any of them stops and plans nothing. After a refused **Plan this batch** the last sheet comes back with every earlier answer kept.
- **Batch cook mode follows the answers (no new words):** an Optional step is in the schedule unless every ingredient it uses was left out (a step that uses no ingredient stays); Cooked it takes only the optional lines that were kept.
- **The API's sentence, not on a screen (cabledrawer 11 Nov):** **The schedule was made again on another phone. Opening it afresh.** (a mark made on a phone that still has the older schedule).
- **Slot names (no screen words; cabledrawer 11 Nov):** a meal's time for Start tonight is read from whole words of its name: **morning** (08:00), **evening** and **night** (19:00) are new, with the words already there (breakfast, brunch, lunch, tiffin, snack, dinner, supper, tea); **Steak night** is no longer read as **tea**.
- **Dropped (cabledrawer 11 Nov, prerelease note 6):** **Eaten today · no tubs** in the one Cooked it.
- **Stocktake (cabledrawer 11 Nov: "Stocktake counts tin, tins, can, cans in whole units"):** a pack called **tin**, **tins**, **can** or **cans** (any capitals) is counted with − and +, as a tin was; an answer far above what is there is stored as given.
- **An optional step in batch cook mode (cabledrawer 11 Nov):** the pill **Optional step** above the step's words, as on the recipe page.

## 68. Whole-0.8 review fixes: import (RF4; every word here accepted, cabledrawer 11 Nov)

- **Undo of an import's save keeps an ingredient another saved recipe uses (I2; the toast wording accepted, cabledrawer 11 Nov):** after the usual Undo sentence, **Pork shoulder is kept: another recipe uses it.** (the ingredient's own name); for two or three, **Pork shoulder and Besan are kept: another recipe uses them.** (a list with "and"); for four or more, **4 ingredients are kept: another recipe uses them.**; when what uses it is the plan, the shopping list or the pantry and not a recipe, **Besan is kept: it is in use.** / **… are kept: they are in use.** (cabledrawer 11 Nov) The Undo itself still reads as done.
- **A link that failed on the several-links screen (I3, accepted, cabledrawer 11 Nov):** the button **Try again** on the row of that link (spoken **Try again: <the link's name>**); it reads only that link. Pressing **Read the recipes** again reads only the links not read yet; no new words.
- **Two sections with one name (I12, accepted, cabledrawer 11 Nov):** in the sheet that makes a section its own recipe, **Another section is already making a recipe with that name. Type a different name.**
- **Notes the reader writes (I6, accepted, cabledrawer 11 Nov; they appear in a line's note, not as screen words):** **plus 1 tsp** for "1 tbsp + 1 tsp sugar" (the line keeps the first amount), and **1lb 2oz** for "500g/1lb 2oz beef mince" (the line is 500 g); "or more", "or less", "or so" and "generous" or "big" stay in the note as written.
- **No new words:** Serves and time out of range (I11) simply stay empty; the Drafts list's count (I7) and a typed 10/3 (I10) use the words that were there.

## 69. Whole-0.8 review fixes: screens (RF5)

Every word here accepted, cabledrawer 11 Nov.

- **The Plan's Start batch cook, when the batch cook was changed or removed meanwhile (H3):** **That batch cook was changed or removed. The Plan is up to date now.** (shown when no batch cook is left on that day; when one is, Start batch cook opens it).
- **Shops, places or meals reordered from an out-of-date list (H5):** **The list changed. Try again.** (the list is read again at the same time; it replaces the server's **Send every shop once, in the order you want.**).
- **Recent changes, with Undo, for the rest of Settings (H8):** **Added the place Garage** · **Renamed the place Spice rack to Larder** · **Changed the order of the shops** · **Changed the order of the places** · **Changed your kitchen: 3 hob rings (was 4), 2 pressure cookers (was 1), no oven (was yes)** (only the parts that changed; **an oven** when it is switched on) · **Switched Batch cook off** / **Switched Batch cook on**. When an Undo can't be done: **That can’t be undone: the place is gone.** · **…the place is in use now.** · **…the place has been renamed again.** · **…there’s already a place called Larder.** · **…the order has been changed again.** · **…your kitchen has been changed again.** · **…Batch cook has been switched again.**
- **Undo of adding a place that is now the only Fridge or Freezer (RF5 fix round 1):** **That can’t be undone: Chest freezer is your only freezer now.** (also **…your only fridge now.**)
- **Recent changes, with Undo, for the pint and Ingredients for each step (RF5; accepted, cabledrawer 11 Nov):** **Changed the pint to US pints (was UK pints)** (or **…to UK pints (was US pints)**) · **Switched Ingredients for each step on** / **Switched Ingredients for each step off**. When an Undo can't be done: **That can’t be undone: the pint has been changed again.** · **That can’t be undone: Ingredients for each step has been switched again.** Only an admin sees Undo on the pint line (as for Batch cook); the lines use the existing Recent changes row and Undo button, so nothing new to lay out in either theme or at 200% text. A save that changes nothing, and a resent old save, say nothing and change nothing.
- **cabledrawer 11 Nov (RF5):** the open Plan refreshing on another person's change (live `plan` event), and the week grid starting at 1200 px (1100–1199 px shows the list). No new words on screen.
