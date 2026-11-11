<script lang="ts">
  // Bottom tabs on phones: the five pages, always in reach of a thumb.
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { PAGES, appRoute, isBatchCook, isCurrent } from '#lib/nav.js';
  import { FROM_PANTRY, isPantryIngredients, pantrySide } from '#lib/pantrySide.svelte.js';
  import Icon from './Icon.svelte';
</script>

<!-- The Pantry tab opens whichever of Pantry · Ingredients was chosen last (N1); Ingredients
     reached that way (?from=pantry) is the Pantry tab's, not Recipes'. -->
<nav class="tabbar" aria-label="Main">
  {#each PAGES as item (item.href)}
    {@const viaPantry = isPantryIngredients(page.url.pathname, page.url.search)}
    {@const current =
      item.href === '/pantry'
        ? viaPantry || isCurrent(item, page.url.pathname)
        : item.href === '/recipes'
          ? !viaPantry && isCurrent(item, page.url.pathname)
          : item.href === '/plan'
            ? isCurrent(item, page.url.pathname) || isBatchCook(page.url.pathname)
            : isCurrent(item, page.url.pathname)}
    {#if item.href === '/pantry' && pantrySide.value === 'ingredients'}
      <a
        href="{resolve('/(app)/recipes/ingredients')}?{FROM_PANTRY}"
        aria-current={current ? 'page' : undefined}
      >
        {@render tab(item)}
      </a>
    {:else}
      <a href={resolve(appRoute(item.href))} aria-current={current ? 'page' : undefined}>
        {@render tab(item)}
      </a>
    {/if}
  {/each}
</nav>

{#snippet tab(item: (typeof PAGES)[number])}
  <Icon name={item.icon} />
  <span>{item.tabLabel}</span>
{/snippet}

<style>
  .tabbar {
    position: fixed;
    inset: auto 0 0 0;
    z-index: 10;
    display: grid;
    /* Each column is at least as wide as its label, so at 200% text they don't overlap. */
    grid-template-columns: repeat(5, minmax(min-content, 1fr));
    min-height: var(--tabbar-height);
    padding: var(--space-4) var(--space-3) max(var(--space-4), env(safe-area-inset-bottom));
    background: var(--color-chrome);
    border-top: 1px solid var(--color-border);
  }

  a {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 3px;
    min-height: var(--touch-target);
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
    text-decoration: none;
  }

  /* A little room either side of each label: at 200% text the widest columns shrink to
     their labels, and without it "Pantry" and "Recipes" touch. */
  span {
    padding-inline: var(--space-1);
  }

  a:hover {
    color: var(--color-text);
  }

  a[aria-current='page'] {
    color: var(--color-accent);
    font-weight: var(--weight-bold);
  }
</style>
