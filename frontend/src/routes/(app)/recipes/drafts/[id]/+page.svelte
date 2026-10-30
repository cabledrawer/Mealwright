<script lang="ts">
  // Carrying on with a draft (spec "Drafts (cabledrawer 21 Oct)"): the review as it was kept, with
  // every choice made so far, in the same screen as Import a recipe. Anyone in the household can
  // carry on. Leaving after changing something asks to save the draft over (ReviewScreen).
  // Online only: a draft is on the server.
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import { ApiError, cantReach } from '#lib/api.js';
  import { getDraft } from '#lib/client/drafts.js';
  import ReviewPage from '#lib/components/import/ReviewPage.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { ImportFlow } from '#lib/import.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { onMount } from 'svelte';

  const flow = new ImportFlow();
  let phone = $state(matchMedia('(max-width: 767px)').matches);
  /** Loading, ready, or why it can't be shown. */
  let phase = $state<'loading' | 'ready' | 'gone' | 'problem'>('loading');
  let problem = $state('');

  async function load() {
    phase = 'loading';
    try {
      flow.load(await getDraft(page.params.id ?? ''));
      phase = 'ready';
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        phase = 'gone';
        problem = error.detail;
      } else if (error instanceof ApiError && cantReach(error)) {
        phase = 'problem';
        problem = '';
      } else {
        phase = 'problem';
        problem = error instanceof ApiError ? error.detail : 'Couldn’t open that draft. Try again.';
      }
    }
  }

  onMount(() => void load());

  // Offline when it opened, back online now: fetch it again.
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      if (phase === 'problem') void load();
    }
  });

  $effect(() => {
    const media = matchMedia('(max-width: 767px)');
    const onchange = () => (phone = media.matches);
    media.addEventListener('change', onchange);
    return () => media.removeEventListener('change', onchange);
  });
</script>

{#if phase === 'ready' && flow.review}
  <ReviewPage {flow} {phone} parent={{ href: '/(app)/recipes/drafts', label: 'Drafts' }} />
{:else}
  <PageHeader title="Draft" parent={{ href: '/(app)/recipes/drafts', label: 'Drafts' }} />
  {#if phase === 'loading'}
    <p class="note" aria-busy="true">Loading…</p>
  {:else if phase === 'problem' && network.down}
    <OfflineNote screen="Drafts" />
  {:else if phase === 'gone'}
    <p class="note" role="alert">{problem}</p>
    <a class="back" href={resolve('/(app)/recipes/drafts')}>Back to Drafts</a>
  {:else}
    <div class="failed" role="alert">
      <p>{problem || 'Couldn’t reach your Mealwright server. Try again.'}</p>
      <button type="button" onclick={() => void load()}>Try again</button>
    </div>
  {/if}
{/if}

<style>
  .note,
  .failed p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .failed {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
  }

  .back,
  .failed button {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
    cursor: pointer;
  }

  .back {
    align-self: flex-start;
  }
</style>
