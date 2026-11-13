<script lang="ts">
  // A one-time sign-in link (0.9 A1, cabledrawer 12 Nov): an admin gives someone a login in
  // Settings → Household, and sends them this link. Here they choose their own password; the
  // link then stops working, and they sign in like anyone else (so the sign-in page's checks
  // for changes waiting on this device apply to them too). Works once, for 24 hours.
  // Link hardening (cabledrawer 13 Nov): the secret follows a `#` and is taken from the address
  // before anything else; nobody is named before the password is set, the username only after.
  import { resolve } from '$app/paths';
  import { ApiError, cantReach } from '#lib/api.js';
  import Button from '#lib/components/Button.svelte';
  import ConnectionNotice from '#lib/components/ConnectionNotice.svelte';
  import TextField from '#lib/components/TextField.svelte';
  import { getJoinLink, join, type JoinLink } from '#lib/client/people.js';
  import { cantReachWords } from '#lib/api.js';
  import { takeLinkSecret } from '#lib/linkSecret.js';
  import { connection } from '#lib/session.svelte.js';

  /** The server's words for a link that doesn't work (cabledrawer 12 Nov). */
  const GONE =
    'This sign-in link has been used or has run out. Ask your household’s admin for a new one.';

  let { plainHttpAllowed }: { plainHttpAllowed: boolean } = $props();

  // First of all: the secret out of the address bar.
  const token = takeLinkSecret();
  const secure = $derived(connection(window.isSecureContext, plainHttpAllowed));

  let link = $state<JoinLink | null>(null);
  /** Why the link can't be used: run out, used, or the server can't be reached. */
  let gone = $state('');
  let password = $state('');
  let problem = $state('');
  let busy = $state(false);
  /** The username, once the password is saved. */
  let username = $state('');

  async function look() {
    gone = '';
    try {
      if (!token) {
        gone = GONE; // an address without its secret: nothing to ask the server
        return;
      }
      link = await getJoinLink(token);
    } catch (error) {
      gone = cantReach(error)
        ? cantReachWords()
        : error instanceof ApiError
          ? error.detail
          : 'Something went wrong. Try again.';
    }
  }

  $effect(() => {
    void look();
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (busy || !link) return;
    problem = '';
    if (password.length < link.min_password) {
      problem = `Use at least ${link.min_password} characters.`;
      return;
    }
    busy = true;
    try {
      username = (await join(token, password)).username;
      password = '';
    } catch (error) {
      problem = cantReach(error)
        ? cantReachWords()
        : error instanceof ApiError
          ? error.detail
          : 'Something went wrong. Try again.';
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>Choose your password · Mealwright</title>
</svelte:head>

{#if username}
  <div class="heading">
    <h1>You’re all set</h1>
    <p>Your password is saved. Sign in as <strong>{username}</strong>.</p>
  </div>
  <a class="go" href={resolve('/(auth)/sign-in')}>Sign in</a>
{:else if link}
  <div class="heading">
    <h1>Welcome</h1>
    <p>Choose a password for your household’s kitchen.</p>
  </div>

  <ConnectionNotice kind={secure} />

  {#if secure !== 'plain-refused'}
    <form onsubmit={submit} novalidate>
      <TextField
        id="password"
        label="Password"
        type="password"
        bind:value={password}
        autocomplete="new-password"
        hint={`At least ${link.min_password} characters.`}
      />
      {#if problem}
        <p class="problem" role="alert">{problem}</p>
      {/if}
      <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save my password'}</Button>
    </form>
    <p class="note">This link works once. It stops working after you save your password.</p>
  {/if}
{:else if gone}
  <div class="heading">
    <h1>Sign-in link</h1>
  </div>
  <p class="problem" role="alert">{gone}</p>
  <Button quiet onclick={() => void look()}>Try again</Button>
{:else}
  <p class="loading" role="status">Loading…</p>
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

  .heading p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }



  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .note,
  .loading {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    text-align: center;
  }

  .go {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 54px;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    text-decoration: none;
  }
</style>
