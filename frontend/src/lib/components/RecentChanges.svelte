<script lang="ts">
  // Pantry → Recent changes (spec, History and undo): the household's latest stock
  // changes, each with Undo while it's within the undo window. Anyone can undo anyone's
  // change. The verb comes first, in bold ("Used 200 g spinach").
  import type { Change } from '$lib/client/types';
  import type { PantryModel } from '$lib/pantry.svelte';
  import { session } from '$lib/session.svelte';

  let { changes, model }: { changes: Change[]; model: PantryModel } = $props();

  function split(summary: string): [string, string] {
    const space = summary.indexOf(' ');
    return space === -1 ? [summary, ''] : [summary.slice(0, space), summary.slice(space)];
  }
</script>

{#if changes.length}
  <ul class="changes">
    {#each changes as change (change.id)}
      {@const [verb, rest] = split(change.summary)}
      <li>
        <span class="what">
          <b>{verb}</b>{rest}
          {#if change.who.login_id !== session.me?.id}
            <span class="who">· {change.who.name}</span>
          {/if}
        </span>
        {#if change.can_undo && !change.undone}
          <button
            type="button"
            class="undo"
            aria-label="Undo: {change.summary}"
            onclick={() => void model.undo(change)}>Undo</button
          >
        {/if}
      </li>
    {/each}
  </ul>
{:else}
  <p class="none">Nothing yet. Changes to the pantry show here, with Undo.</p>
{/if}

<style>
  .changes {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    min-height: var(--touch-target);
    font-size: var(--text-md);
  }

  .who {
    color: var(--color-text-muted);
  }

  .undo {
    flex: none;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .none {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }
</style>
