<script lang="ts">
  // The end of the ingredient editor: "Delete from Ingredients" (spec "Removing an ingredient",
  // cabledrawer 17 and 19 Oct). Recipes don't block it, so before it is pressed it says how many
  // recipes use the ingredient: their lines keep their words and show "not linked", and Undo
  // links them again. A recipe's own made-ahead ingredient can't be deleted while Made ahead is
  // on, and the editor says why, with the recipe's name as a link.
  import { resolve } from '$app/paths';
  import type { Ref } from '#lib/client/types.js';
  import { plural } from '#lib/words.js';
  import Button from '#lib/components/Button.svelte';

  let {
    usedIn,
    madeBy,
    removable,
    onremove,
    onfollow
  }: {
    /** How many recipes use the ingredient. */
    usedIn: number;
    /** The recipe whose own made-ahead ingredient this is, if any. */
    madeBy: Ref | null;
    /** False while some of it is in the pantry (or it is on a list): nothing is offered. */
    removable: boolean;
    onremove: () => void;
    /** The made-by recipe's link was followed with a plain click. */
    onfollow?: () => void;
  } = $props();

  const uid = $props.id();

  function follow(event: MouseEvent) {
    const plain =
      event.button === 0 && !(event.ctrlKey || event.metaKey || event.shiftKey || event.altKey);
    if (plain) onfollow?.();
  }
</script>

{#if madeBy}
  <p>
    Made by the recipe <a
      href={resolve('/(app)/recipes/[id]', { id: String(madeBy.id) })}
      onclick={follow}>{madeBy.name}</a
    >. Turn off Made ahead there to delete it.
  </p>
{:else if removable}
  <div class="area">
    {#if usedIn > 0}
      <p id="{uid}-hint">
        Used in {usedIn}
        {plural(usedIn, 'recipe', 'recipes')}. {usedIn === 1
          ? 'Its line keeps its words and shows'
          : 'Their lines keep their words and show'} “not linked”.
      </p>
    {/if}
    <Button small quiet aria-describedby={usedIn > 0 ? `${uid}-hint` : undefined} onclick={onremove}
      >Delete from Ingredients</Button
    >
  </div>
{/if}

<style>
  .area {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  a {
    color: var(--color-accent);
    font-weight: var(--weight-bold);
    text-decoration: underline;
  }
</style>
