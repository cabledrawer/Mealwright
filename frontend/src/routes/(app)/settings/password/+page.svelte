<script lang="ts">
  // Settings → Sign-in → Change password (PR A2; the mockup Dark-ChangePassword09). Needs the
  // current password. New passwords need 12 characters (cabledrawer 11 Nov); passwords people
  // already have keep working (19 Oct). "Sign out my other devices" is on to start with
  // (proposed, for cabledrawer), and is only shown while there are other devices.
  import { ApiError, cantReach, cantReachWords, detailOf } from '#lib/api.js';
  import Button from '#lib/components/Button.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import TextField from '#lib/components/TextField.svelte';
  import {
    MIN_PASSWORD,
    changePassword,
    getMySignIn,
    lengthHint,
    othersText,
    type MySignIn
  } from '#lib/mySignIn.js';
  import { network } from '#lib/network.svelte.js';

  let mine = $state<MySignIn | null>(null);
  let current = $state('');
  let next = $state('');
  let again = $state('');
  let signOutOthers = $state(true);
  let busy = $state(false);
  let checked = $state(false);
  let problem = $state('');
  /** The wrong-password pause (the server's words, with the note under them). */
  let paused = $state(false);
  let done = $state('');

  const others = $derived(mine ? othersText(mine) : '');
  const errors = $derived({
    current: current ? undefined : 'Type your current password.',
    next: [...next].length >= MIN_PASSWORD ? undefined : `Use at least ${MIN_PASSWORD} characters.`,
    again: again === next ? undefined : 'The two new passwords aren’t the same.'
  });
  const ready = $derived(!errors.current && !errors.next && !errors.again);

  $effect(() => {
    void network.backAgain;
    void getMySignIn()
      .then((found) => (mine = found))
      .catch(() => undefined); // the list is only for the switch's line; the form still works
  });

  function submit(event: SubmitEvent) {
    event.preventDefault();
    void save();
  }

  async function save() {
    if (busy) return;
    checked = true;
    problem = '';
    paused = false;
    done = '';
    if (!ready) return;
    busy = true;
    try {
      const signingOut = !!others && signOutOthers;
      mine = await changePassword(current, next, signingOut);
      current = '';
      next = '';
      again = '';
      checked = false;
      done = signingOut
        ? 'Password changed. Your other devices are signed out.'
        : 'Password changed.';
    } catch (error) {
      if (cantReach(error)) problem = cantReachWords();
      else if (error instanceof ApiError) {
        problem = error.detail;
        paused = error.code === 'username_paused';
      } else problem = detailOf(null);
      current = '';
    } finally {
      busy = false;
    }
  }
</script>

<PageHeader title="Change password" parent={{ href: '/(app)/settings', label: 'Sign-in' }} />

<form class="page" onsubmit={submit} novalidate>
  <div class="card">
    <TextField
      id="current-password"
      label="Current password"
      type="password"
      bind:value={current}
      autocomplete="current-password"
      error={checked ? errors.current : undefined}
    />
    <TextField
      id="new-password"
      label="New password"
      type="password"
      bind:value={next}
      autocomplete="new-password"
      hint={lengthHint(next)}
      error={checked ? errors.next : undefined}
    />
    <TextField
      id="new-password-again"
      label="New password again"
      type="password"
      bind:value={again}
      autocomplete="new-password"
      error={checked ? errors.again : undefined}
    />
    {#if others}
      <div class="switch-row">
        <span class="who">
          <span class="label" id="others-label">Sign out my other devices</span>
          <span class="detail" id="others-detail">{others}</span>
        </span>
        <Switch
          bind:checked={signOutOthers}
          labelledby="others-label"
          describedby="others-detail"
        />
      </div>
    {/if}
  </div>
  {#if problem}
    <p class="problem" role="alert">{problem}</p>
    {#if paused}
      <p class="note">
        Only one wrong-password pause per username, never longer than a minute. Other people can
        still sign in.
      </p>
    {/if}
  {/if}
  <p class="done" role="status">{done}</p>
  <Button type="submit" disabled={busy || network.offline}
    >{busy ? 'Changing…' : 'Change password'}</Button
  >
  <p class="note">
    New passwords need at least {MIN_PASSWORD} characters. Passwords you already have keep working.
  </p>
  <p class="note">
    Forgot it? Ask an admin in your household. The only admin? Run <code>reset-admin</code> on the server
    (see the docs).
  </p>
</form>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 560px;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: var(--touch-target);
  }

  .who {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .detail,
  .note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .note {
    margin: 0 var(--space-2);
  }

  code {
    font-family: var(--font-mono, monospace);
  }

  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .done {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .done:empty {
    display: none;
  }
</style>
