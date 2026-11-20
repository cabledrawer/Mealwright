<script lang="ts">
  import { onMount, tick, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import Button from '#lib/components/Button.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import {
    cantCheckText,
    loseOnSignOutText,
    STILL_CANT_REACH,
    UNREADABLE,
    type Unreadable
  } from '#lib/offline/held.js';
  import { signOutHere, trySending, type Waiting } from '#lib/offline/signOut.js';
  import { cancelMyResetLink } from '#lib/client/people.js';
  import { network } from '#lib/network.svelte.js';
  import { household, sentence } from '#lib/people.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import SignInSection from '../SignInSection.svelte';
  import { plural } from '#lib/words.js';
  import { PHONE_QUERY } from '#lib/layout.js';

  // Who is shown stays put while signing out (session.me goes first).
  const who = untrack(() => session.me);
  const admin = who?.role === 'admin';

  // An unused reset link made for you, admin or not (spec "Pe1"): you can cancel it here, so a
  // member (who isn't shown the Household pages) still can. Placement proposed, for cabledrawer.
  onMount(() => {
    void household.load();
  });
  const resetPending = $derived(
    household.people.find((person) => person.is_me)?.login?.reset_pending ?? false
  );
  let resetProblem = $state<string | null>(null);
  async function cancelReset() {
    if (network.offline) return;
    resetProblem = null;
    try {
      await cancelMyResetLink();
      await household.load();
      toasts.show('Reset link cancelled');
    } catch (error) {
      resetProblem = sentence(error);
    }
  }

  let busy = $state(false);
  /** Changes not sent yet: the warning is showing. */
  let left = $state(0);
  /** Which changes the warning showed: "Sign out and lose them" loses those, never others. */
  let shown: string[] = [];
  let stillCant = $state(false);
  /** The phone database couldn't be read: whether anything is waiting isn't known. */
  let cantCheck = $state(false);
  const device = matchMedia(PHONE_QUERY).matches ? 'phone' : 'computer';

  /** What's still waiting decides: sign out, warn, or (couldn't check) wait. */
  function found(waiting: Waiting | Unreadable): number {
    cantCheck = waiting === UNREADABLE;
    shown = waiting === UNREADABLE ? [] : waiting.ids;
    return waiting === UNREADABLE ? 0 : waiting.count;
  }

  // Settings › Your sign-in › Sign out returns to Sign in (spec). Changes still waiting are sent first, for
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

<PageHeader
  title="Your sign-in"
  overline="You"
  subtitle="Your own password and the devices you are signed in on."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<section class="section" aria-label="Your sign-in">
  {#if resetPending}
    <div class="card pending">
      <p>
        Someone made a reset link for your password, and it hasn’t been used yet. If you didn’t ask
        for one, cancel it.
      </p>
      <Button quiet disabled={network.offline} onclick={() => void cancelReset()}
        >Cancel the link</Button
      >
      {#if resetProblem}<p role="alert">{resetProblem}</p>{/if}
    </div>
  {/if}
  <SignInSection {device} {admin} part="mine" />
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
        >Sign out and lose {plural(left, 'it', 'them')}</button
      >
    </div>
  {/if}
</section>

<style>
  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 760px;
  }

  .card {
    padding: var(--space-1) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .pending {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
    padding-block: var(--space-5);
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

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
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
</style>
