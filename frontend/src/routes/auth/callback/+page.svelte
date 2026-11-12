<script lang="ts">
  // Where the sign-in server sends the browser back (0.9 O1). Outside (auth), whose layout
  // would send someone already signed in straight on: a setup test runs while signed in.
  // Posts what came back (state, and code or error) to the server, once, then:
  // - signed in: the same rules as a password sign-in. Another login than the one this phone
  //   holds starts clean, but never over changes still waiting here: then the new session is
  //   ended again and the sign-in page says whose changes are waiting.
  // - a setup test: the result, and the setup tab shows it too (it looks again on focus).
  // - refused: the server's sentence, and a way back.
  // The address bar loses the code at once, so it's never left in the history.
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { finishSignIn, type TestResult } from '#lib/client/sso.js';
  import Logo from '#lib/components/Logo.svelte';
  import { endSession } from '#lib/offline/signOut.js';
  import { signOutState } from '#lib/offline/unfinished.svelte.js';
  import { wipeIfAnotherLogin } from '#lib/offline/wipe.js';
  import { session } from '#lib/session.svelte.js';
  import {
    BACK_TO_SETUP,
    BACK_TO_SIGN_IN,
    SIGNING_IN,
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
  /** Where "Back" goes: the setup screen for a test. */
  let back = $state<'sign-in' | 'setup'>('sign-in');

  async function finish() {
    if (!flowState) {
      problem = ssoMessage('expired') ?? '';
      return;
    }
    try {
      const out = await finishSignIn(flowState, code, error);
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
    {#if tested}
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
