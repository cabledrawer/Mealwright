<script lang="ts">
  import { tick, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import Button from '$lib/components/Button.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import OfflineNote from '$lib/components/OfflineNote.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ThemeSwitch from '$lib/components/ThemeSwitch.svelte';
  import { network } from '$lib/network.svelte';
  import {
    cantCheckText,
    loseOnSignOutText,
    STILL_CANT_REACH,
    UNREADABLE,
    type Unreadable
  } from '$lib/offline/held';
  import { signOutHere, trySending, type Waiting } from '$lib/offline/signOut';
  import { session } from '$lib/session.svelte';

  // Who is shown stays put while signing out (session.me goes first).
  const who = untrack(() => session.me);

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
      await goto(resolve('/sign-in'), { replaceState: true, invalidateAll: true });
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

<div class="sections">
  <!-- Settings needs the server (spec section 6, "Opening the app offline"). Two parts still
       work offline, so they stay: the theme switch, which is saved on this device (cabledrawer
       18 Oct: "Keep it visible"), and signing out (docs/dev/sync-protocol.md section 12).
       Anything added to Appearance later that needs the server is hidden offline. -->
  {#if network.offline}
    <OfflineNote screen="Settings" />
  {/if}
  <section class="section" aria-labelledby="appearance">
    <h2 id="appearance">Appearance</h2>
    <div class="card">
      <div class="row">
        <span class="label">Theme</span>
        <ThemeSwitch variant="pill" />
      </div>
    </div>
  </section>

  <section class="section" aria-labelledby="privacy">
    <h2 id="privacy">Privacy</h2>
    <div class="card">
      <a class="row to" href={resolve('/settings/privacy')}>
        <span class="who">
          <span class="label">Outside connections</span>
          <span class="detail">Recipe import, recipe photos and your own network</span>
        </span>
        <Icon name="back" size={18} stroke={2.4} />
      </a>
    </div>
  </section>

  <section class="section" aria-labelledby="sign-in">
    <h2 id="sign-in">Sign-in</h2>
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
        <button type="button" class="lose" disabled={busy} onclick={() => void signOutNow('anyway')}
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
</div>

<style>
  .sections {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 640px;
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
</style>
