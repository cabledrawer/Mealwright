<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import Button from '#lib/components/Button.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import ThemeSwitch from '#lib/components/ThemeSwitch.svelte';
  import { ApiError, cantReach } from '#lib/api.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { changePints, getHousehold } from '#lib/client/household.js';
  import { checkMode, type CheckMode } from '#lib/checkMode.svelte.js';
  import type { Pints } from '#lib/client/types.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
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
  import RecentSection from './RecentSection.svelte';
  import ShopsPlaces from './ShopsPlaces.svelte';

  // Who is shown stays put while signing out (session.me goes first).
  const who = untrack(() => session.me);

  // --- Pints (0.6 import; the words are proposed, for cabledrawer) -----------------------------------
  /** The household's pint, once the server has said (null until then, and when it can't). */
  let pints = $state<Pints | null>(null);
  let pintsProblem = $state<string | null>(null);
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

  function readPints() {
    getHousehold().then(
      (household) => (pints = household.pints),
      () => {} // offline or unreachable: the row stays hidden, the rest of Settings still works
    );
  }
  onMount(readPints);
  // Opened offline: the row shows once the connection comes back.
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      if (pints === null) readPints();
    }
  });

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
  const SECTIONS = $derived(
    [
      { id: 'appearance', label: 'Appearance', show: true },
      { id: 'amounts', label: 'Amounts', show: pints !== null },
      { id: 'meal-slots', label: 'Meal slots', show: admin },
      { id: 'shops-places', label: 'Shops & places', show: true },
      { id: 'recent-changes', label: 'Recent changes', show: true },
      { id: 'privacy', label: 'Privacy', show: true },
      { id: 'sign-in', label: 'Sign-in', show: true }
    ].filter((section) => section.show)
  );
  let current = $state('appearance');

  async function goTo(id: string) {
    current = id;
    await tick();
    const heading = document.getElementById(id);
    heading?.scrollIntoView({ block: 'start' });
    heading?.focus({ preventScroll: true });
  }

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

<PageHeader title="Settings" />

<div class="layout">
  <nav class="list" aria-label="Settings sections">
    <ul>
      {#each SECTIONS as section (section.id)}
        <li>
          <button
            type="button"
            aria-current={current === section.id ? 'true' : undefined}
            onclick={() => void goTo(section.id)}>{section.label}</button
          >
        </li>
      {/each}
    </ul>
    <p class="later">Household, Your data and About come in 0.9.</p>
  </nav>
  <div class="sections">
    <!-- Settings needs the server (spec section 6, "Opening the app offline"). Two parts still
       work offline, so they stay: the theme switch, which is saved on this device (cabledrawer
       18 Oct: "Keep it visible"), and signing out (docs/dev/sync-protocol.md section 12).
       Once loaded, Amounts stays too, with its switch greyed out while the server can't be
       reached. Anything added later that needs the server is greyed out or hidden the same way. -->
    {#if network.down && pints === null}
      <OfflineNote screen="Settings" />
    {/if}
    <section class="section" aria-labelledby="appearance">
      <h2 id="appearance" tabindex="-1">Appearance</h2>
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

    {#if pints !== null}
      <section class="section" aria-labelledby="amounts">
        <h2 id="amounts" tabindex="-1">Amounts</h2>
        <div class="card">
          <div class="row">
            <span class="who">
              <span class="label" id="pints-label">Read pints as US pints</span>
              <span class="detail" id="pints-detail">
                {pints === 'us'
                  ? 'A pint is 473 ml (US).'
                  : 'A pint is 568 ml (UK). Switch on for 473 ml (US).'}
                {#if !admin}Only an admin can change this.{/if}
              </span>
            </span>
            <Switch
              bind:checked={() => pints === 'us', (on) => void setPints(on)}
              labelledby="pints-label"
              describedby="pints-detail"
              disabled={!admin || network.offline}
            />
          </div>
        </div>
        {#if pintsProblem}<p class="warning-line" role="alert">{pintsProblem}</p>{/if}
      </section>
    {/if}

    {#if admin}
      <section class="section" aria-labelledby="meal-slots">
        <h2 id="meal-slots" tabindex="-1">Meal slots</h2>
        <MealSlots />
      </section>
    {/if}

    <section class="section" aria-labelledby="shops-places">
      <h2 id="shops-places" tabindex="-1">Shops &amp; places</h2>
      <ShopsPlaces />
    </section>

    <section class="section" aria-labelledby="recent-changes">
      <h2 id="recent-changes" tabindex="-1">Recent changes</h2>
      <RecentSection />
    </section>

    <section class="section" aria-labelledby="privacy">
      <h2 id="privacy" tabindex="-1">Privacy</h2>
      <div class="card">
        <a class="row to" href={resolve('/(app)/settings/privacy')}>
          <span class="who">
            <span class="label">Outside connections</span>
            <span class="detail">Recipe import, recipe photos and your own network</span>
          </span>
          <Icon name="back" size={18} stroke={2.4} />
        </a>
      </div>
    </section>

    <section class="section" aria-labelledby="sign-in">
      <h2 id="sign-in" tabindex="-1">Sign-in</h2>
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

  .later {
    margin: var(--space-3) 0 0;
    padding: 0 var(--space-6);
    color: var(--color-text-muted);
    font-size: var(--text-xs);
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

  .sign-out {
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
