<script lang="ts">
  // Where the sign-in server sends the browser back (0.9 O1). Outside (auth), whose layout
  // would send someone already signed in straight on: a setup test runs while signed in.
  // Posts what came back (state, and code or error) to the server, once, then:
  // - signed in: the same rules as a password sign-in. Another login than the one this phone
  //   holds starts clean, but never over changes still waiting here: then the new session is
  //   ended again and the sign-in page says whose changes are waiting.
  // - a setup test: the result, and the setup tab shows it too (it looks again on focus).
  // - waiting (0.9.5 Pe3/M2): the sign-in matched nobody here and waits, with no session, until
  //   an admin says who it is: "Almost there" (mockup Dark-SsoWaiting095-Phone).
  // - confirmed (D3): an admin who signs in only with single sign-on confirmed Delete
  //   everything with a fresh sign-in; back to that page, which now asks for the words only.
  // - refused: the server's sentence, and a way back (to Delete everything, when that is where
  //   this tab came from).
  // "Sign out" on "Almost there" (S7) tells the server, so the next "Sign in with …" on this
  // browser asks the sign-in server to ask who it is.
  // - again: the sign-in server refused the sign-in for one thing Mealwright asked for and
  //   can do without; the server has begun a second try, and the browser goes there.
  // The address bar loses the code at once, so it's never left in the history.
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { ApiError, cantReach, cantReachWords, signOut } from '#lib/api.js';
  import {
    finishSignIn,
    goToSignInServer,
    markConfirming,
    startAddress,
    wasConfirming,
    type TestResult
  } from '#lib/client/sso.js';
  import Logo from '#lib/components/Logo.svelte';
  import { endSession } from '#lib/offline/signOut.js';
  import { signOutState } from '#lib/offline/unfinished.svelte.js';
  import { wipeIfAnotherLogin } from '#lib/offline/wipe.js';
  import { session } from '#lib/session.svelte.js';
  import {
    ALMOST_THERE,
    BACK_TO_DELETE,
    BACK_TO_SETUP,
    BACK_TO_SIGN_IN,
    SIGN_IN_AGAIN,
    SIGN_OUT,
    SIGNING_IN,
    WAITING_AFTER,
    WAITING_BEFORE,
    WAITING_NOTE,
    TEST_TAB_DONE,
    ssoMessage,
    testPassedText
  } from '#lib/ssoWords.js';
  import { theme } from '#lib/theme.svelte.js';

  const params = page.url.searchParams;
  const flowState = params.get('state') ?? '';
  const code = params.get('code');
  const error = params.get('error');
  history.replaceState(history.state, '', page.url.pathname);

  let problem = $state('');
  let tested = $state<TestResult | null>(null);
  /** "Almost there": the username at the sign-in server that waits for an admin. */
  let waitingAs = $state<string | null>(null);
  /** Where "Back" goes: the setup screen for a test, Delete everything for its confirming. */
  let back = $state<'sign-in' | 'setup' | 'delete'>(wasConfirming() ? 'delete' : 'sign-in');
  let signingOut = $state(false);

  async function signOutWaiting() {
    signingOut = true;
    try {
      await signOut();
    } catch {
      // Not reached: there is no sign-in here to end, so go on; only the next sign-in's
      // "ask who it is" is lost.
    }
    await goto(resolve('/(auth)/sign-in'), { replace: true });
  }

  async function finish() {
    if (!flowState) {
      problem = ssoMessage('expired') ?? '';
      return;
    }
    try {
      const out = await finishSignIn(flowState, code, error);
      if (out.done === 'again' && out.url) {
        goToSignInServer(out.url);
        return;
      }
      if (out.done === 'waiting') {
        waitingAs = out.username ?? '';
        return;
      }
      if (out.done === 'confirmed') {
        markConfirming(false);
        await goto(resolve('/(app)/settings/your-data/delete'), { replace: true });
        return;
      }
      if (out.done === 'tested') {
        back = 'setup';
        tested = out.test;
        return;
      }
      const me = out.me;
      if (!me) return;
      const kept = await wipeIfAnotherLogin(me, null);
      if (kept !== 'kept' && kept !== 'wiped') {
        // Someone's changes are waiting here, or the phone couldn't check: not this way.
        await endSession();
        await goto(resolve('/(auth)/sign-in'), { replace: true });
        return;
      }
      signOutState.unfinished = false;
      session.me = me;
      theme.adopt(me.theme, undefined, me.id);
      await goto(resolve('/(app)'), { replace: true, refreshAll: true });
    } catch (failure) {
      if (!(failure instanceof ApiError)) throw failure;
      problem = cantReach(failure) ? cantReachWords() : failure.detail;
    }
  }

  void finish();
</script>

<svelte:head>
  <title>Single sign-on · Mealwright</title>
</svelte:head>

<div class="page">
  <Logo size={56} />
  <main class="card">
    {#if waitingAs !== null}
      <h1 class="title">{ALMOST_THERE}</h1>
      <p class="lead">{WAITING_BEFORE} <strong>{waitingAs}</strong>{WAITING_AFTER}</p>
      <p class="info" role="status">{WAITING_NOTE}</p>
      <div class="buttons">
        <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- an API address, not a page -->
        <a class="primary" href={startAddress(false)} data-sveltekit-reload>{SIGN_IN_AGAIN}</a>
        <button
          class="secondary"
          type="button"
          disabled={signingOut}
          onclick={() => void signOutWaiting()}>{SIGN_OUT}</button
        >
      </div>
    {:else if tested}
      {#if tested.passed}
        <p class="ok" role="status">
          {testPassedText(tested.username, tested.groups, tested.role)}
        </p>
      {:else}
        <p class="problem" role="alert">{tested.message ?? ssoMessage(tested.code)}</p>
      {/if}
      <p class="note">{TEST_TAB_DONE}</p>
      <a class="back" href={resolve('/(app)/settings/sso')}>{BACK_TO_SETUP}</a>
    {:else if problem}
      <p class="problem" role="alert">{problem}</p>
      {#if back === 'setup'}
        <a class="back" href={resolve('/(app)/settings/sso')}>{BACK_TO_SETUP}</a>
      {:else if back === 'delete'}
        <a class="back" href={resolve('/(app)/settings/your-data/delete')}>{BACK_TO_DELETE}</a>
      {:else}
        <a class="back" href={resolve('/(auth)/sign-in')}>{BACK_TO_SIGN_IN}</a>
      {/if}
    {:else}
      <p class="wait" role="status">{SIGNING_IN}</p>
    {/if}
  </main>
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 22px;
    min-height: 100dvh;
    padding: max(48px, env(safe-area-inset-top)) var(--space-9)
      max(var(--space-9), env(safe-area-inset-bottom));
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 18px;
    width: 100%;
    max-width: 440px;
  }

  .title {
    margin: 0;
    font-size: 26px;
    font-weight: var(--weight-extrabold);
    letter-spacing: -0.02em;
    line-height: 1.25;
  }

  .lead {
    color: var(--color-text-soft);
    font-size: 1rem;
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .lead strong {
    color: var(--color-text);
  }

  .info {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    line-height: 1.45;
  }

  .buttons {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .primary,
  .secondary {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 48px;
    border-radius: 14px;
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .primary {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .secondary {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  button.secondary {
    font-family: var(--font-ui);
    cursor: pointer;
  }

  button.secondary:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .wait,
  .note {
    color: var(--color-text-muted);
    font-size: var(--text-lg);
    text-align: center;
  }

  .note {
    font-size: var(--text-base);
  }

  .problem,
  .ok {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .problem {
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .ok {
    background: var(--color-success-soft, var(--color-surface));
    color: var(--color-text);
  }

  .back {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: var(--touch-target);
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }
</style>
