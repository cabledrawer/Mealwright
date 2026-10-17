<script lang="ts">
  // First run: the first person creates the admin account (Onboarding step 1). There
  // is no default admin and no default password (spec section 7). The rest of
  // onboarding (Amounts, Household, Shops) comes in 0.8.
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { ApiError, createAdmin } from '$lib/api';
  import Button from '$lib/components/Button.svelte';
  import ConnectionNotice from '$lib/components/ConnectionNotice.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import { connection, session } from '$lib/session.svelte';
  import { theme } from '$lib/theme.svelte';
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();

  // Same rules as the server (backend: account.py).
  const MIN_PASSWORD = 10;
  const USERNAME = /^[a-z0-9][a-z0-9._-]{0,49}$/;

  let name = $state('');
  let username = $state('');
  let password = $state('');
  let checked = $state(false);
  let busy = $state(false);
  let problem = $state('');

  const secure = $derived(connection(window.isSecureContext, data.setup.plain_http_allowed));

  const errors = $derived({
    name: name.trim() ? undefined : 'Please enter your name.',
    username: USERNAME.test(username.trim().toLowerCase())
      ? undefined
      : username.trim()
        ? 'Use up to 50 lowercase letters, numbers, dots, dashes or underscores.'
        : 'Please choose a username.',
    password:
      password.length >= MIN_PASSWORD ? undefined : `Use at least ${MIN_PASSWORD} characters.`
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    checked = true;
    problem = '';
    if (errors.name || errors.username || errors.password) {
      const first = errors.name ? 'name' : errors.username ? 'username' : 'password';
      document.getElementById(first)?.focus();
      return;
    }
    busy = true;
    try {
      const me = await createAdmin(name.trim(), username.trim().toLowerCase(), password);
      session.me = me;
      theme.adopt(me.theme);
      await goto(resolve('/'), { replaceState: true, invalidateAll: true });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      problem = error.detail;
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>Set up Mealwright</title>
</svelte:head>

<div class="heading">
  <h1>Welcome! First, your account</h1>
  <p>
    You're the first person here, so you'll be the admin. You'll be able to add the rest of the
    household later.
  </p>
</div>

<ConnectionNotice kind={secure} />

{#if secure !== 'plain-refused'}
  <form onsubmit={submit} novalidate>
    <TextField
      id="name"
      label="Your name"
      bind:value={name}
      autocomplete="name"
      error={checked ? errors.name : undefined}
    />
    <TextField
      id="username"
      label="Username"
      bind:value={username}
      autocomplete="username"
      error={checked ? errors.username : undefined}
    />
    <TextField
      id="password"
      label="Password"
      type="password"
      bind:value={password}
      autocomplete="new-password"
      hint="At least 10 characters · stored scrambled, never as plain text"
      error={checked ? errors.password : undefined}
    />
    <p class="note">
      <svg
        aria-hidden="true"
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.2"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" />
        <path d="M9 12l2 2 4-4" />
      </svg>
      <span>No default password and no account with us. This login lives only on your server.</span>
    </p>
    {#if problem}
      <p class="problem" role="alert">{problem}</p>
    {/if}
    <Button type="submit" disabled={busy}
      >{busy ? 'Creating your account…' : 'Create account'}</Button
    >
  </form>
{/if}

<style>
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  h1 {
    font-size: 1.75rem;
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
    line-height: 1.15;
  }

  .heading p {
    color: var(--color-text-muted);
    font-size: var(--text-lg);
    line-height: 1.45;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .note {
    display: flex;
    gap: var(--space-5);
    padding: var(--space-6) 14px;
    border-radius: var(--radius-button);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .note svg {
    margin-top: 1px;
  }

  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }
</style>
