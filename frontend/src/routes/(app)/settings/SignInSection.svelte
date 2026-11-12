<script lang="ts">
  // Settings → Sign-in, above Sign out (PR A2; the mockup Dark-SignInSettings09): your
  // password ("Change password", with when it last changed), where you're signed in (this
  // device tagged, every other one with its own Sign out) and "Sign out everywhere else".
  // Single sign-on and API tokens come later (O1, O2). Signing out another device has no
  // "Are you sure?": nothing is lost, it only has to sign in again.
  import { resolve } from '$app/paths';
  import { cantReach, cantReachWords, detailOf, ApiError } from '#lib/api.js';
  import Icon from '#lib/components/Icon.svelte';
  import {
    changedText,
    deviceName,
    getMySignIn,
    placeDetail,
    signOutDevice,
    signOutEverywhereElse,
    type MySignIn
  } from '#lib/mySignIn.js';
  import { network } from '#lib/network.svelte.js';

  let { device }: { device: 'phone' | 'computer' } = $props();

  let mine = $state<MySignIn | null>(null);
  let problem = $state('');
  /** Why the list couldn't be fetched: shown in its place, not read out (nothing was tapped). */
  let loadProblem = $state('');
  let busy = $state(false);
  /** Said after a sign-out here, for screen readers ("Signed out iPad · Safari."). */
  let said = $state('');

  const others = $derived(mine ? mine.sessions.filter((s) => !s.this_device) : []);

  $effect(() => {
    void network.backAgain;
    void load();
  });

  function why(error: unknown): string {
    if (cantReach(error)) return cantReachWords();
    if (error instanceof ApiError) return error.detail;
    return detailOf(null);
  }

  async function load() {
    try {
      mine = await getMySignIn();
      loadProblem = '';
    } catch (error) {
      loadProblem = why(error);
    }
  }

  async function run(job: () => Promise<MySignIn>, done: string) {
    if (busy) return;
    busy = true;
    problem = '';
    said = '';
    try {
      mine = await job();
      said = done;
    } catch (error) {
      problem = why(error);
      // An already-ended sign-in: show the list as it is now.
      if (error instanceof ApiError && error.status === 404) await load();
    } finally {
      busy = false;
    }
  }
</script>

<h3 class="sub-title">Your password</h3>
<div class="card">
  <a class="row to" href={resolve('/(app)/settings/password')}>
    <span class="who">
      <span class="label">Change password</span>
      {#if mine && changedText(mine)}<span class="detail">{changedText(mine)}</span>{/if}
    </span>
    <Icon name="back" size={18} stroke={2.4} />
  </a>
</div>

<h3 class="sub-title">Where you’re signed in</h3>
<div class="card" data-testid="signed-in-places">
  {#if mine === null}
    <p class="row detail">{loadProblem || 'Loading…'}</p>
  {:else}
    {#each mine.sessions as place (place.id)}
      <div class="row">
        <span class="who">
          <span class="label">{deviceName(place)}</span>
          <span class="detail">{placeDetail(place)}</span>
        </span>
        {#if place.this_device}
          <span class="tag">This {device}</span>
        {:else}
          <button
            type="button"
            class="small"
            aria-label="Sign out {deviceName(place)}"
            disabled={busy || network.offline}
            onclick={() =>
              void run(() => signOutDevice(place.id), `Signed out ${deviceName(place)}.`)}
            >Sign out</button
          >
        {/if}
      </div>
    {/each}
  {/if}
</div>
{#if problem}<p class="warning-line" role="alert">{problem}</p>{/if}
<p class="said" role="status">{said}</p>
{#if others.length > 0}
  <button
    type="button"
    class="everywhere"
    disabled={busy || network.offline}
    onclick={() => void run(signOutEverywhereElse, 'Signed out everywhere else.')}
    >Sign out everywhere else</button
  >
{/if}

<style>
  .sub-title {
    margin: var(--space-2) 0 0;
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
    margin: 0;
    padding: var(--space-4) 0;
  }

  .row + .row {
    border-top: 1px solid var(--color-border);
  }

  .who {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .to {
    color: inherit;
    text-decoration: none;
  }

  .to :global(svg) {
    flex: none;
    color: var(--color-text-muted);
    transform: scaleX(-1);
  }

  .tag {
    padding: var(--space-1) var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .small,
  .everywhere {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-button);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .everywhere {
    align-self: stretch;
  }

  .small:disabled,
  .everywhere:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .warning-line {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .said {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
