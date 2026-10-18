# The word list: how Mealwright talks

**Draft, waiting for cabledrawer (not yet approved).** Written by Claude Code overnight on 18 Oct from the spec and the screens as they are built (0.3). Nothing in here is a new decision: every line says where it comes from. Where the built screens disagree with each other or with the spec, the disagreement is under "Differences found (for cabledrawer)" at the end and nothing was chosen. cabledrawer approves the first version and any change to it (spec: UX — CORE → Keeping the UI good, item 1).

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
| **Recent changes**, **Undo** | history, log, audit trail | spec "Recent changes" and "History and undo". (Settings → Your data has a "change log"; see section 11.) |
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

**Words the checker rejects on screen** (`review`, Plain words): "items", "units", "lots", "entities", "quantity", "SKU", "location", "sync", "queue", "conflict". Principle 7 adds "food items", "labels", "groups". See section 11: the screens use "item(s)" in a few places, so that word needs your ruling.

**Never "Are you sure?"** There are no confirm dialogs: actions happen at once and offer Undo (spec principle 6). The one justified exception is signing out with unsent changes (spec "Signing out with unsent changes").

**Never "No conflict pop-ups":** clashes are a quiet note with Undo ("Wren ticked this too") (spec "Offline shopping-list sync").

## 2. Screen and page names

Today · Plan · Shopping · Pantry · Recipes (sidebar names). Phone tabs: Today · Plan · **Shop** · Pantry · Recipes ("Shop" is the short name under the tab: `frontend/src/lib/nav.ts`). Under Recipes: All recipes · Drafts · Ingredients (spec "Recipes navigation"). Other pages: Settings, Sign in, Set up Mealwright (first run). Source: spec "Layout decisions"; `nav.ts`.

## 3. Places, shops and lists

- Places: **Fridge · Freezer · Cupboard · Spice rack**; renameable, so use the household's own names on screen (spec Onboarding; Settings → Shops & places).
- Shops are names only. **Any shop** is the group for ingredients with no usual shop; **All** is the view with every shop under its own heading and is where Shopping opens (spec "Shopping opens on All", cabledrawer 18 Oct).
- Lists: **Main list** (called "This week" until renamed; "main list" is shown in small text beside it) and **extra lists** ("Party on Saturday"). **+ New list**. The picker reads "Main list · 12" and "Extra list · 5 · ticked items still go to the pantry". Source: spec "Shopping extra lists"; `ListPicker.svelte`.
- Aisles use these names: Veg & fruit · Meat & fish · Dairy · Dry goods · Tins & jars · Spices · Other (`frontend/src/lib/shopping/aisles.ts`; spec "Shopping").
- Where something goes: "→ Fridge" (a put-away result), "Moved Milk → Freezer".

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
7. **Switches, not checkboxes**, for every on/off, labelled in words that say the on state ("Stay signed in for 30 days", "Remember for next time", "Staple") (spec principle 15).
8. **Choices with several options use buttons that say what they do**, in the order the spec gives: "Try sending now · Stay signed in · Sign out and lose them".
9. **Screen-reader names say what happens** ("Add Oil to the shopping list", "Tick Basmati rice", "Undo: Used 200 g spinach") and the visible name is part of them (WCAG "label in name").

## 6. Toasts and Undo

- A toast is one calm sentence about **what happened**, in the past tense, with the ingredient's name first or the verb first as the server words it: "Used 200 g spinach", "Binned Milk", "Toor dal moved to Fridge", "Basmati rice ticked", "Oil added to the shopping list", "Renamed to Toor dal", "Toor dal is a staple". Source: `pantry.svelte.ts`, `store.svelte.ts`, `IngredientEditor.svelte`, `foodEditor.svelte.ts`; spec "Tap a staple when it runs out".
- Every change has an **Undo** button in its toast (6 seconds; it waits while the pointer or keyboard focus is on it) and **Ctrl+Z** on desktop (spec principle 6; `toast.svelte.ts`).
- **After Undo: "Undone: " and the change's own words,** with the original capital letter: "Undone: Used 200 g spinach", "Undone: Removed Oil from Ingredients" (`undo.svelte.ts`, `client/changes.ts`). When only some could be put back, the server's own sentence is added: "Undone: Used about ½ tub Yogurt. Yogurt is back in Ingredients, with ½ tub in the Fridge." (api, "Remove a food").
- **Already done is said, not repeated:** "Oil is already on the shopping list." (Pantry) and "Milk is already on the list · 2 L" (Shopping add box) (spec "Tap a staple…", "Adding something that's already on the list").
- **A note, not a pop-up, when two people clash:** "Wren ticked this too", "Wren added milk too", "Wren put coriander in the Freezer", each with Undo (spec "Offline shopping-list sync").
- **A problem toast** (for something that didn't work) uses the same calm voice and offers "Try again" (see section 7).

## 7. Error messages

**How one is built: what happened, then what to do.** Short, plain, no codes, no blame, no "Error". The server writes its own sentence in `detail` and the app shows it as it is (api, top).

Patterns in use:

- **Couldn't + the verb + a way forward:** "Couldn’t load the pantry. Please try again." · "Couldn’t load your ingredients. Please try again." · "Couldn’t load this ingredient. Check your connection and try again." (`pantry.svelte.ts`, `ingredients.svelte.ts`, `foodEditor.svelte.ts`)
- **Connection:** "Can't reach your Mealwright server. Check your connection." (`api.ts`). In an offline-capable place the offline wording of section 8 is used instead.
- **Anything else:** "Something went wrong. Please try again." (`api.ts`)
- **Asking for the right thing in a field:** say what to type, with an example: "Please enter your name." · "Please choose a username." · "Use at least 10 characters." · "Use up to 50 lowercase letters, numbers, dots, dashes or underscores." · "Give the size a name, like tub or packet." · "Try something like ½ packet or 250 g." · "Use g, kg or one of its sizes, like packet." (`setup/+page.svelte`, `IngredientEditor.svelte`, `amountEdit.ts`)
- **Never a raw status code or a stack trace**; logs stay on the server and never hold what people cook, buy or type (spec section 7, Logs).

(See section 11 for three different endings the built messages use today.)

## 8. Offline and connection wording

All from spec principle 16 and "Offline shopping-list sync" (cabledrawer 17 to 18 Oct); built in `network.svelte.ts`, `ConnectionStatus.svelte`, `OfflineNote.svelte`, `shopping/view.ts`, `store.svelte.ts`.

- **Nothing extra while all is well.** A short blip shows nothing.
- **Bar, phone:** "Offline — 3 changes waiting" (singular "1 change waiting"), with "Try now". **Desktop:** "Offline", with "Try now", and under it "3 changes waiting. They'll save when you're back." In the collapsed sidebar a small dot that is also the "Try now" button.
- **Back:** the toast "Back online — all saved" (short, goes by itself).
- **Shopping subtitle:** "12 to buy · saved" when connected; offline "12 to buy · offline, saving on this phone" (on a computer "…on this computer"); extra lists "Extra list · 5 · offline".
- **A screen that needs the server:** "You're offline." then "Pantry needs your Mealwright server — your shopping list works offline." (naming Pantry, Ingredients or Settings), with a **Shopping** button. "+ Add to pantry" stays visible and says "Adding to the pantry needs your Mealwright server. Try again when you're back online."
- **A phone that has never loaded the list:** "Your shopping list isn't on this phone yet. It'll be here after you've opened it once while connected."
- **"Changes", never "actions", "operations" or "mutations"; "waiting", never "queued" or "pending".**

## 9. Signing in and out

From spec "Sign in", "Sign-out warning", "Offline shopping-list sync" (cabledrawer 17 and 18 Oct); built in `sign-in/+page.svelte`, `setup/+page.svelte`, `settings/+page.svelte`, `offline/held.ts`.

- Sign in page: "Welcome back", "Sign in to your household's kitchen", fields **Username**, **Password** (with **Show** / **Hide**), the switch "Stay signed in for 30 days" (see section 11), button **Sign in** ("Signing in…" while it works), "Forgot your password? Ask your household's admin to reset it." (no email reset: nothing leaves the server), "Your own server · nothing is sent anywhere else".
- First run: "Welcome! First, your account", "You're the first person here, so you'll be the admin…", button **Create account**; "No default password and no account with us. This login lives only on your server."
- Password turned off by the admin: only the single-sign-on button and "Trouble signing in? Ask your household's admin."
- **Plain http:// connection:** "This connection isn't secure" with "Signing in needs a secure connection. Open Mealwright at its https:// address, through your reverse proxy." (refused) or the warning "This connection isn't secure. Passwords travel unencrypted. Use only for testing on a network you trust." (allowed) (spec section 7).
- **Sign out with nothing waiting:** just signs out. **With changes waiting:** "3 changes haven't been sent yet. If you sign out now, they're lost." (1: "1 change hasn't been sent yet. If you sign out now, it's lost.") Buttons: **Try sending now · Stay signed in · Sign out and lose them**.
- **Can't check what's waiting:** "This phone couldn't check for changes waiting to be sent. Nothing has been deleted." Buttons: Try again · Stay signed in · Sign out anyway — anything waiting on this phone may be lost.
- **Another login on a phone holding changes:** "Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." If someone else signs in anyway: "Wren's 3 changes haven't been sent yet. If you carry on, they're lost." Buttons: Sign in as Wren instead · Carry on and lose them. After being signed out for this: "You were signed out because Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." (1 change: "…Wren's change is waiting… to send it.")
- **A phone that can't delete its offline copy:** "This phone couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again."
- **Expired session:** "Please sign in again." with the number of changes kept: "Please sign in again. Your 3 changes are kept on this phone."

## 10. Phone and computer

- **"this phone" / "this computer" is chosen by layout, not by device:** with the bottom tabs the app says "this phone"; with the sidebar it says "this computer", so a tablet held wide says "computer" (spec "This phone or this computer", cabledrawer 18 Oct). Used in offline subtitles, the sign-in messages and the held-changes messages.
- **Phone first** (spec principle 1): write for the phone and let the desktop add detail. The desktop never reads worse than the phone.
- **Tap on a phone, click on a computer:** screen text avoids both and says what happens ("Open", "Choose"). Where the two must differ, the phone word is tap and the computer word is click: "· tap for dates" / "· click for dates" in a pantry row (`PantryGroup.svelte`).
- **Keyboard:** names for keys are written as people say them: "Ctrl+Z" (Cmd+Z on a Mac), "Escape closes".
- **Same wording on both**, unless the space is very tight: shorter forms are for the phone only and are listed here ("Shop" under the tab, "Offline — 3 changes waiting" on the phone bar versus two lines on desktop).

## 11. Differences found (for cabledrawer)

Nothing was chosen. Each line says what disagrees and where, so you can rule on it once and the list is then fixed.

1. **"item(s)".** `e2e/REVIEW.md` lists "items" as a word the checker rejects. The spec itself uses it ("Tick an item = 1 tap", "Add an item…" on Shopping) and the screens say "17 items · 3 use soon" (Pantry), "Add an item…" / "Add item" (Shopping), "Cleared 2 ticked items", "Ticked items go straight into the pantry." and "ticked items still go to the pantry". Rule needed: is "item" fine for things on a shopping list (and the Pantry count), or should these become "ingredient(s)"? (Proposed for your OK: keep "item" for shopping-list lines only; say "ingredients" for the Pantry count; delete "items" from the checker's rejected list and write "items" as "allowed on the shopping list".)
2. **The sign-in switch.** Spec "Sign in (drawn 17 Oct)": a "Remember this phone/computer" switch (30 days). The built page says "Stay signed in for 30 days". And "Stay signed in" is also the name of the sign-out warning's button, which means "cancel signing out". Two meanings for one phrase.
3. **Apostrophes.** The app uses both the curly ’ ("Couldn’t…", "Don’t count it", "How it’s counted", "isn’t a staple") and the straight ' ("Can't reach your Mealwright server", "This connection isn't secure", "You're offline.", "Your shopping list isn't on this phone yet", the sign-in and sign-out messages in `offline/held.ts`). The spec text is written with straight ones. Needs one choice (curly is the proper typographic one).
4. **Three endings for errors.** "Couldn’t save — try again" (dash, no full stop: `foodEditor.svelte.ts`, `client/changes.ts`, `IngredientEditor.svelte`) · "Couldn’t add it — try again." (dash and full stop: `NewIngredient.svelte`) · "Couldn’t load the pantry. Please try again." (full stops, "Please": `pantry.svelte.ts`, `ingredients.svelte.ts`) · "Couldn’t add that ingredient." (no way forward: `AddToPantry.svelte`). Section 7 says "what happened, then what to do"; these need one shape.
5. **"on the list" and "on the shopping list".** Shopping says "Milk is already on the list · 2 L"; Pantry says "Oil is already on the shopping list." Both are in the spec, one for each screen. Listed so it is a choice rather than an accident.
6. **Shopping subtitle online.** The spec words only the offline and held states ("12 to buy · offline, saving on this phone", "— all saved"). Built online: "10 to buy · saved", and "N to buy · synced with Wren" when someone else is on the list. The online sentence is not in the spec.
7. **"Change log" versus "Recent changes".** Spec "Settings" has "Your data → … change log" and everywhere else "Recent changes". Settings isn't built yet beyond Appearance and Sign-in.
8. **"Try now / Try sending now / Try again".** Three retry buttons (section 5, rule 4). They mean different things and each is in the spec or built that way. Listed in case you would rather have one word.
9. **"Shop" and "Shopping".** The phone tab says "Shop" and the page says "Shopping" (spec "Layout decisions"; `nav.ts`). Fine in the mockups; listed for completeness.
10. **Empty-state sentences.** Today and Plan say "This is where you'll see/plan…"; Pantry says "Add what's in your fridge and cupboards, and Mealwright keeps count."; Ingredients says "No ingredients yet. They're added when you put something in the pantry or import a recipe."; Recipes says "Your recipes will be here." Tone varies from "This is where…" to a plain instruction. The spec has no rule for empty states yet.
11. **Capital after "Undone:".** "Undone: Used 200 g spinach" keeps the capital of the original sentence (built). A lower case ("Undone: used 200 g spinach") would read more like one sentence. Built wording was kept here.

12. **An exclamation mark.** The first-run heading is "Welcome! First, your account" (from the drawn mockup); nothing else on screen uses one, and the error rule in section 7 says calm. Left as built.

## 12. Not covered yet (for later versions of this list)

Recipe screens (0.4), Today (when built), Plan (0.6), cook mode, import review, onboarding beyond the first account, Settings sections not built, notifications (after 1.0), and any word an error from the server uses that the app doesn't build itself. Add each with its source when it is built (the gallery and this list change in the same pull request as the screen).
