<script lang="ts">
  import Loading from '#lib/components/Loading.svelte';
  // A one-time sign-in link (0.9 A1, cabledrawer 12 Nov): an admin gives someone a login in
  // Settings › People, and sends them this link. Here they choose their own password; the
  // link then stops working, and they are signed in on this device straight away (F254,
  // cabledrawer 20 Nov). The sign-in page's checks for changes waiting on this device still
  // apply: when another login's changes wait here, this session ends again and they sign in on
  // the sign-in page, which warns them. Works once, for 24 hours.
  // Link hardening (cabledrawer 13 Nov): the secret follows a `#` and is taken from the address
  // before anything else; nobody is named before the password is set, the username only after.
  // A Reset password link ("/reset#<secret>", Pe1) is the same page: the server says which kind.
  // Opened where someone is already signed in (Pe2, cabledrawer 13 Nov), it simply refuses: no
  // names, no sign-out, and the link stays unused (the server refuses too).
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { ApiError, cantReach, SOMETHING_WENT_WRONG, type Me } from '#lib/api.js';
  import Button from '#lib/components/Button.svelte';
  import ConnectionNotice from '#lib/components/ConnectionNotice.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import TextField from '#lib/components/TextField.svelte';
  import { getJoinLink, join, type JoinLink } from '#lib/client/people.js';
  import { cantReachWords } from '#lib/api.js';
  import { takeLinkSecret } from '#lib/linkSecret.js';
  import { turnAway } from '#lib/offline/held.js';
  import { endSession } from '#lib/offline/signOut.js';
  import { signOutState } from '#lib/offline/unfinished.svelte.js';
  import { wipeIfAnotherLogin } from '#lib/offline/wipe.js';
  import { connection, session } from '#lib/session.svelte.js';
  import { theme } from '#lib/theme.svelte.js';

  let {
    plainHttpAllowed,
    signedIn,
    kind = 'join'
  }: {
    plainHttpAllowed: boolean;
    signedIn: boolean;
    /** Which address it was opened at: "/join" or "/reset" (Pe1). */
    kind?: 'join' | 'reset';
  } = $props();

  /** The heading where the link can't be used: the address says which kind (proposed). */
  const linkName = $derived(kind === 'reset' ? 'Reset password link' : 'Sign-in link');
  /** A reset link used or run out: the server's words (cabledrawer 12 Nov), said of a reset link
   * (16b review R-L2; proposed, for cabledrawer). */
  const RESET_GONE =
    'This reset link has been used or has run out. Ask your household’s admin for a new one.';
  /**
   * The address has no secret: the page was reloaded, or a tab restored, after the secret was
   * taken out of the address bar. Nothing is known about the link, so the page says only what
   * is true (16b review R-L2; proposed, for cabledrawer).
   */
  const NO_SECRET = 'Open the link again from the message it came in.';

  // First of all: the secret out of the address bar.
  const token = takeLinkSecret();
  const secure = $derived(connection(window.isSecureContext, plainHttpAllowed));

  let link = $state<JoinLink | null>(null);
  /** Why the link can't be used: run out, used, or the server can't be reached. */
  let gone = $state('');
  /** The address had no secret (reloaded, or a tab restored). */
  const noSecret = !token;
  let password = $state('');
  let problem = $state('');
  let busy = $state(false);
  /** The username, once the password is saved. */
  let username = $state('');
  /** The server found someone signed in on this device after all. */
  let refusedThere = $state(false);
  const refused = $derived(signedIn || refusedThere);
  const reset = $derived(link?.kind === 'reset');

  /** Someone is signed in here: the page refuses, and the link stays unused (Pe2). */
  function signedInHere(error: unknown): boolean {
    if (error instanceof ApiError && error.code === 'signed_in_here') refusedThere = true;
    return refusedThere;
  }

  async function look() {
    gone = '';
    if (refused) return; // nothing is asked: the link stays as it is
    try {
      if (!token) return; // an address without its secret: nothing to ask the server
      link = await getJoinLink(token);
    } catch (error) {
      if (signedInHere(error)) return;
      gone = cantReach(error)
        ? cantReachWords()
        : error instanceof ApiError
          ? error.code === 'link_gone' && kind === 'reset'
            ? RESET_GONE
            : error.detail
          : SOMETHING_WENT_WRONG;
    }
  }

  $effect(() => {
    void look();
  });

  /**
   * The link signed them in (F254): into the app, as the sign-in page does, unless another
   * login's changes wait on this device or it couldn't check. Then the session ends again and
   * the sign-in page, named for them, gives its warning. True once they are in the app.
   */
  async function signedInNow(me: Me, name: string): Promise<boolean> {
    const result = await wipeIfAnotherLogin(me, null);
    if (result !== 'kept' && result !== 'wiped') {
      await endSession();
      turnAway(name);
      return false;
    }
    signOutState.unfinished = false;
    session.me = me;
    theme.adopt(me.theme, undefined, me.id);
    await goto(resolve('/(app)'), { replace: true, refreshAll: true });
    return true;
  }

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
      const joined = await join(token, password);
      password = '';
      if (joined.me && (await signedInNow(joined.me, joined.username))) return;
      username = joined.username;
    } catch (error) {
      if (signedInHere(error)) return;
      problem = cantReach(error)
        ? cantReachWords()
        : error instanceof ApiError
          ? error.detail
          : SOMETHING_WENT_WRONG;
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>Choose your password · Mealwright</title>
</svelte:head>

{#if refused}
  <!-- words.md section 81, word for word (cabledrawer 13 Nov). -->
  <div class="heading">
    <h1>This link can’t be used here</h1>
    <p>
      Someone is already signed in on this device. Sign-in links only work where nobody is signed
      in.
    </p>
  </div>
  <p class="info">
    <Icon name="info" size={18} />
    <span>
      The link hasn’t been used. Open it on another device, or sign out here first and then open it
      again.
    </span>
  </p>
  <a class="go" href={resolve('/(app)')}>Go to Today</a>
{:else if username}
  <div class="heading">
    <h1>You’re all set</h1>
    <p>Your password is saved. Sign in as <strong>{username}</strong>.</p>
  </div>
  <a class="go" href={resolve('/(auth)/sign-in')}>Sign in</a>
{:else if link}
  <div class="heading">
    {#if reset}
      <!-- proposed, for cabledrawer -->
      <h1>Choose a new password</h1>
      <p>Your recipes, plans and history stay as they are.</p>
    {:else}
      <h1>Welcome</h1>
      <p>Choose a password for your household’s kitchen.</p>
    {/if}
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
{:else if noSecret}
  <div class="heading">
    <h1>{linkName}</h1>
  </div>
  <p class="info">
    <Icon name="info" size={18} />
    <span>{NO_SECRET}</span>
  </p>
{:else if gone}
  <div class="heading">
    <h1>{linkName}</h1>
  </div>
  <p class="problem" role="alert">{gone}</p>
  <Button quiet onclick={() => void look()}>Try again</Button>
{:else}
  <Loading />
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

  /* The mockup's info box (Dark-LinkSignedIn095-Phone). */
  .info {
    display: flex;
    gap: 10px;
    padding: var(--space-5) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-info);
    color: var(--color-info-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .info :global(svg) {
    flex: none;
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
