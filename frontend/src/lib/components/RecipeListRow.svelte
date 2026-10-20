<script lang="ts">
  // One recipe in the All recipes list (mockups Recipes-Phone, Dark-Recipes-Phone): a
  // square, the name, and a quiet line "50 min · 320 kcal · all in stock but 1". The square
  // is plain and warm until the photo goes in (0.4, PR 2). The row is not a link yet: the
  // recipe page (PR 3b) makes it one.
  import type { RecipeRow } from '$lib/client/recipes';
  import { recipeParts } from '$lib/recipeLine';

  let { recipe }: { recipe: RecipeRow } = $props();
  /** Between the parts; a normal space each side, so a long line wraps there. */
  const SEP = ' · ';
  const parts = $derived(recipeParts(recipe));
</script>

<div class="recipe">
  <span class="square" aria-hidden="true"></span>
  <span class="text">
    <span class="name">{recipe.name}</span>
    <span class="line"
      >{#each parts as part, i (i)}{#if i > 0}{SEP}{/if}<span class:soon={part.soon}
          >{part.text}</span
        >{/each}</span
    >
  </span>
</div>

<style>
  .recipe {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 72px;
    padding: var(--space-4) 0;
  }

  .square {
    flex: none;
    width: 52px;
    height: 52px;
    border-radius: var(--radius-md);
    background: var(--color-recipe-square);
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  .name {
    font-size: 1rem;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .line {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    overflow-wrap: anywhere;
  }

  .soon {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-semibold);
  }
</style>
