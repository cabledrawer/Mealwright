<script lang="ts">
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { ApiError, signOut } from '$lib/api';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import ThemeSwitch from '$lib/components/ThemeSwitch.svelte';
  import { session } from '$lib/session.svelte';

  let busy = $state(false);
  let problem = $state('');

  // Settings → Sign out returns to Sign in (spec). The warning about changes not yet
  // sent comes with the offline shopping list in 0.3.
  async function leave() {
    busy = true;
    problem = '';
    try {
      await signOut();
      session.me = null;
      await goto(resolve('/sign-in'), { replaceState: true, invalidateAll: true });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      problem = error.detail;
    } finally {
      busy = false;
    }
  }
</script>

<PageHeader title="Settings" />

<div class="sections">
  <section class="section" aria-labelledby="appearance">
    <h2 id="appearance">Appearance</h2>
    <div class="card">
      <div class="row">
        <span class="label">Theme</span>
        <ThemeSwitch variant="pill" />
      </div>
    </div>
  </section>

  <section class="section" aria-labelledby="sign-in">
    <h2 id="sign-in">Sign-in</h2>
    <div class="card">
      <div class="row">
        <span class="who">
          <span class="label">{session.me?.name}</span>
          <span class="detail">Signed in as {session.me?.username}</span>
        </span>
        <button type="button" class="sign-out" disabled={busy} onclick={leave}>Sign out</button>
      </div>
    </div>
    {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
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

  .problem {
    padding: 0 var(--space-3);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }
</style>
