<script lang="ts">
  // "Used in 5 recipes" in the ingredient editor (mockups Ingredients-Phone and
  // Ingredients-Desktop): the recipes that use the ingredient, A to Z, each a link to its page
  // (on a computer it opens in the reading pane). A long list is folded behind "+ 2 more" so an
  // ingredient used in thirty recipes doesn't take over the editor. With none, it says so calmly.
  import { resolve } from '$app/paths';
  import type { Ref } from '$lib/client/types';

  let {
    recipes,
    count,
    onfollow
  }: {
    /** The recipes, A to Z. */
    recipes: Ref[];
    /** How many recipes use it (the server's count; the list is the same recipes). */
    count: number;
    /** A recipe's link was followed with a plain click: the editor can get out of the way. */
    onfollow?: () => void;
  } = $props();

  const uid = $props.id();

  /** More recipes than this are folded behind "+ N more". */
  const SHOWN = 5;
  let all = $state(false);

  const shown = $derived(all ? recipes : recipes.slice(0, SHOWN));
  const folded = $derived(recipes.length - SHOWN);

  function follow(event: MouseEvent) {
    const plain =
      event.button === 0 && !(event.ctrlKey || event.metaKey || event.shiftKey || event.altKey);
    if (plain) onfollow?.();
  }
</script>

<section aria-labelledby="{uid}-heading">
  <h3 id="{uid}-heading">
    {count === 0 ? 'Used in recipes' : `Used in ${count} ${count === 1 ? 'recipe' : 'recipes'}`}
  </h3>
  {#if recipes.length}
    <ul>
      {#each shown as recipe (recipe.id)}
        <li class="chip">
          <a href={resolve('/(app)/recipes/[id]', { id: String(recipe.id) })} onclick={follow}
            >{recipe.name}</a
          >
        </li>
      {/each}
      {#if folded > 0}
        <li>
          <!-- One button for both ways, so keyboard focus stays on it. -->
          <button type="button" aria-expanded={all} onclick={() => (all = !all)}
            >{#if all}Show fewer{:else}+ {folded} more<span class="visually-hidden"
                >{folded === 1 ? ' recipe' : ' recipes'}</span
              >{/if}</button
          >
        </li>
      {/if}
    </ul>
  {:else}
    <p>Not in any recipe yet.</p>
  {/if}
</section>

<style>
  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  h3 {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  ul {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* The pill is as wide as the name; the link inside is 44 px high to tap. */
  .chip {
    display: flex;
    align-items: center;
    max-width: 100%;
    min-height: 32px;
    padding: 0 var(--space-6);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .chip a {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    margin: -6px 0;
    color: inherit;
    text-decoration: none;
    overflow-wrap: anywhere;
  }

  .chip a:hover {
    text-decoration: underline;
  }

  button {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  button[aria-expanded='true'] {
    color: var(--color-text-muted);
  }
</style>
