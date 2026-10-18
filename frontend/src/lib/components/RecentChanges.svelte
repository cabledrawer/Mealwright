<script lang="ts">
  // Recent changes (spec, History and undo), on Pantry (stock) and Ingredients: the household's latest
  // changes, each with what it did per ingredient (the server's totals) and Undo while
  // it's within the undo window. Anyone can undo anyone's
  // change. The verb comes first, in bold ("Used 200 g spinach").
  import { totalWords } from '$lib/changeTotals';
  import type { Change } from '$lib/client/types';
  import { session } from '$lib/session.svelte';

  let {
    changes,
    onundo,
    none = 'Nothing yet. Changes to the pantry show here, with Undo.',
    verbFirst = true
  }: {
    changes: Change[];
    onundo: (change: Change) => void;
    /** What to say when there are no changes. */
    none?: string;
    /** Summaries start with the verb ("Used 200 g spinach"), so it goes in bold. Where some
     * start with the ingredient ("Toor dal is now a staple"), only the kinds of change whose
     * summary always starts with a verb do (decided by the kind, never by the words, so an
     * ingredient called "Added sugar" is never half bold). */
    verbFirst?: boolean;
  } = $props();

  /** Ingredient changes whose summary starts with a verb: Added X, Removed X from
   * Ingredients, Merged X into Y, Made X its own ingredient again, Undid: … */
  const VERB_KINDS = new Set(['food_created', 'food_removed', 'merged', 'split', 'undo']);

  const SHOWN = 3;

  function split(change: Change): [string, string] {
    const summary = change.summary;
    const space = summary.indexOf(' ');
    if (!verbFirst && !VERB_KINDS.has(change.kind)) return ['', summary];
    return space === -1 ? [summary, ''] : [summary.slice(0, space), summary.slice(space)];
  }
</script>

{#if changes.length}
  <ul class="changes">
    {#each changes as change (change.id)}
      {@const [verb, rest] = split(change)}
      <li>
        <span class="what">
          <span
            >{#if verb}<b>{verb}</b>{/if}{rest}
            {#if change.who.login_id !== session.me?.id}
              <span class="who">· {change.who.name}</span>
            {/if}</span
          >
          {#if change.totals?.length}
            {@const words = change.totals.map(totalWords)}
            <span class="lines">
              {#each words.slice(0, SHOWN) as text, i (i)}
                <span>{text}</span>
              {/each}
              {#if words.length > SHOWN}
                <span>and {words.length - SHOWN} more</span>
              {/if}
            </span>
          {/if}
        </span>
        {#if change.can_undo && !change.undone}
          <button
            type="button"
            class="undo"
            aria-label="Undo: {change.summary}"
            onclick={() => onundo(change)}>Undo</button
          >
        {/if}
      </li>
    {/each}
  </ul>
{:else}
  <p class="none">{none}</p>
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

  .what {
    display: flex;
    min-width: 0;
    flex-direction: column;
    padding: var(--space-2) 0;
  }

  .lines {
    display: flex;
    flex-direction: column;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
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
