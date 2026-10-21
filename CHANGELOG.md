# Changelog

All notable changes to Mealwright are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers follow the plan in `docs/spec.md` section 8: 0.N.0 per build milestone (not published), then MAJOR.MINOR.PATCH from 1.0.0.

## [Unreleased]

Work towards 0.4.0 (recipes).

### Added

- The recipe page on the phone: tap a recipe in All recipes. It shows the name, description and time, nutrition per serving ("unknown" for what nobody typed, never 0), the ingredients with where each one is (its place, "On list", "Staple", "Not enough", or nothing when missing), the method with its headings, tags, and the source note. "Serves 4" with − and + changes the amounts on screen only (whole servings 1 to 99; the saved recipe never changes; the stock marks and "N missing" follow the chosen servings: enough for the recipe at the chosen servings, or any stock when the amounts can't be compared). A line shows your own words and the ingredient's name in small text only when it differs. Tapping an ingredient opens the ingredient editor; a line that uses another recipe opens it. "Keep screen awake" starts off every time, turns itself off when you leave the page, and is not shown where the browser can't do it. "1 missing · Add to the list" adds what is neither in stock nor already on the shopping list, with one Undo for all of it (it works offline like a staple tap); it is not shown when nothing is left to add, and a recipe that uses a recipe that is not checked never says "all in stock". Recipes need the server. Plan it, Start cooking, Cook once, Edit, Delete and the photo are not on the page yet.
- API: `GET /recipes/{id}/stock` says where each ingredient line is (in stock and where, staple, short, missing), with the same rules as the list's hints, read in a fixed number of queries.
- Keeping the UI good: the recipe page's parts are in the gallery; a saved screenshot of the page (phone-light and desktop-dark); browser tests for every state, 200% text, keyboard use and reduced motion.
- All recipes on the phone (the Recipes tab): the count in the title, the Ingredients button, search, the filter row (All, Can cook now, then your tags) and the list A to Z. Each row says how long it takes, its calories ("nutrition unknown" when not given, never 0) and what is in stock ("all in stock", "all in stock but 1", "2 missing", "Uses spinach (today)"). A recipe that uses another recipe that is not made ahead (or one made ahead that has no pantry ingredient yet, or one since deleted) is never "all in stock" and is left out of Can cook now, because inner recipes are not checked yet (it says "1 missing" if something checked is missing, and no stock words otherwise). Freezer stock counts as in stock. A recipe with no photo has a plain warm square. Search looks in recipe names, tags and ingredient names, other names included ("thuvaram" finds recipes with toor dal), never in the method. Recipes need the server, like Pantry. The "+ New recipe" and Drafts buttons are not there yet.
- API: `GET /recipes` takes `q`, `tag` and `can_cook_now`, and each recipe comes with its calories, a stock summary and what it uses that is about to go off (and `stock_unchecked`, true when it uses a recipe that is not checked), read in a fixed number of queries however many recipes there are.
- The bottom tabs no longer overlap at 200% text size.
- Recipes: the data and the API, with no screens yet. A recipe holds its name, a one-line description, time, servings (a new recipe starts at 4), "Makes", tags, nutrition per serving (an empty box stays "unknown", never 0), ingredient lines and method steps (with headings), and a source note. Recipes can use other recipes as ingredients, to any depth, and a loop is refused with the chain named. A recipe can be marked made ahead, which adds its own ingredient (switch it off and on again and the kept ingredient is linked back, with its stock; while it is on, that ingredient can't be removed, and the refusal says which recipe makes it). Saving is all at once, and a second person saving over a change is stopped and told who made it. Deleting is at once and can be undone for 7 days.
- Ingredients: merging moves recipe lines to the ingredient you keep (and "made its own ingredient again" puts them back); removing an ingredient keeps each line's words, unlinks it, and Undo links it again; "used in N recipes" and a "Not in any recipe" filter are in the API.
- Database: one change adds the recipe tables (recipes, lines, steps, tags and the photo record). Nothing existing is rewritten.
- Names: tabs, line breaks and invisible control characters are now refused in every name, including the names of ingredients, shops and shopping lists that already exist when they are changed. Names already saved are not touched. The two joiners that Tamil and Malayalam need, emoji sequences (families, flags such as Scotland's) and variation selectors are allowed.
- Recipe photos (API only, no screens yet; cabledrawer 19 and 20 Oct): one photo per recipe, JPEG, PNG or WebP up to 15 MB and 50 megapixels (a bigger JPEG is opened at a reduced size, so memory stays low). Each photo is turned upright, its hidden details (camera, date, the place it was taken, comments) are removed, colours are made sRGB and see-through parts white, and it's kept on your own server as two JPEGs (a large copy and a small one for the list); the file sent isn't kept. A photo is uploaded first and only goes on the recipe when the recipe is saved. Uploads that aren't saved on a recipe are deleted after 24 hours, and a household can have at most 10 of them at once. A save that leaves the photo out keeps it; "Remove photo" sends an explicit removal (cabledrawer 20 Oct). Photos are sent so the browser keeps no copy, like everything else. Replacing or removing a photo deletes its files when the recipe is saved; so does the deletion for good 7 days after a recipe is deleted, and Undo keeps it.
- Database: one more change for photos: a photo can be without a recipe while it's waiting to be saved, and its list copy's size is kept. Nothing existing is lost; going back to the earlier version deletes only the photos that were never saved on a recipe.
- New dependency: Pillow 12.3.0 (MIT-CMU licence), to read and clean photos. It makes the image about 30 MB bigger (cabledrawer 20 Oct: OK).
- Docs only: spec section 6 records the 0.4 recipe decisions; receipts and prices are recorded as an idea only (nothing changes in 0.4 to 0.9); the non-technical prototype test moves to 0.9 with the private trial.
- Keeping the UI good: the approved word list (`docs/dev/words.md`), a development-only component gallery at `/dev/gallery`, stress screenshots (many items, long names, 200% text), a browser code size limit in `./check` (170 KiB gzip), a slow-phone browser test, saved Pantry and Shopping screenshots, a stronger reduced-motion rule and keyboard-only tests for the desktop screens.
- More space between words: Plus Jakarta Sans's own space is narrow, so the text now has a little extra word spacing (buttons and text boxes too). Titles and the wordmark are unchanged.
- Spec and plan: "Keeping the UI good" and "Faster working" (cabledrawer 18 and 19 Oct).

### Fixed

- Opening the app offline or on a weak signal shows Today and the saved shopping list at once (cabledrawer 20 Oct, hand test). In 0.3.0 a signal where requests hang rather than fail held a blank screen for about 30 seconds, then "Loading…" on Shopping for up to 75 seconds when changes were waiting. Now the app waits at most half a second for the server, opens as the person last signed in on this device, and tries the network in the background; the list updates when the server answers. Waiting changes still start sending as the app opens, and are sent once, not three times. If the server then says the sign-in has run out, it goes to sign in as usual; if it names another login, that login is signed out again and goes to the sign-in page (nothing is wiped while the screen is up), where the usual warning or wipe follows.

### Security
- certifi 2026.7.22 → 2026.10.19 (the server's list of trusted certificates), for GHSA-6q48-6c7w-9gw2 (critical, CVSS 9.1). vite 8.3.1 → 8.3.3 (a build tool only, not in the app), for GHSA-587h-7wmj-h5pm (high, 7.5), GHSA-698v-4r3x-3vcv and GHSA-r825-w8mm-5pxw (medium, 6.3).
- Pillow 12.3.0 → 13.0.0 (reads and shrinks recipe photos), for nine warnings: GHSA-8g5g-8vmr-9782 / CVE-2026-112403 (critical, CVSS 9.2, JPEG decoding); GHSA-c6hw-5grf-ff96 / CVE-2026-112404 and GHSA-pchr-8j38-3x4p / CVE-2026-112896 (high, 8.8); GHSA-58r4-6rv3-gfh8 / CVE-2026-112397, GHSA-65qm-jvmh-6pqg / CVE-2026-112400, GHSA-p4wg-p73j-c528 / CVE-2026-112895 and GHSA-q45j-58j2-45rg / CVE-2026-112897 (high, 8.7); GHSA-vx6w-vv9f-6gvg / CVE-2026-112899 (medium, 6.9) and GHSA-462x-pgg6-55fp / CVE-2026-112395 (medium, 6.5). Its licence (MIT-CMU) is unchanged and it has no dependencies of its own. No other library changed.
- At most 10 live-update streams per sign-in; past that the oldest closes, and its tab quietly stops live updates (no offline bar) until it is looked at again.
- Signing out ends that sign-in's live updates at once.
- Requests bigger than 4 MiB are refused ("That's too much to send in one go."). A photo upload may be up to 15 MB ("That photo is bigger than 15 MB."); nothing else may.
- A number too big for the database is refused instead of causing a server error.
- In https mode (the default) browsers are told to use only https for Mealwright's address for a year (HSTS, without `includeSubDomains` or `preload`). Never sent in plain-http mode.
- A sign-in without "Remember this phone" (or computer) now lasts at most 30 days in total, even when used every day, the same as with it. It still ends after 12 hours without use.
- New kept tests: every endpoint refuses a signed-out visitor; one household can't reach another's lists, ticks, notes, changes or live updates.

## [0.3.0] - 2026-10-19

The shopping list milestone: shared shopping lists with a Shopping screen, ticking items into the pantry, and a phone that keeps working without a connection (ticks and adds are kept on the phone and sent later). Also live updates, an installable app, and a few small Pantry and Ingredients improvements. Not published; for testing on cabledrawer's homelab.

**Before you install it: back up your data.** This version changes the database (the shopping lists are new tables and columns; nothing existing is rewritten), and the old version can't read a database the new one has changed. On the server (from `docs/dev/test-on-homelab.md`, section 4.1; replace `<folder>` with the folder that holds your `compose.yaml`):

```bash
cd <folder>
OLD=$(grep -oE 'image: *mealwright:[^ ]+' compose.yaml | cut -d: -f3)
echo "Current version: $OLD"
docker compose stop mealwright
sudo tar -C <folder> --exclude=data/logs -czf "backups/data-$OLD-$(date +%Y%m%d-%H%M).tar.gz" data
sudo chmod 600 backups/data-*.tar.gz
ls -lh backups/       # the new backup should be there, and not tiny
```

- `cd` goes to the Mealwright folder.
- The `OLD=` line reads which version you are running now from `compose.yaml`, and the next line shows it, so the backup's file name says which version it belongs to.
- `docker compose stop mealwright` stops the app, so the database file is copied in one piece.
- The `tar` line makes a dated, compressed copy of the `data` folder in `backups/`, leaving out the log folder.
- `chmod 600` lets only its owner read the backup.
- `ls -lh backups/` shows the new file; it should be there and not tiny.

To go back, follow section 5 of the same file (restore that backup and set the image tag back to 0.2.1).

### Added

**Shopping**

- **Shopping lists.** Every household has a main list, "This week", that can be renamed but never removed, and any number of extra lists that can be made, renamed and removed, with Undo. A line is an ingredient with an amount; adding an ingredient that is already on the list says so instead of adding it twice. Changes to a list can be undone for 7 days.
- **The Shopping screen.** The list is split by shop, then by aisle, with ticked items folded into "In the trolley · N" at the end of each shop and "Clear ticked" (with Undo). Ingredients with no usual shop go under "Any shop". Tap an amount to change it or take the line off the list. The add box finds ingredients by any of their names. Each ingredient now has an aisle; ingredients you already had get a starting aisle from the bundled table.
- **Typing a name that isn't an ingredient yet** offers "+ New ingredient", which asks **"How do you count it?"** (By weight, By volume, One by one, or Don't count it for a staple), with the likely answer picked first and its packet sizes asked up front. The same question comes from a new **+ New ingredient** button on Ingredients. **+ Staple** is now on the phone's Pantry too: a name nobody has used becomes a new staple, with nothing recorded in the pantry. The guess comes from the bundled table on your server (`GET /api/v1/foods/guess`); nothing is looked up on the internet.
- **Ticking puts the shopping into the pantry.** A tick files what you bought in the ingredient's usual place (Cupboard if it has none), with no use-by date. On the phone a toast says where it went, with **Change** (another place) and Undo; on desktop a **Put away** panel beside the list does the same. Unticking, or Undo, takes it back out and never takes the pantry below zero. **Different pack?** changes what the pantry got ("What did you buy?"), and an item with no amount offers **How much?** instead. Staples and items with no amount put nothing in the pantry. Every tick shows in Pantry's Recent changes ("Bought 2 packets Toor dal → Cupboard") with Undo.
- **Two phones, one list.** Nothing is ever refused with a pop-up because someone else changed the list: the server applies changes in the order it receives them, and where it matters it leaves a **quiet note** under the item, with Undo and a dismiss button, such as "Wren had removed this. Your tick still went into the pantry.", "Wren added milk too" or "Wren changed Milk to 2 L" ("Your other phone" when it was you). Nine kinds of clash have a note (N1 to N9 in `docs/dev/sync-protocol.md`).
- **"Did you buy 2?"** When two phones tick the same item while offline, a card asks, with **Yes, 2** and **Just 1**; the first answer settles it for everyone, and Undo brings the card back. Just 1 takes the extra packet back out of the pantry.
- **Sync for phones** (`POST /api/v1/shopping/actions` and `GET /api/v1/shopping/changes?since=N`): a phone sends a batch of its changes, each with its own ID so that sending one twice does nothing the second time, and gets back an answer for each and everything that changed since it last looked. The batch is described in `docs/dev/sync-protocol.md`, and both are in the OpenAPI document.

**Offline**

- **It works without a connection.** Ticks, adds and every other change to a list are kept on the phone, shown at once, and sent when the connection is back: one batch at a time, in order, tried again after a pause if the server can't be reached. Closing the app doesn't lose them. (iPhone Safari can clear a web app's saved data after about 7 days without use; adding Mealwright to the Home Screen helps.) While offline the bar says "Offline — 3 changes waiting" (on desktop "3 changes waiting. They'll save when you're back."), Shopping's subtitle says "12 to buy · offline, saving on this phone", and when everything is sent a toast says "Back online — all saved".
- **Opening the app offline.** The app opens as the person last signed in on that phone, and Shopping works from the phone's copy, including finding ingredients in the add box. Pantry, Ingredients and Settings need your server: offline they say "You're offline. Pantry needs your Mealwright server — your shopping list works offline." with a Shopping button. Settings still has Sign out and the theme switch, and "+ Add to pantry" says it needs the server. A phone that has never loaded the list says "Your shopping list isn't on this phone yet. It'll be here after you've opened it once while connected."
- **Signing in running out doesn't lose changes.** If your sign-in runs out while offline, the changes stay on the phone: "Please sign in again. Your 3 changes are kept on this phone." Signing back in as the same person sends them at once. A different person is warned first ("Wren's 3 changes haven't been sent yet. If you carry on, they're lost.", with "Sign in as Wren instead" and "Carry on and lose them") and nothing is ever sent under their login.
- **A different login always starts clean.** When someone else signs in on a phone, its offline copy is wiped, as at signing out, and the next start makes a new device ID. A wrong password wipes nothing.
- **Signing out sends first.** Sign out tries to send what is waiting. If something is still unsent: "3 changes haven't been sent yet. If you sign out now, they're lost." with Try sending now, Stay signed in and Sign out and lose them. Signing out wipes the phone's offline copy (the offline database, saved lists and ingredient names, and everything the app kept for the household in the browser), and other tabs of the app clear themselves and go to the sign-in page.
- **A storage error is never "nothing waiting".** If the browser can't read the app's offline store, nothing is deleted or written on that result. The same login carries on (cabledrawer 18 Oct): it never wipes anything. Anyone else pressing Sign in is told "This phone couldn't check for changes waiting to be sent. Nothing has been deleted.", with Try again and "Carry on anyway — anything waiting on this phone may be lost". Settings says the same instead of signing out, with Try again, Stay signed in and "Sign out anyway — anything waiting on this phone may be lost" (cabledrawer 18 Oct). Both "anyway" choices wipe as usual.
- **Signing out loses only the changes the warning showed.** If another tab queues more after "3 changes haven't been sent yet" appears, "Sign out and lose them" warns again with the new count instead of losing them. Adding a change and wiping take turns across tabs (the browser's Web Locks), so a change added at that moment is never lost unseen.
- **A phone that can't delete its offline copy lets nobody in.** If a wipe can't delete the offline store, it is never opened or used again, the session is still ended, and the sign-in page says "This phone couldn't delete its offline copy of the household. Nobody can sign in on it until that's done. Close other Mealwright tabs or restart the browser, then Try again." with a Try again button (cabledrawer 18 Oct). Until Try again has deleted it, the whole sign-in form is disabled (cabledrawer 18 Oct).
- **Carrying on loses only the changes the warning showed.** The sign-in warning remembers which of Wren's changes it showed. If another tab has queued a different one since, it warns again with the new count instead of losing it.
- **No bouncing when the server won't sign out.** If the server answers the sign-out with an error, the sign-in page stays and says "Couldn't finish signing out on this phone." with Try again, instead of going back and forth between the app and the sign-in page. Nothing is deleted. A Try again the server refuses says it again, read out.
- **The sign-in page says why you were signed out** (cabledrawer 18 Oct): "You were signed out because Wren's 3 changes are waiting on this phone. Sign in as Wren to send them." ("Wren's change … to send it" for one; "this computer" on a computer.)
- **Sign in is busy from the first press.** Sign in shows "Signing in…" and ignores a second press (or Enter) straight away, so a quick second press can't start a second sign-in while the phone is still being checked.
- **"Couldn't finish signing out" has a grey Try again**, the quiet look, on that screen only; every other Try again is the main button.
- **"Still stuck?" under the offline copy message.** Under "This phone couldn't delete its offline copy of the household…" one small line says: "Still stuck? Clear this site's data in your browser's settings." The README has a matching Troubleshooting entry.

**Live updates, installing and connection**

- **Live updates.** A second phone or window sees a tick, an added item or a pantry change within a moment, without reloading. They come from your own Mealwright server only (`GET /api/v1/events`, Server-Sent Events); the stream carries numbers, never names. An open screen doesn't count as activity, so the 12-hour sign-out still happens; a kitchen tablet should use "Remember this phone".
- **Installable app.** A manifest, icons made from the brand icon, and a service worker that keeps only the app's own files, so the app's own files (its code, fonts and icons) load without a connection. The screens still need your server; Shopping works offline from the phone's copy (see Offline above). It never keeps anything from the server (`/api`) and never updates itself mid-use: a new version starts the next time every window has been closed. No Install button yet.
- **Connection bar.** "Offline" with Try now on every page (above the tabs on a phone, at the foot of the sidebar on desktop), a short "Back online" toast, and "12 to buy · offline" on Shopping. A blip under 3 seconds shows nothing. With changes waiting it says "Offline — 3 changes waiting" (see Offline above).

**Pantry and Ingredients**

- **Tap a staple to add it to the shopping list.** On Pantry, a staple chip adds that ingredient to the main shopping list with the toast "Oil added to the shopping list · Undo". A small tick shows on the chip while it is on the list; tapping a ticked chip adds nothing more and says "Oil is already on the shopping list." The tap goes through the same add action and waiting list as Shopping, so a tap made while the connection is failing is kept on the phone and sent once, when the server is back. Screen readers hear "Add Oil to the shopping list" or "Oil, on the shopping list". An "Edit staples" link under the chips opens Ingredients with the Staples filter.
- **"+ List" on running-low rows** (hidden in 0.2 until the shopping list worked) does the same for that ingredient (toast with Undo, tick, "already on the shopping list", works through the waiting list).
- **Recent changes on Ingredients.** New ingredients, Staple on or off, removals, merges and edits, each with Undo for 7 days: on desktop a one-line "Recent changes · 9" bar above the editor ("· 10+" past ten) opens the list in the side column; on the phone a "Recent changes" button opens a sheet. It updates after changes you make here, when stock changes anywhere, and when you come back to the page; an ingredient edited on another phone doesn't appear live yet. Pantry's Recent changes still lists stock changes only.
- **Server:** `GET /api/v1/changes?area=ingredients` lists ingredient changes (and their Undos) only, for your household only. No database change for this.
- **Marks in an opened Pantry row.** An opened row with a single packet shows the ¼ · ½ · ¾ · Full marks, with "About 250 g left · type it instead" under them (the link opens the packet menu at "What's left", with the box ready). In a narrow desktop column the marks go two by two, each at least 44 px wide. If saving a mark fails, its tick goes back. The arrow keys move between the marks.

### Changed

- **Collapsed sidebar:** the Recipes icon opens a small pop-out with All recipes, Drafts and Ingredients, the current page marked. It works with the keyboard and screen readers (a menu).
- **Add to pantry:** "Pick a date" opens the phone's date picker straight away and then shows the date it chose ("Sat 24 Oct") on the chip. The separate Date field is gone, and cancelling the picker changes nothing. The Use-by chips now choose as the arrow keys move, like the app's other chip groups; "Pick a date" opens its picker only on Space, Enter or a tap, never just because focus arrived on it. Screen readers announce the chip once, not also the hidden date field behind it.
- **Pantry search** shows one list of results, each with its place ("Toor dal · Cupboard") and "also called thuvaram paruppu" when another name matched. On the phone there is a "Search pantry" field above the tabs, with the same one-list results.
- **Undo says what it undid:** "Undone: Removed Oil from Ingredients", for Ctrl+Z and the toast's Undo.
- **Use soon card:** "Lemon · Today" and "Tomorrow" start with a capital, like the Today chip.
- **Recent changes shows its verb in bold** on every change worded verb first: Added, Removed, Renamed, Merged, Undid, "Added other name …", "Removed other name …" and "Forgot your weight of …". An ingredient that happens to be called "Added sugar" is not bolded by mistake.

### Database

- **One migration** (`f509d7a1c609`): six new tables for the shopping lists (`shopping_list`, `list_item`, `list_tick`, `sync_action`, `list_note` and `double_tick`), `aisle` and `version` on ingredients, `tick_id` on changes, and `list_seq` and `list_purged_seq` on the household. It makes each household's main list "This week" and gives existing ingredients a starting aisle from the bundled table. Nothing existing is rewritten. Checked by tests that build a 0.2.1 database with real-looking data, upgrade it, and also go back down and up again.
- Old shopping-list notes and answered questions are tidied away after 7 days, and removed lists and lines after 12 months, by the same hourly background job that summarises old pantry history. A phone that was behind a tidy-up gets a fresh copy of the lists; changes still waiting on it are kept and sent after.

### Privacy and security

- **Nothing new leaves your server.** Live updates, the sync endpoints and the app's service worker talk only to your own Mealwright server, and the conversions table and the "How do you count it?" guess stay on it too.
- **The live stream carries numbers, never names.**
- **Every `/api` answer is sent with `Cache-Control: no-store`, and the service worker never keeps anything from `/api`.**
- **What the phone keeps, and when it goes.** The offline copy of the lists lives in the browser's own database (IndexedDB). Signing out, or a different person signing in, wipes it, along with the app's other saved data about the household. A sign-in that merely runs out keeps it on purpose, so the changes waiting aren't lost. Besides the theme and sidebar choices and two flags for an unfinished sign-out or wipe, the only thing put in `localStorage` is the last login's number and username (no password or session), so the app knows whose phone it is when the offline copy can't be read; the wipe removes it too.
- One household can never see or change another's lists, notes, questions or changes (tested on every endpoint). An ID from another household is answered exactly like one that doesn't exist.

### For developers

- New dependency: **idb 8.0.3** (ISC; approved by cabledrawer 17 Oct), a small helper for the browser's IndexedDB. No other new dependency.
- The sync protocol is written up in `docs/dev/sync-protocol.md` and tested with two- and three-phone tests (random queues from several phones keep the pantry and the list honest); the Shopping screen writes only through one function, `sendAction`, that puts a change on the phone's queue first.
- `GET /api/v1/changes?area=ingredients` lists ingredient changes only, for your household only.
- `docs/dev/test-on-homelab.md` explains how to build the image, copy it to the server and go back; no registry is used in 0.x.

## [0.2.1] - 2026-10-18

Fixes from cabledrawer's hand test of 0.2.0, plus a few small Pantry improvements from his friction log. Not published; for testing on cabledrawer's homelab.

**Before you install it: back up your data.** This version changes the database (one small addition), and the old version can't read a database the new one has changed. On the server (from `docs/dev/test-on-homelab.md`, section 5):

```bash
cd ~/mealwright
docker compose stop mealwright
sudo tar -C ~/mealwright --exclude=data/logs -czf "backups/data-0.2.0-$(date +%Y%m%d-%H%M).tar.gz" data
ls -lh backups/
```

- `cd` goes to the Mealwright folder.
- `docker compose stop mealwright` stops the app, so the database file is copied in one piece.
- The `tar` line makes a dated, compressed copy of the `data` folder in `backups/`, leaving out the log folder.
- `ls -lh backups/` shows the new file; it should be there and not tiny.

To go back, follow section 6 of the same file (restore that backup and set the image tag back to 0.2.0).

### Fixed

- **Pantry search finds other names.** Typing "thuvaram" in "Find in pantry" now finds Toor dal, the same way Recipes › Ingredients does (one shared piece of matching code). The count at the top of each place now matches what is shown.
- **Recent changes "before → after" counts what was already there.** "Added 1 pack Paneer" with 200 g already in the Fridge now reads "1 pack · 200 g → 2 packs · 400 g", not "0 g → 1 pack · 200 g". The same for Used, and for the "Undid:" lines. Each new change saves the whole amounts it saw, so the line stays right after later changes. Undo itself is unchanged; tests now check it puts back exactly the right amounts. Changes recorded before 0.2.1 keep their old wording (the packets that change touched).
- **"+ Staple" can make a new ingredient.** Type a name nobody has used and choose "+ New ingredient: …"; it is made with Staple on and no stock is recorded.
- **A size needs a name with letters in it** ("packet", "tub", "dozen"). "1" is refused on screen and by the server, with "Give the size a name, like tub or packet." The Name box now hints "packet, tub, dozen…".
- **A full, unopened pack has the ¼ · ½ · ¾ · Full choices** in its menu too (Full is ticked), not only once it is open.
- **Undoing an older "Used" for a removed ingredient says so:** "Undone: Used about ½ tub Yogurt. Yogurt is back in Ingredients, with ½ tub in the Fridge."

### Changed

- **Add to pantry** has a "Today" use-by choice next to No date, +3 days, +1 week and Pick a date.
- The grey example in the amount box suits the unit (200 for g, 1 for kg or a size, 250 for ml, 6 for items).
- In an opened pantry row, "Used" (and "Save" for counted foods) stays greyed out until an amount is typed.
- The pack lines in an opened pantry row ("1 pack · 200 g · use by today") show an arrow and a press colour, so it is clear they open the pack menu.

### Database

- One migration: two empty columns on `change_line` (`total_before_milli`, `total_after_milli`) hold the whole amounts a change saw. Nothing is rewritten. Checked by a test that builds a 0.2.0 database with real-looking data, upgrades it, and also goes back down and up again.

## [0.2.0] - 2026-10-17

Milestone 0.2 (Ingredients, pantry, history and undo): the shared ingredient list, a pantry that counts things the way they're sold, and Undo for every change. Not published; for testing on cabledrawer's homelab.

### Added

- **Ingredients** (Recipes › Ingredients): one list of everything you buy and cook with, shared by recipes, the pantry and (from 0.3) shopping. Search finds an ingredient by any of its names. Filters: All · Staples · Maybe the same.
- **The ingredient editor**, the same one from anywhere: a side panel on desktop, a sheet on phone. Everything saves as you go:
  - name and other names ("thuvaram paruppu", "arhar dal");
  - how it's counted (by weight, by volume, one by one) and how it's sold ("Packet = 500 g", one marked Usual);
  - weight of 1 cup or of one, running low at, where it lives, usual shop ("+ Shop" adds one), Staple;
  - "Can use instead".
- **Merge** two ingredients into one (their stock and sizes move across), **split** a name back out, and "**Not the same**" for a "Maybe the same" hint. The server decides which ingredient of a pair would be merged away.
- **"Remove from Ingredients"**, only when nothing depends on the ingredient (today: nothing in the pantry). After the 7 days of Undo it's deleted for good, with its monthly history totals. An Undo that would put stock back into a removed ingredient brings it back and says so.
- **Pantry:** places as tabs on phone (All · Fridge · Freezer · Cupboard · More, with Use soon under More) and as four columns beside a side panel on desktop.
  - Amounts **as sold**: "1½ packets · about 750 g", "9 left · bought as a dozen".
  - Each packet is kept with its own use-by date, the oldest is used first, and stock never goes below zero.
  - Tap a packet for Used · Binned · To freezer · Move to… · Change use-by date…, and ¼ · ½ · ¾ · Full for an open pack.
  - "Used some" and "How many left?" (type 0 when it's all gone) for a whole ingredient.
  - **"+ Add to pantry"**: what, how much, where, use by.
- **Use soon:** anything with a use-by of today, tomorrow or the day after (or already past), in the household's local time, with Used · Binned · To freezer.
- **Staples:** assumed in stock and never counted; shown as chips.
- **Recent changes** with Undo: what each change did, one line per ingredient ("Paneer: 0 g → 2 packs · 400 g").
- **Undo for every ingredient and pantry change**, by anyone in the household, for 7 days ("Not the same" and adding a shop aren't undone): the Undo toast, and Ctrl+Z / Cmd+Z on desktop. Inside a text box, Ctrl+Z undoes your typing instead. If something has been used since, Undo puts back what it can and says so.
- **Instant changes:** the screen updates straight away and saves in the background. If saving fails, it goes back and says "Couldn't save — try again".
- **"Ask once":** when Mealwright needs a weight it doesn't know ("About how much does 1 cup of Toor dal weigh?"), it asks once and can remember the answer. Your answers always beat the built-in table.
- **A built-in conversion table** of 221 common ingredients from USDA FoodData Central, SR Legacy (public domain, CC0 1.0). Credit: "Food conversion data: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy, 2018. fdc.nal.usda.gov."
- **Places** Fridge, Freezer, Cupboard and Spice rack, added to every household.
- **History:** pantry changes older than 12 months are summarised as monthly totals by a background job (at start-up and every hour), so it also works on a server that's off at night.
- **API** under `/api/v1` for ingredients, places, shops, the pantry, changes and Undo, with safe retries (`Idempotency-Key`). It's described in `docs/dev/api-0.2.md` and the OpenAPI document.

### Changed

- **"Ingredient", never "food", on screen** (cabledrawer's rule). A test fails if "food" appears in any on-screen text or server message.
- **Names appear exactly as typed** everywhere, screen-reader labels included.
- **The household's time zone and cup size** are taken once from an admin's browser (never from location) and never changed silently. No `TZ` setting is needed. "Weight of 1 cup" follows the household's cup: 240 ml for a US English browser, otherwise 250 ml.
- **The nightly log tidy** from 0.1.1 now runs on the app's scheduler (APScheduler). It still keeps 14 days, and catches up if the server was asleep at midnight.
- **Recipes** in the desktop sidebar is a tree: All recipes · Drafts · Ingredients. Drafts is empty until 0.5.

### Privacy and security

- No new outside connections. The conversion table is bundled; the app never fetches it.
- Nothing about what people cook or buy is written to the log.
- One household can never see or change another's ingredients, places, shops, pantry or changes (tested on every endpoint).

### For developers

- New dependencies: **APScheduler 3.11.3** and **tzlocal 5.4.4** (MIT, ship in the image). For tests only: **Hypothesis** (MPL-2.0) with sortedcontainers (Apache-2.0), and **@axe-core/playwright** with axe-core (MPL-2.0).
- `./check` allows 0BSD, Unlicense, CC0-1.0 and Zlib for development-only packages (cabledrawer's standing rule), and `CHECK_IMAGE` lets two copies run at once.
- Accessibility checks (axe in light and dark, 44 px targets, no sideways scroll) run in the browser tests, and there's a screenshot tool for mockup reviews (`e2e/review/`).

## [0.1.1] - 2026-10-17

### Fixed

- **Sign-in shows the real wait** after too many wrong passwords: "30 seconds" at first, then 1 minute, 2 minutes and so on, up to 15 minutes. It used to say "1 minute" when the wait was 30 seconds. (Found by cabledrawer while testing 0.1.0.)
- **Every sign-in is logged**, including the one at first setup, which signs the admin in. A test checks there is exactly one "Signed in" line per sign-in. (Found by cabledrawer.)

### Changed

- **Log lines carry the time** (UTC, e.g. `2026-10-17T18:21:50Z`).
- **The app keeps its own log for 14 days**, in `/data/logs/mealwright.log`, readable by Mealwright's own user only. Just after each midnight (UTC) it starts a new file and deletes files last written more than 14 days ago, even on a quiet server. Later, "Report a problem" will read recent errors from it. **Sign-in lines go only to this file, never to the container output** (`docker logs`), because Docker can only limit its copy by size, so on a quiet server it would keep them for months. The container output now holds start-up messages, warnings and errors. `compose.example.yaml` also limits Docker's copy to 2 files of 1 MB as a safety net. Leave `data/logs` out of backups (the update backup in the homelab guide already does). (Asked by cabledrawer.)
- **The sign-in slow-down is logged** when it starts or doubles ("Sign-in slowed down for tess from 192.168.1.20 (wait 30 s)"). Each refused try isn't logged, so nobody can fill the disk by hammering the sign-in page. (Asked by cabledrawer.)
- The sign-in slow-down no longer keeps memory for usernames and addresses that were only looked up.

### Privacy and security

- **A blocked outside connection is logged in plain words and names only the switch** ("recipe import is switched off"), never the site or address, which could show what someone was cooking. A test checks it. (Asked by cabledrawer.)
- **Database errors no longer show what people typed.** Such an error's text used to include the values in the query (for example a typed username), and it would reach the log as part of the error. The values are now hidden. (Found by the review of this patch.)
- **Usernames that don't exist aren't written to the log.** Someone who types their password into the username box would otherwise have it logged. The log says "unknown user" instead. (Found by cabledrawer.)

## [0.1.0] - 2026-10-17

Milestone 0.1, Foundation: an empty but real Mealwright you can install, sign in to and click around, with the safety rails built in. Not published; for testing on cabledrawer's homelab.

### Added

- **One Docker image** with the web app and its API. It runs as an unprivileged user (UID 10001), keeps everything in `/data`, has a health check, and contains no `pip`. `compose.example.yaml` shows how to run it behind a reverse proxy.
- **First run:** the first visitor creates the admin account (there's no default admin), then the app opens.
- **Sign in and out**, with "Remember this device" for 30 days. Passwords need at least 10 characters and are stored scrambled (Argon2). After 5 wrong guesses, sign-in slows down, per account and per real address, so one person's guesses don't slow down anyone else.
- **The app shell:** bottom tabs on phone and a collapsible sidebar on desktop, with empty Today, Plan, Shopping, Pantry and Recipes pages and a Settings page with Sign out.
- **Auto · Light · Dark** in plain sight, saved to your account. A designed dark theme, with fonts bundled.
- **One switch component** for every on/off.
- **API** under `/api/v1`, described at `/api/v1/openapi.json`. `GET /api/v1/version` reports the version for update tools such as Diun.
- **Database changes are applied on start-up** (migrations: household, Privacy switches, logins and sessions).
- **`./check`** runs every check before each pull request: lint, types, tests, browser tests, licence allow list, pip-audit, osv-scanner, Bandit, and Trivy plus a no-telemetry check on the image.
- Licence (AGPL-3.0), README, contributing guide, security policy, this changelog, and the homelab testing guide (`docs/dev/test-on-homelab.md`).

### Privacy and security

- **The outbound gate:** the only way Mealwright connects to anything outside your server. Each kind of connection has its own Privacy switch, and **all of them are off**. While the app runs, any other connection or address lookup is refused, whether it comes from our code or a library.
- **No telemetry:** FastAPI's built-in telemetry is switched off, and no telemetry package is installed (checked in the code and in the image).
- **Strict browser rules (Content Security Policy):** pages load files only from your own server. A real-browser test proves an outside script is blocked. Location, camera and microphone are off; referrers aren't sent.
- **Logs** hold only sign-ins and errors, never what people view or search for (the web server's request log is off).
- **HTTPS is required for sign-in.** On a plain `http://` address, Mealwright says so instead of failing silently; `MEALWRIGHT_ALLOW_PLAIN_HTTP` allows it for testing, with a warning.
- **Works behind any reverse proxy.** Its forwarded headers are believed only from `MEALWRIGHT_TRUSTED_PROXIES` (off by default).
- Requests from other sites are refused, and the session cookie can't be read by scripts and is stored only as a fingerprint.

[Unreleased]: https://git.example.org/tess/mealwright/compare/v0.3.0...main
[0.3.0]: https://git.example.org/tess/mealwright/src/tag/v0.3.0
[0.2.1]: https://git.example.org/tess/mealwright/src/tag/v0.2.1
[0.2.0]: https://git.example.org/tess/mealwright/src/tag/v0.2.0
[0.1.1]: https://git.example.org/tess/mealwright/src/tag/v0.1.1
[0.1.0]: https://git.example.org/tess/mealwright/src/tag/v0.1.0
