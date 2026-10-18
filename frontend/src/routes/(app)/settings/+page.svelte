<script lang="ts">
  import { untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import Button from '$lib/components/Button.svelte';
  import OfflineNote from '$lib/components/OfflineNote.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ThemeSwitch from '$lib/components/ThemeSwitch.svelte';
  import { network } from '$lib/network.svelte';
  import { loseOnSignOutText, STILL_CANT_REACH } from '$lib/offline/held';
  import { signOutHere, trySending } from '$lib/offline/signOut';
  import { session } from '$lib/session.svelte';

  // Who is shown stays put while signing out (session.me goes first).
  const who = untrack(() => session.me);

  let busy = $state(false);
  /** Changes not sent yet: the warning is showing. */
  let left = $state(0);
  let stillCant = $state(false);

  // Settings → Sign out returns to Sign in (spec). Changes still waiting are sent first, for
  // up to 5 seconds; if any are left, the one "Are you sure?" of the app says so, because
  // unsent changes can't be undone (docs/dev/sync-protocol.md section 12).
  async function leave() {
    busy = true;
    try {
      left = await trySending();
      if (left === 0) await signOutNow();
    } finally {
      busy = false;
    }
  }

  async function sendNow() {
    busy = true;
    stillCant = false;
    try {
      left = await trySending();
      if (left === 0) await signOutNow();
      else stillCant = true;
    } finally {
      busy = false;
    }
  }

  function stay() {
    left = 0;
    stillCant = false;
  }

  /** Wipe this browser, end the session (now, or once the server is back) and sign in again. */
  async function signOutNow() {
    busy = true;
    await signOutHere();
    left = 0;
    await goto(resolve('/sign-in'), { replaceState: true, invalidateAll: true });
  }
</script>

<PageHeader title="Settings" />

<div class="sections">
  <!-- Settings needs the server (spec section 6, "Opening the app offline"). Signing out
       still works offline (docs/dev/sync-protocol.md section 12), so that part stays. -->
  {#if network.offline}
    <OfflineNote screen="Settings" />
  {:else}
    <section class="section" aria-labelledby="appearance">
      <h2 id="appearance">Appearance</h2>
      <div class="card">
        <div class="row">
          <span class="label">Theme</span>
          <ThemeSwitch variant="pill" />
        </div>
      </div>
    </section>
  {/if}

  <section class="section" aria-labelledby="sign-in">
    <h2 id="sign-in">Sign-in</h2>
    <div class="card">
      <div class="row">
        <span class="who">
          <span class="label">{who?.name}</span>
          <span class="detail">Signed in as {who?.username}</span>
        </span>
        <button type="button" class="sign-out" disabled={busy || left > 0} onclick={leave}
          >Sign out</button
        >
      </div>
    </div>
    {#if left > 0}
      <div class="warning">
        <p role="alert">
          {loseOnSignOutText(left)}{#if stillCant}<br />{STILL_CANT_REACH}{/if}
        </p>
        <Button disabled={busy} onclick={() => void sendNow()}
          >{busy ? 'Sending…' : 'Try sending now'}</Button
        >
        <div class="choices">
          <button type="button" class="stay" disabled={busy} onclick={stay}>Stay signed in</button>
          <button type="button" class="lose" disabled={busy} onclick={() => void signOutNow()}
            >Sign out and lose {left === 1 ? 'it' : 'them'}</button
          >
        </div>
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

  .choices {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .stay,
  .lose {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: none;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .stay {
    color: var(--color-text);
  }

  .lose {
    color: var(--color-warning-text);
    text-decoration: underline;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }
</style>
