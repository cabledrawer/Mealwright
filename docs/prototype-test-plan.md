# Mealwright — clickable prototype and test plan (planning step 5)

Written 17 Oct 2026; checked against the canvas on 17 Oct 2026 (later the same day), 15 screen groups / 62 linked artboards. Goes with the spec (`claude/kitchen-app-spec.md`, step 5 and UX principle 10). Prototype lives on the Design canvas "Mealwright mockups" (artifact Ux4u2mYZtAfmagKn5EuxK1).

## The prototype

The existing artboards are the prototype: their buttons are real links, so there is one source and every canvas edit keeps the prototype current. Press **Play** on an artboard to click through; a green sticky left of the grid explains this.

**Link check (17 Oct):** every link points at a real screen, none jump between phone and desktop, and every screen can be reached by clicking from Sign in.

**Start points**

- Phone, first run: *Sign in · phone* → "First time here? Set up Mealwright" → *Onboarding · phone* (Continue / Skip → Today)
- Phone, everyday: *Sign in · phone* → Sign in → *Today · phone*
- Desktop: *Sign in · desktop* (→ Today, or → *Onboarding · desktop* → Finish setup / Skip → Today)

**Before the session, set these Tweaks** (they choose which state a screen shows):

- *Today*: firstDay **off** (normal day, shows "Did you cook Sambar?"). Turn it on only if you test the first-day empty state.
- *Shopping*: **Offline** (shows the offline bar and "Did you buy 2?" card). "Try now" switches it to Back online during Play.
- *Sign in*: passwordLogins **on**.

**Linked paths (all four sets: phone/desktop × light/dark)**

- Sign in → Today; Sign in → "First time here?" → Onboarding → Today; Settings → Sign out → Sign in
- Bottom tabs (phone) and sidebar (desktop) between Today · Plan · Shopping · Pantry · Recipes
- Avatar → Settings (phone: Today avatar only; desktop: sidebar avatar)
- Today → "Did you cook Sambar?" → Cooked it → "Cooked it" review; Move it → Plan; Didn't → card goes away
- Today (first day) → Import a recipe / Add what's in your cupboards / Plan a meal
- Plan: Week ⇄ Month; phone "+ Add dinner" → All recipes
- Phone Recipes tab → All recipes → recipe page; All recipes → Import a recipe / Drafts · 3 / Ingredients
- Recipe → Start cooking → Cook mode → "Next step" → "Cooked it" review → Confirm → Pantry
- Recipe → Cook once, eat for… → Add tubs to the plan → Plan
- Recipe → Plan it → Plan; Today → Find a recipe / Shop list / Open plan
- Import review → Save · Save & plan it; leaving → "Save as draft?" → Save draft → Drafts
- Desktop sidebar → Drafts, Ingredients (under Recipes)
- Theme switch: Dark (in light) or Light/Auto (in dark) jumps to the same screen in the other theme

**What the prototype can't do (tell the tester up front)**

- Most drags, switches, steppers, ticks and filters are drawn but don't change anything. A few do: Cook mode's "Ingredients for this step" switch and "Show ingredients" sheet, Shopping "Try now", Today "Didn't".
- Cook mode shows one step; "Next step" jumps straight to the "Cooked it" review.
- Onboarding shows one step; Continue goes to Today.
- Each screen shows one fixed state (e.g. Plan phone already has the long-press sheet open; Ingredients phone has the edit sheet open).

## Gaps found while checking (for cabledrawer)

Fixed since the first version of this plan: phone now has an All recipes screen with "Import a recipe" (Import review reachable on phone); canvas count now matches the handoff (15 screens).

Fixed 17 Oct (canvas version 77, cabledrawer's go-ahead): the **Skip** button is gone from the phone "Cooked it" review (light and dark), matching desktop and the spec; phone Today "Find a recipe", Plan "+ Add dinner" and Pantry "recipes that use them" now open **All recipes** instead of the Sambar page (light and dark). Desktop unchanged — its Recipes screen is list and recipe together.

Still open:

3. **Phone Settings is only reachable from the Today avatar.** No avatar on Plan, Shop, Pantry or Recipes. That's the thing task 9 tests (principle 13), so leave it for the test — but expect it to come up.
4. **Ingredients on phone has one way in** (All recipes → Ingredients). Fine for v1 per spec ("tap any ingredient anywhere opens the same editor" — that rule isn't drawn).

## Test with a non-technical person

**Setup:** 30–40 minutes, one person, on a phone if possible (phone breaks ties). Set the Tweaks above, open the canvas full-window on *Sign in · phone* and hand it over. Ask them to think aloud. Don't help or explain; if they're stuck for ~30 seconds, note it and move them on. Write down where they tap first, where they hesitate, and words they use for things.

Say first: "This is a picture of an app, not the real thing. Some buttons work, some don't. You can't break it. I'm testing the app, not you."

**Tasks** (read out one at a time, in plain words — don't use the button names). Tasks 1–9 are the core; if time is short, drop the *optional* ones.

1. **First run.** "Someone has installed this for your household. Get it ready the way you'd like." → Sign in → "First time here?" → Onboarding → Today. *Watch:* do they find "First time here?" or try to sign in; do they understand the amounts choice; do they read Skip as safe or as losing something?
2. **Glance.** "Without tapping anything: what are you eating for dinner today, and how much cooked food is left?" → Today. *Watch:* do "tubs left" and "tub 2 of 4" make sense without explanation (principle 7)?
3. **Yesterday's dinner.** "The app is asking you something about last night. You did cook it — tell it." → Today "Did you cook Sambar?" → Cooked it → review. *Watch:* do they understand nothing changes until they answer; is "Move it" clear?
4. **Shopping, no signal.** "You're in the shop and the signal has dropped. What do you need? Tick off the milk." → Shop tab (Offline). *Watch:* do they notice the offline bar and trust ticks are saved; do they understand "Did you buy 2?"; do they get the split by shop, the "check you have these" card and the list picker (This week · Party on Saturday)?
5. **Use things up.** "What in your fridge needs using soon? Find something to make with it." → Today "Use soon" or Pantry → Recipes. *Watch:* which route they choose, and which recipe they pick from All recipes.
6. **Cook.** "Cook the sambar, then tell the app you've cooked it." → Recipes → Start cooking → Cook mode → Cooked it review → Confirm. *Watch:* do they find "Show ingredients"; do they try the experimental per-step switch and understand "may be wrong"; in the review, do Before → After and the Use switches read right; do they trust what it's going to change; do they notice "Remember for next time"?
7. **Batch cook.** "You want the biryani to last for four lunches this week." → Recipe → Cook once, eat for… → Add tubs to the plan. *Watch:* do the patterns (Lunches · Lunch & dinner · Dinners · I'll pick) make sense; do they find where the tubs land?
8. **Look ahead.** "See what's planned for the rest of October." → Plan → Month. *Watch:* do they find the Week | Month toggle?
9. **Dark mode.** "Make the screen darker for the evening." → avatar → Settings (phone), sidebar theme switch (desktop). *Watch:* how long it takes on phone — principle 13 says the switch must be in plain sight (see gap 3).
10. *Optional* — **Half a packet.** "You used about half a bag of rice outside the app. Tell it what's left." → Pantry → rice → ½. *Watch:* do quarters (¼ · ½ · ¾ · Full) feel natural; do grouped packets with dates make sense?
11. *Optional* — **Import and come back later.** "Add a recipe from a website, but stop halfway — you'll finish it tomorrow." → Recipes → Import a recipe → leave → Save draft → Drafts. *Watch:* is "Save as draft?" understood; do they find Drafts again?
12. *Optional* — **Fix an ingredient.** "The app calls it 'toor dal'; you call it 'thuvaram paruppu'. Teach it." → Recipes → Ingredients → edit sheet. *Watch:* do they find Ingredients under Recipes; is "other names" clear?

**Afterwards ask:** What was confusing? What would you use most? Anything you expected to find and didn't? Would you use this instead of what you do now? Did anything make you worry about your data or privacy?

**Record per task:** done / done with help / not done · time · first tap · quotes. Anything that fails for the tester becomes a canvas comment (change on all four versions) and, if it changes a decision, a line in the spec.
