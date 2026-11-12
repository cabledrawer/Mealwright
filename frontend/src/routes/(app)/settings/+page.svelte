<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import Button from '#lib/components/Button.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import { batchCook } from '#lib/batchCook.svelte.js';
  import Switch from '#lib/components/Switch.svelte';
  import AmountsChoice from '#lib/components/AmountsChoice.svelte';
  import YourKitchen from '#lib/components/YourKitchen.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import ThemeSwitch from '#lib/components/ThemeSwitch.svelte';
  import { ApiError, cantReach } from '#lib/api.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { getShops, getPlaces } from '#lib/client/foods.js';
  import {
    changeAmountsShown,
    changePints,
    getHousehold,
    getKitchen,
    type Kitchen
  } from '#lib/client/household.js';
  import { getMealSlots } from '#lib/client/plan.js';
  import { getPeople } from '#lib/client/people.js';
  import { checkMode, type CheckMode } from '#lib/checkMode.svelte.js';
  import type { AmountsShown, Pints } from '#lib/client/types.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { privacy } from '#lib/privacy.svelte.js';
  import { updates } from '#lib/updates.svelte.js';
  import { UPDATE_AVAILABLE, UPDATE_TAG } from '#lib/aboutWords.js';
  import { THEME_LABELS, theme } from '#lib/theme.svelte.js';
  import {
    cantCheckText,
    loseOnSignOutText,
    STILL_CANT_REACH,
    UNREADABLE,
    type Unreadable
  } from '#lib/offline/held.js';
  import { signOutHere, trySending, type Waiting } from '#lib/offline/signOut.js';
  import { VERSION_WORDS } from '#lib/version.js';
  import { session } from '#lib/session.svelte.js';
  import MealSlots from './MealSlots.svelte';
  import PhoneList from './PhoneList.svelte';
  import RecentSection from './RecentSection.svelte';
  import ShopsPlaces from './ShopsPlaces.svelte';
  import SignInSection from './SignInSection.svelte';
  import type { Group, Row } from './sectionIcons.js';
  import { GROUPS, SECTION_ORDER, type SectionId } from './sectionOrder.js';

  // Who is shown stays put while signing out (session.me goes first).
  const who = untrack(() => session.me);

  // --- Pints (0.6 import; the words are proposed, for cabledrawer) -----------------------------------
  /** The household's pint, once the server has said (null until then, and when it can't). */
  let pints = $state<Pints | null>(null);
  let pintsProblem = $state<string | null>(null);
  /** How amounts are shown (0.9 U2; cabledrawer 12 Nov). Read with the pint. */
  let amountsShown = $state<AmountsShown>('as_written');
  const admin = who?.role === 'admin';

  /** The two ways Check can look on the phone (F141; words are the mockup's). */
  const CHECK_MODE_CHOICES: { value: CheckMode; label: string; hint: string }[] = [
    {
      value: 'focus',
      label: 'Focus',
      hint: 'The whole list, with the app’s menu hidden. Close keeps it in Drafts.'
    },
    {
      value: 'one',
      label: 'One at a time',
      hint: 'Each line that needs you, then every step of the method. Back and Next.'
    }
  ];

  /** The kitchen's equipment for Batch cook (B1), once the server has said. */
  let kitchenNow = $state<Kitchen | null>(null);
  let kitchenOpen = $state(false);
  let kitchenOpener = $state<HTMLElement | null>(null);
  function readKitchen() {
    getKitchen().then(
      (found) => (kitchenNow = found),
      () => {} // offline or unreachable: the row stays hidden, as Amounts does
    );
  }

  /** One string, so the two sentences always have their space between them (RF5). */
  const kitchenWords = $derived(
    'Batch cook never plans more at once than your kitchen has.' +
      (kitchenNow && !kitchenNow.asked
        ? ' Not asked yet: Batch cook asks the first time you use it.'
        : '')
  );

  /** An admin hides or shows Batch cook (Experimental); it flips back if the server can't take it. */
  let batchProblem = $state<string | null>(null);
  async function setBatchCook(on: boolean) {
    batchProblem = null;
    const before = batchCook.shown;
    batchCook.shown = on;
    try {
      await batchCook.set(on);
      kitchen.wroteSettings(); // Recent changes shows "Switched Batch cook off" (RF5, H8)
    } catch (error) {
      batchCook.shown = before;
      batchProblem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    }
  }

  function readPint() {
    getHousehold().then(
      (household) => {
        pints = household.pints;
        amountsShown = household.amounts_shown ?? 'as_written';
      },
      () => {} // offline or unreachable: the row stays hidden, the rest of Settings still works
    );
  }
  function readPints() {
    readKitchen();
    void batchCook.load();
    readPint();
  }
  onMount(readPints);
  // An Undo from Recent changes (or the toast) may have put the Batch cook switch or the kitchen's
  // equipment back: read them again (RF5, H8).
  let undoneSeen = kitchen.elsewhere;
  $effect(() => {
    if (kitchen.elsewhere === undoneSeen) return;
    undoneSeen = kitchen.elsewhere;
    readKitchen();
    void batchCook.load();
    readPint();
  });
  // Opened offline: the row shows once the connection comes back.
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      if (pints === null) readPints();
    }
  });

  /** How amounts are shown (0.9 U2): the choice moves at once; if it can't be saved it goes back. */
  async function setAmountsShown(next: AmountsShown) {
    const before = amountsShown;
    pintsProblem = null;
    amountsShown = next;
    try {
      amountsShown = (await changeAmountsShown(next)).amounts_shown;
      kitchen.wroteSettings();
    } catch (error) {
      amountsShown = before;
      pintsProblem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    }
  }

  /** The switch flips at once and is sent; if it can't be saved it flips back and says so. */
  async function setPints(us: boolean) {
    const before = pints;
    pintsProblem = null;
    pints = us ? 'us' : 'uk';
    try {
      pints = (await changePints(pints)).pints;
      kitchen.wroteSettings();
    } catch (error) {
      pints = before;
      pintsProblem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    }
  }

  // --- The section list (cabledrawer 7 Nov): computer, a list on the left; phone, a list at the top.
  // The sections follow one another in one scroll (spec: "phone: one grouped list"); choosing
  // one in the list goes to it. Meal slots are for admins only: hidden for everyone else.
  const visible = $derived<Record<SectionId, boolean>>({
    appearance: true,
    amounts: pints !== null,
    household: true,
    'meal-slots': admin,
    'shops-places': true,
    'your-kitchen': kitchenNow !== null,
    'recent-changes': true,
    privacy: true,
    'sign-in': true,
    'your-data': true,
    about: true
  });
  const SECTIONS = $derived(SECTION_ORDER.filter((section) => visible[section.id]));
  let current = $state('appearance');

  // --- The phone (F193, cabledrawer 9 Nov, option B; mockups Dark-Settings08-Phone and
  // Dark-SettingsSlots08-Phone): a grouped list, and each section on its own page ("?section=…",
  // or the "#…" an older link ends with), with "‹ Settings" to come back. The computer keeps its
  // list of sections beside all of them, and goes to the section a link names.
  let phone = $state(matchMedia('(max-width: 767px)').matches);
  $effect(() => {
    const media = matchMedia('(max-width: 767px)');
    const onChange = () => (phone = media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  });

  /** The section a link asks for, if it is one shown to this person. */
  const asked = $derived.by(() => {
    const id = page.url.searchParams.get('section') ?? page.url.hash.slice(1);
    return SECTIONS.find((section) => section.id === id)?.id ?? null;
  });
  /** On the phone, the one section that has the page (null: the list). */
  const only = $derived(phone ? asked : null);
  /** A section is drawn on a computer always, on the phone only when it has the page. */
  const showing = (id: string) => !phone || only === id;
  const heading = $derived(SECTIONS.find((section) => section.id === only)?.label);

  // What the list's rows show (proposed, for cabledrawer: the words under "Settings" in the mockup).
  let slotsOn = $state<number | null>(null);
  let shopsCount = $state<number | null>(null);
  let placesCount = $state<number | null>(null);
  let peopleCount = $state<number | null>(null);
  const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  const privacyOn = $derived(
    privacy.loaded && privacy.problem === null
      ? Object.values(privacy.switches).filter(Boolean).length + (privacy.entries.length ? 1 : 0)
      : null
  );

  function readRowValues() {
    if (admin)
      getMealSlots().then(
        (slots) => (slotsOn = slots.filter((s) => s.enabled).length),
        () => {}
      );
    getShops().then(
      (shops) => (shopsCount = shops.length),
      () => {}
    );
    getPlaces().then(
      (places) => (placesCount = places.length),
      () => {}
    );
    void privacy.load().catch(() => {});
    getPeople().then(
      (found) => (peopleCount = found.people.length),
      () => {}
    );
    if (admin) void updates.load();
  }
  // Each time the list is shown (first, and coming back to it from a section): read the values.
  $effect(() => {
    if (phone && only === null) untrack(readRowValues);
  });

  /** One row of the phone's list for a section, or none when this person doesn't see it. */
  function rowFor(id: SectionId): Row | null {
    switch (id) {
      case 'appearance':
        return {
          id,
          label: 'Appearance',
          icon: 'appearance',
          value: THEME_LABELS[theme.choice]
        };
      case 'amounts':
        return pints === null
          ? null
          : {
              id,
              label: 'Amounts',
              icon: 'amounts',
              value: pints === 'us' ? 'US pints' : 'UK pints'
            };
      case 'meal-slots':
        return admin
          ? {
              id,
              label: 'Meal slots',
              icon: 'meal-slots',
              value: slotsOn === null ? undefined : `${slotsOn} on`
            }
          : null;
      case 'shops-places':
        return {
          id,
          label: 'Shops & places',
          icon: 'shops-places',
          value:
            shopsCount === null || placesCount === null
              ? undefined
              : `${plural(shopsCount, 'shop', 'shops')} · ${plural(placesCount, 'place', 'places')}`
        };
      case 'your-kitchen':
        return kitchenNow === null
          ? null
          : {
              id,
              label: 'Your kitchen',
              icon: 'your-kitchen',
              value: `${kitchenNow.hob_rings} hob ${kitchenNow.hob_rings === 1 ? 'ring' : 'rings'}`
            };
      case 'recent-changes':
        return { id, label: 'Recent changes', icon: 'recent-changes' };
      case 'household':
        return {
          id,
          label: 'Household',
          icon: 'household',
          href: resolve('/(app)/settings/household'),
          value: peopleCount === null ? undefined : plural(peopleCount, 'person', 'people')
        };
      case 'privacy':
        return {
          id,
          label: 'Privacy',
          icon: 'privacy',
          href: resolve('/(app)/settings/privacy'),
          value: privacyOn === null ? undefined : privacyOn === 0 ? 'All off' : `${privacyOn} on`
        };
      case 'your-data':
        return {
          id,
          label: 'Your data',
          icon: 'your-data',
          href: resolve('/(app)/settings/your-data')
        };
      case 'sign-in':
        return { id, label: 'Sign-in', icon: 'sign-in' };
      case 'about':
        return {
          id,
          label: 'About',
          icon: 'about',
          href: resolve('/(app)/settings/about'),
          // An admin, when the last check found a newer version (spec "Updates", level 3).
          badge: updates.available ? UPDATE_AVAILABLE : undefined
        };
    }
  }

  // The phone's groups: each section's group is named in sectionOrder.ts, and the rows follow
  // that array's order. "Report a problem" (mockup Dark-Settings09-Phone; proposed, for
  // cabledrawer) is a row of its own after About, for everyone.
  const groups: Group[] = $derived(
    GROUPS.map((group) => {
      const rows = SECTION_ORDER.filter((section) => section.group === group.name)
        .map((section) => rowFor(section.id))
        .filter((row): row is Row => row !== null);
      if (group.name === 'Mealwright')
        rows.push({
          id: 'report',
          label: 'Report a problem',
          icon: 'report',
          href: resolve('/(app)/settings/about/report')
        });
      return { ...group, rows };
    })
  );

  async function goTo(id: string) {
    current = id;
    await tick();
    const heading = document.getElementById(id);
    heading?.scrollIntoView({ block: 'start' });
    heading?.focus({ preventScroll: true });
  }

  // A computer opened with "?section=…" goes to that section.
  // The sections above it fill in as they load and push it down, so it stays put until the person
  // scrolls or presses something, or a few seconds have passed.
  // An admin sees "Update available" by About once a check has found a newer version.
  onMount(() => {
    if (admin && !phone) void updates.load();
  });

  let sectionsBox = $state<HTMLElement>();
  onMount(() => {
    if (phone || !asked) return;
    const id = asked;
    void goTo(id);
    if (!sectionsBox) return;
    const again = () => document.getElementById(id)?.scrollIntoView({ block: 'start' });
    const watcher = new ResizeObserver(again);
    watcher.observe(sectionsBox);
    const events = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const;
    const stop = () => {
      watcher.disconnect();
      for (const name of events) window.removeEventListener(name, stop);
      clearTimeout(timer);
    };
    const timer = setTimeout(stop, 4000);
    for (const name of events) window.addEventListener(name, stop, { passive: true });
    return stop;
  });

  let busy = $state(false);
  /** Changes not sent yet: the warning is showing. */
  let left = $state(0);
  /** Which changes the warning showed: "Sign out and lose them" loses those, never others. */
  let shown: string[] = [];
  let stillCant = $state(false);
  /** The phone database couldn't be read: whether anything is waiting isn't known. */
  let cantCheck = $state(false);
  const device = matchMedia('(max-width: 767px)').matches ? 'phone' : 'computer';

  /** What's still waiting decides: sign out, warn, or (couldn't check) wait. */
  function found(waiting: Waiting | Unreadable): number {
    cantCheck = waiting === UNREADABLE;
    shown = waiting === UNREADABLE ? [] : waiting.ids;
    return waiting === UNREADABLE ? 0 : waiting.count;
  }

  // Settings → Sign out returns to Sign in (spec). Changes still waiting are sent first, for
  // up to 5 seconds; if any are left, the one "Are you sure?" of the app says so, because
  // unsent changes can't be undone (docs/dev/sync-protocol.md section 12). When the phone
  // couldn't check what's waiting, it doesn't sign out (nothing is wiped) and says so, with
  // Try again and "Sign out anyway" (cabledrawer 18 Oct).
  async function leave() {
    busy = true;
    try {
      const waiting = await trySending();
      if (waiting === UNREADABLE && cantCheck) {
        // Still can't: the line is put back as new, so it's read out again.
        cantCheck = false;
        await tick();
      }
      left = found(waiting);
      if (left === 0 && !cantCheck) await signOutNow();
    } finally {
      busy = false;
    }
  }

  /** The couldn't-check warning's Try again: looks again, as Sign out does. */
  let trying = $state(false);
  async function tryAgain() {
    trying = true;
    try {
      await leave();
    } finally {
      trying = false;
    }
  }

  async function sendNow() {
    busy = true;
    stillCant = false;
    try {
      left = found(await trySending());
      if (cantCheck) return;
      if (left === 0) await signOutNow();
      else stillCant = true;
    } finally {
      busy = false;
    }
  }

  function stay() {
    left = 0;
    shown = [];
    stillCant = false;
    cantCheck = false;
  }

  /**
   * Wipe this browser, end the session (now, or once the server is back) and sign in again.
   * Only over the changes the warning showed (none when there was no warning): they're read
   * again just before the wipe, and if another tab has queued any other since, nothing is
   * wiped and the warning comes back with the new count, read out again.
   */
  async function signOutNow(choice: string[] | 'anyway' = shown) {
    busy = true;
    const result = await signOutHere(choice);
    if (result === 'signed-out') {
      left = 0;
      await goto(resolve('/(auth)/sign-in'), { replace: true, refreshAll: true });
      return;
    }
    // Take the warning away first, so it's put back (and read out) as new.
    left = 0;
    cantCheck = false;
    stillCant = false;
    await tick();
    left = found(result);
    busy = false;
  }
</script>

{#if only !== null && heading}
  <PageHeader title={heading} parent={{ href: '/(app)/settings', label: 'Settings' }} />
{:else}
  <PageHeader title="Settings" />
{/if}

<div class="layout">
  {#if phone && only === null}
    <PhoneList {groups} />
  {:else if !phone}
    <nav class="list" aria-label="Settings sections">
      <ul>
        {#each SECTIONS as section (section.id)}
          <li>
            <button
              type="button"
              aria-current={current === section.id ? 'true' : undefined}
              onclick={() => void goTo(section.id)}
              >{section.label}
              {#if section.id === 'about' && updates.available}<span class="badge"
                  >{UPDATE_AVAILABLE}</span
                >{/if}</button
            >
          </li>
        {/each}
      </ul>
    </nav>
  {/if}
  <div class="sections" bind:this={sectionsBox}>
    <!-- Settings needs the server (spec section 6, "Opening the app offline"). Two parts still
       work offline, so they stay: the theme switch, which is saved on this device (cabledrawer
       18 Oct: "Keep it visible"), and signing out (docs/dev/sync-protocol.md section 12).
       Once loaded, Amounts stays too, with its switch greyed out while the server can't be
       reached. Anything added later that needs the server is greyed out or hidden the same way. -->
    {#if network.down && pints === null}
      <OfflineNote screen="Settings" />
    {/if}
    {#if showing('appearance')}
      <section class="section" aria-labelledby="appearance">
        <h2 class="title" id="appearance" tabindex="-1">Appearance</h2>
        <div class="card">
          <div class="row">
            <span class="label">Theme</span>
            <ThemeSwitch variant="pill" />
          </div>
          <!-- F141 (cabledrawer 3 Nov), mockup Dark-SettingsCheckMode07-Phone: how Check looks on the
           phone, kept on this device. Shown at every width; the line under it says a computer
           always shows the whole list (the mockup is phone-only, so showing it on a computer too is
           cabledrawer 5 Nov). -->
          <fieldset class="check-mode">
            <legend>Checking a recipe on the phone</legend>
            <span class="detail">How the Check screen looks after an import.</span>
            {#each CHECK_MODE_CHOICES as option (option.value)}
              <label class="choice" class:on={checkMode.choice === option.value}>
                <input
                  type="radio"
                  name="checkmode"
                  value={option.value}
                  checked={checkMode.choice === option.value}
                  onchange={() => checkMode.set(option.value)}
                />
                <span class="dot" aria-hidden="true"></span>
                <span class="choice-words">
                  <span class="choice-name">{option.label}</span>
                  <span class="choice-hint">{option.hint}</span>
                </span>
              </label>
            {/each}
            <span class="detail small">On a computer, Check always shows the whole list.</span>
          </fieldset>
        </div>
      </section>
    {/if}

    {#if pints !== null && showing('amounts')}
      <section class="section" aria-labelledby="amounts">
        <h2 class="title" id="amounts" tabindex="-1">Amounts</h2>
        <AmountsChoice
          value={amountsShown}
          disabled={!admin || network.offline}
          onchange={(next) => void setAmountsShown(next)}
          describedby={admin ? undefined : 'amounts-admin'}
        />
        <div class="card">
          <div class="row">
            <span class="who">
              <span class="label" id="pints-label">Read pints as US pints</span>
              <span class="detail" id="pints-detail">
                {pints === 'us'
                  ? 'A pint is 473 ml (US).'
                  : 'A pint is 568 ml (UK). Switch on for 473 ml (US).'}
              </span>
            </span>
            <Switch
              bind:checked={() => pints === 'us', (on) => void setPints(on)}
              labelledby="pints-label"
              describedby={admin ? 'pints-detail' : 'pints-detail amounts-admin'}
              disabled={!admin || network.offline}
            />
          </div>
        </div>
        {#if !admin}<p class="detail" id="amounts-admin">Only an admin can change this.</p>{/if}
        {#if pintsProblem}<p class="warning-line" role="alert">{pintsProblem}</p>{/if}
      </section>
    {/if}

    {#if showing('household')}
      <section class="section" aria-labelledby="household">
        <h2 class="title" id="household" tabindex="-1">Household</h2>
        <div class="card">
          <a class="row to" href={resolve('/(app)/settings/household')}>
            <span class="who">
              <span class="label">People</span>
              <span class="detail">Who eats here, their portions and who signs in</span>
            </span>
            <Icon name="back" size={18} stroke={2.4} />
          </a>
        </div>
      </section>
    {/if}

    {#if admin && showing('meal-slots')}
      <section class="section" aria-labelledby="meal-slots">
        <h2 class="title" id="meal-slots" tabindex="-1">Meal slots</h2>
        <MealSlots />
      </section>
    {/if}

    {#if showing('shops-places')}
      <section class="section" aria-labelledby="shops-places">
        <h2 class="title" id="shops-places" tabindex="-1">Shops &amp; places</h2>
        <ShopsPlaces />
      </section>
    {/if}

    {#if kitchenNow !== null && showing('your-kitchen')}
      <section class="section" aria-labelledby="your-kitchen">
        <h2 class="title" id="your-kitchen" tabindex="-1">Your kitchen</h2>
        <div class="card" data-testid="your-kitchen">
          <div class="row">
            <span class="label">Hob rings</span><span class="value">{kitchenNow.hob_rings}</span>
          </div>
          <div class="row">
            <span class="label">Pressure cookers</span><span class="value"
              >{kitchenNow.pressure_cookers}</span
            >
          </div>
          <div class="row">
            <span class="label">Oven</span><span class="value"
              >{kitchenNow.oven ? 'Yes' : 'No'}</span
            >
          </div>
          <div class="row">
            <span class="who">
              <span class="label" id="batch-label">Show Batch cook</span>
              <span class="detail" id="batch-detail">
                Experimental. Switched off, it leaves the sidebar and the Plan.
                {#if !admin}Only an admin can change this.{/if}
              </span>
            </span>
            <Switch
              bind:checked={() => batchCook.shown, (on) => void setBatchCook(on)}
              labelledby="batch-label"
              describedby="batch-detail"
              disabled={!admin || network.offline}
            />
          </div>
          {#if batchProblem}<p class="warning-line" role="alert">{batchProblem}</p>{/if}
          <div class="row">
            <span class="who">
              <span class="detail">{kitchenWords}</span>
            </span>
            <button
              type="button"
              class="change"
              disabled={network.offline}
              onclick={(event) => {
                kitchenOpener = event.currentTarget;
                kitchenOpen = true;
              }}>Change</button
            >
          </div>
        </div>
      </section>
    {/if}

    {#if showing('recent-changes')}
      <section class="section" aria-labelledby="recent-changes">
        <h2 class="title" id="recent-changes" tabindex="-1">Recent changes</h2>
        <RecentSection />
      </section>
    {/if}

    {#if showing('privacy')}
      <section class="section" aria-labelledby="privacy">
        <h2 class="title" id="privacy" tabindex="-1">Privacy</h2>
        <div class="card">
          <a class="row to" href={resolve('/(app)/settings/privacy')}>
            <span class="who">
              <span class="label">Outside connections</span>
              <span class="detail"
                >Recipe import, recipe photos, update check and your own network</span
              >
            </span>
            <Icon name="back" size={18} stroke={2.4} />
          </a>
        </div>
      </section>
    {/if}

    {#if showing('sign-in')}
      <section class="section" aria-labelledby="sign-in">
        <h2 class="title" id="sign-in" tabindex="-1">Sign-in</h2>
        <SignInSection {device} {admin} />
        <div class="card">
          <div class="row">
            <span class="who">
              <span class="label">{who?.name}</span>
              <span class="detail">Signed in as {who?.username}</span>
            </span>
            <button
              type="button"
              class="sign-out"
              disabled={busy || left > 0 || cantCheck}
              onclick={leave}>Sign out</button
            >
          </div>
        </div>
        {#if cantCheck}
          <div class="warning">
            <p role="alert">{cantCheckText(device)}</p>
            <Button disabled={busy} onclick={() => void tryAgain()}>
              {trying ? 'Trying…' : 'Try again'}
            </Button>
            <Button quiet disabled={busy} onclick={stay}>Stay signed in</Button>
            <button
              type="button"
              class="lose"
              disabled={busy}
              onclick={() => void signOutNow('anyway')}
              >Sign out anyway. Anything waiting on this {device} may be lost</button
            >
          </div>
        {:else if left > 0}
          <div class="warning">
            <p role="alert">
              {loseOnSignOutText(left)}{#if stillCant}<br />{STILL_CANT_REACH}{/if}
            </p>
            <Button disabled={busy} onclick={() => void sendNow()}
              >{busy ? 'Sending…' : 'Try sending now'}</Button
            >
            <Button quiet disabled={busy} onclick={stay}>Stay signed in</Button>
            <button type="button" class="lose" disabled={busy} onclick={() => void signOutNow()}
              >Sign out and lose {left === 1 ? 'it' : 'them'}</button
            >
          </div>
        {/if}
      </section>
    {/if}

    {#if showing('your-data')}
      <section class="section" aria-labelledby="your-data">
        <h2 class="title" id="your-data" tabindex="-1">Your data</h2>
        <div class="card">
          <a class="row to" href={resolve('/(app)/settings/your-data')}>
            <span class="who">
              <span class="label">Backups, export and starting again</span>
              <span class="detail">How often Mealwright backs up, and how to restore</span>
            </span>
            <Icon name="back" size={18} stroke={2.4} />
          </a>
        </div>
      </section>
    {/if}

    {#if showing('about')}
      <section class="section" aria-labelledby="about">
        <h2 class="title" id="about" tabindex="-1">About</h2>
        <div class="card">
          <a class="row to" href={resolve('/(app)/settings/about')}>
            <span class="who">
              <span class="label">{VERSION_WORDS}</span>
              <span class="detail">Version, updates and how old this version is</span>
            </span>
            {#if updates.available}<span class="badge">{UPDATE_TAG}</span>{/if}
            <Icon name="back" size={18} stroke={2.4} />
          </a>
        </div>
      </section>
    {/if}
    {#if kitchenNow !== null}
      <YourKitchen
        open={kitchenOpen}
        kitchen={kitchenNow}
        onsaved={(saved) => {
          kitchenNow = saved;
          kitchen.wroteSettings(); // Recent changes shows "Changed your kitchen…" (RF5, H8)
          kitchenOpen = false;
          kitchenOpener?.focus();
        }}
        onclose={() => {
          kitchenOpen = false;
          kitchenOpener?.focus();
        }}
      />
    {/if}
    <!-- The sidebar shows the version on a computer; this is the phone's place for it (N1). -->
    <p class="version">{VERSION_WORDS}</p>
  </div>
</div>

<style>
  .version {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    text-align: center;
  }

  @media (min-width: 768px) {
    .version {
      display: none;
    }
  }

  .layout {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
  }

  @media (min-width: 768px) {
    .layout {
      display: grid;
      grid-template-columns: 240px minmax(0, 760px);
      gap: 28px;
      align-items: start;
    }

    .list {
      position: sticky;
      top: var(--space-7);
    }
  }

  .list ul {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .list button {
    width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-field);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-align: left;
    cursor: pointer;
  }

  .list button[aria-current='true'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  /* "Update available" by About, for an admin (X1). */
  .badge {
    flex: none;
    margin-left: var(--space-3);
    padding: 2px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.02em;
    white-space: nowrap;
  }

  .sections {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
    min-width: 0;
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 760px;
    scroll-margin-top: var(--space-7);
  }

  /* On the phone the page's own title says which section this is. */
  @media (max-width: 767px) {
    h2.title {
      display: none;
    }
  }

  h2 {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    padding: var(--space-1) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: 54px;
    padding: var(--space-4) 0;
  }

  .who {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  /* A row that opens another page: its arrow points on (the back icon, turned round). */
  .to {
    color: inherit;
    text-decoration: none;
  }

  .to :global(svg) {
    flex: none;
    color: var(--color-text-muted);
    transform: scaleX(-1);
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .value {
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
  }

  .sign-out,
  .change {
    min-height: var(--touch-target);
    padding: 0 18px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .warning {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .warning p {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .warning-line {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .lose {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: none;
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .check-mode {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
    margin: 0;
    padding: var(--space-5) 0 var(--space-6);
    border: none;
    border-top: 1px solid var(--color-border);
  }

  .check-mode legend {
    padding: 0;
    margin-bottom: var(--space-2);
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .check-mode .small {
    font-size: var(--text-xs);
  }

  .choice {
    display: flex;
    align-items: flex-start;
    gap: var(--space-6);
    min-height: var(--touch-target);
    padding: var(--space-6);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    cursor: pointer;
  }

  .choice.on {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
  }

  .choice {
    position: relative;
  }

  /* The real radio is invisible and covers the card (so the whole card is the target); the dot
     draws it. */
  .choice input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  .dot {
    flex: none;
    width: 22px;
    height: 22px;
    margin-top: 2px;
    border: 2px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    box-sizing: border-box;
  }

  .choice input:checked + .dot {
    border: 6px solid var(--color-accent);
  }

  .choice input:focus-visible + .dot {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  .choice-words {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .choice-name {
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
  }

  .choice-hint {
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    line-height: 1.45;
  }
</style>
