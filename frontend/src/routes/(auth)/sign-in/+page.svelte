<script lang="ts">
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { ApiError, signIn } from '$lib/api';
  import Button from '$lib/components/Button.svelte';
  import ConnectionNotice from '$lib/components/ConnectionNotice.svelte';
  import Switch from '$lib/components/Switch.svelte';
  import TextField from '$lib/components/TextField.svelte';
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

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    problem = '';
    busy = true;
    try {
      const me = await signIn(username, password, remember);
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
    <Button type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</Button>
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
