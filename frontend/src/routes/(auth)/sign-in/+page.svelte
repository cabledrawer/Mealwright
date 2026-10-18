<script lang="ts">
  // Changes still waiting on this phone (sync protocol 11.5, section 16 decision 4): the
  // same person signing back in sends them at once (the app does that on starting). Anyone
  // else is warned first, and never sends them; carrying on wipes the phone's copy, as
  // signing out does, and the next start makes a new device ID.
  import { tick, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { ApiError, signIn, signOut } from '$lib/api';
  import Button from '$lib/components/Button.svelte';
  import ConnectionNotice from '$lib/components/ConnectionNotice.svelte';
  import Switch from '$lib/components/Switch.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import {
    heldChanges,
    keptText,
    loseOthersText,
    sameUsername,
    waitingForText,
    type Held
  } from '$lib/offline/held';
  import { wipeDevice } from '$lib/offline/wipe';
  import { connection, safeNext, session } from '$lib/session.svelte';
  import { theme } from '$lib/theme.svelte';
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();

  let username = $state('');
  let password = $state('');
  let remember = $state(true);
  let busy = $state(false);
  let problem = $state('');

  const secure = $derived(connection(window.isSecureContext, data.setup.plain_http_allowed));
  const device = matchMedia('(max-width: 767px)').matches ? 'phone' : 'computer';

  /** Someone's changes waiting on this phone. */
  let held = $state<Held | null>(null);
  /** "Wren's 3 changes haven't been sent yet. If you carry on, they're lost." */
  let warning = $state(false);

  $effect(() => {
    void heldChanges().then((found) => (held = found));
  });

  const someoneElse = $derived(
    !!held && username.trim() !== '' && !sameUsername(username, held.who)
  );
  const heldText = $derived(
    !held ? '' : someoneElse ? waitingForText(held.who.name, held.count) : keptText(held.count)
  );

  // Typing another username takes the warning away until Sign in is pressed again.
  $effect(() => {
    void username;
    untrack(() => (warning = false));
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    problem = '';
    if (someoneElse) {
      warning = true;
      return;
    }
    await signInNow();
  }

  async function asThem() {
    if (!held) return;
    username = held.who.username;
    password = '';
    await tick();
    warning = false;
    document.getElementById('password')?.focus();
  }

  async function carryOn() {
    busy = true;
    await wipeDevice();
    held = null;
    warning = false;
    await signInNow();
  }

  async function signInNow() {
    busy = true;
    try {
      const me = await signIn(username, password, remember);
      if (held && me.id !== held.who.id) {
        // Another login after all: end that session again before anything is sent.
        await signOut().catch(() => undefined);
        warning = true;
        return;
      }
      session.me = me;
      theme.adopt(me.theme);
      const next = safeNext(page.url.searchParams.get('next'));
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- safeNext only returns pages of this app
      await goto(next, { replaceState: true, invalidateAll: true });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      problem = error.detail;
      password = '';
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>Sign in · Mealwright</title>
</svelte:head>

<div class="heading">
  <h1>Welcome back</h1>
  <p>Sign in to your household's kitchen</p>
</div>

<ConnectionNotice kind={secure} />

{#if held}
  <p class="held" role="status">{heldText}</p>
{/if}

{#if secure !== 'plain-refused'}
  <form onsubmit={submit} novalidate>
    <TextField id="username" label="Username" bind:value={username} autocomplete="username" />
    <TextField
      id="password"
      label="Password"
      type="password"
      bind:value={password}
      autocomplete="current-password"
    />
    <div class="remember">
      <span class="remember-text">
        <span id="remember-label" class="remember-label">Remember this {device}</span>
        <span id="remember-hint" class="remember-hint">Stay signed in for 30 days</span>
      </span>
      <Switch bind:checked={remember} labelledby="remember-label" describedby="remember-hint" />
    </div>
    {#if problem}
      <p class="problem" role="alert">{problem}</p>
    {/if}
    {#if warning && held}
      <div class="warning">
        <p role="alert">{loseOthersText(held.who.name, held.count)}</p>
        <Button disabled={busy} onclick={() => void asThem()}
          >Sign in as {held.who.name} instead</Button
        >
        <button type="button" class="lose" disabled={busy} onclick={() => void carryOn()}>
          Carry on and lose {held.count === 1 ? 'it' : 'them'}
        </button>
      </div>
    {:else}
      <Button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
    {/if}
  </form>

  <p class="forgot">Forgot your password? Ask your household's admin to reset it.</p>
{/if}

<style>
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    text-align: center;
  }

  h1 {
    font-size: 1.625rem;
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
  }

  .heading p,
  .forgot {
    color: var(--color-text-muted);
    font-size: var(--text-lg);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .remember {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-6);
    min-height: var(--touch-target);
  }

  .remember-text {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .remember-label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .remember-hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .held {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-offline);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
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
    border: none;
    background: none;
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  .forgot {
    font-size: var(--text-base);
    line-height: 1.5;
    text-align: center;
  }

  @media (min-width: 768px) {
    .heading {
      text-align: left;
    }
    h1 {
      font-size: 1.75rem;
    }
  }
</style>
