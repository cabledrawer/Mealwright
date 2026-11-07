<script lang="ts">
  // Settings → Recent changes (F172, cabledrawer 7 Nov): the only place with every kind of change
  // and its Undo (Ingredients and Pantry have no list of their own now). The toast still offers
  // Undo straight after each change.
  import { cantReachWords } from '#lib/api.js';
  import { AllChanges } from '#lib/allChanges.svelte.js';
  import RecentChanges from '#lib/components/RecentChanges.svelte';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';

  const recent = new AllChanges();

  // Fetch again after a change here or elsewhere, when stock moved, and when the connection
  // comes back.
  $effect(() => {
    void kitchen.version;
    void live.pantry;
    void network.backAgain;
    void recent.load();
  });
</script>

<div class="card">
  {#if recent.problem && !recent.changes.length}
    <p class="problem" role="status">
      {recent.problem}
      {#if recent.problem !== cantReachWords()}
        <button type="button" class="link" onclick={() => void recent.load()}>Try again</button>
      {/if}
    </p>
  {:else}
    <RecentChanges
      changes={recent.changes}
      onundo={(change) => void recent.undo(change)}
      verbFirst={false}
      none={recent.loaded ? 'Nothing yet. Changes show here, with Undo for 7 days.' : 'Loading…'}
    />
  {/if}
  {#if recent.next !== null}
    <button
      type="button"
      class="more"
      disabled={recent.loadingMore || network.offline}
      onclick={() => void recent.more()}>{recent.loadingMore ? 'Loading…' : 'Show more'}</button
    >
  {/if}
  {#if recent.moreProblem}<p class="problem" role="alert">{recent.moreProblem}</p>{/if}
</div>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .more {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .more:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .problem {
    margin: 0;
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-weight: var(--weight-semibold);
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: inherit;
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }
</style>
