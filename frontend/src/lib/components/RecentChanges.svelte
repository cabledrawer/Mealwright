<script lang="ts">
  // Pantry → Recent changes (spec, History and undo): the household's latest stock
  // changes, each with Undo while it's within the undo window. Anyone can undo anyone's
  // change. The verb comes first, in bold ("Used 200 g spinach").
  import type { Change, ChangeLine } from '$lib/client/types';
  import type { PantryModel } from '$lib/pantry.svelte';
  import { session } from '$lib/session.svelte';

  let { changes, model }: { changes: Change[]; model: PantryModel } = $props();

  const SHOWN = 3;

  /** "Spinach: 200 g → 0 g · Fridge → Freezer", in plain words. */
  function lineWords(line: ChangeLine): string {
    const parts: string[] = [];
    if (line.before.display !== line.after.display) {
      parts.push(`${line.before.display} → ${line.after.display}`);
    }
    if (line.place_before && line.place_after && line.place_before.id !== line.place_after.id) {
      parts.push(`${line.place_before.name} → ${line.place_after.name}`);
    }
    if ((line.use_by_before ?? null) !== (line.use_by_after ?? null)) {
      parts.push(line.use_by_after ? `use by ${dayMonth(line.use_by_after)}` : 'no use-by date');
    }
    return `${line.food.name}: ${parts.join(' · ') || 'no change'}`;
  }

  function dayMonth(iso: string): string {
    return new Intl.DateTimeFormat('en-GB', {
      day: 'numeric',
      month: 'short',
      timeZone: 'UTC'
    }).format(new Date(`${iso}T12:00:00Z`));
  }

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
          <span
            ><b>{verb}</b>{rest}
            {#if change.who.login_id !== session.me?.id}
              <span class="who">· {change.who.name}</span>
            {/if}</span
          >
          {#if change.lines?.length}
            <span class="lines">
              {#each change.lines.slice(0, SHOWN) as line, i (i)}
                <span>{lineWords(line)}</span>
              {/each}
              {#if change.lines.length > SHOWN}
                <span>and {change.lines.length - SHOWN} more</span>
              {/if}
            </span>
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
