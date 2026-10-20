<script lang="ts">
  // Recipes on a computer (mockups Desktop-Recipe and Dark-Recipe, spec "Platform emphasis" and
  // "Recipe page"): a Notes-style set of three panes. The sidebar is the first; All recipes is
  // the second; the recipe being read is the third. This layout stays in place while recipes
  // open and close beside the list, so the list keeps its search, its filter and its scroll, and
  // Back and Forward move between recipes like any other pages.
  //
  // Only All recipes and a recipe's own page use the panes, and only where there is room
  // (recipePanes.ts). Ingredients and Drafts, and every smaller screen, are single pages as
  // before, with no wrapper at all.
  //
  // /recipes shows the list and a calm empty reading pane (cabledrawer to confirm: the alternative
  // was to open the first recipe).
  import type { Snippet } from 'svelte';
  import { page } from '$app/state';
  import ChooseRecipe from '$lib/components/ChooseRecipe.svelte';
  import OfflineNote from '$lib/components/OfflineNote.svelte';
  import RecipeListScreen from '$lib/components/RecipeListScreen.svelte';
  import { RECIPES_PAGES, isCurrentRecipesPage } from '$lib/nav';
  import { network } from '$lib/network.svelte';
  import { recipePanes } from '$lib/recipePanes.svelte';
  import { RecipeList, filterFromSearch } from '$lib/recipes.svelte';

  let { children }: { children: Snippet } = $props();

  // Pantry's "Recipes for these" arrives with ?filter=use-soon, which starts the list on "Use soon".
  const list = new RecipeList(filterFromSearch(page.url.searchParams));
  const panes = $derived(
    recipePanes.fits && isCurrentRecipesPage(RECIPES_PAGES[0]!, page.url.pathname)
  );
  const currentId = $derived(page.params.id === undefined ? null : Number(page.params.id));
  /** There are no recipes at all: nothing to point to in the reading pane. */
  const none = $derived(list.loaded && !list.problem && list.all === 0);

  let reading = $state<HTMLElement>();
  // Each recipe opens at its top, not where the last one was left.
  $effect(() => {
    void page.params.id;
    if (reading) reading.scrollTop = 0;
  });
</script>

<svelte:head>
  {#if panes && currentId === null}<title>Recipes · Mealwright</title>{/if}
</svelte:head>

{#if panes}
  <div class="panes">
    <!-- Offline: one note for the whole area, not one in each pane. The panes stay in place
         (hidden), so the search and the open recipe are still there when the connection is back. -->
    {#if network.offline}
      <div class="offline">
        <h1>Recipes</h1>
        <OfflineNote screen="Recipes" />
      </div>
    {/if}
    <div class="row" hidden={network.offline}>
      <RecipeListScreen pane {list} {currentId} />
      <div class="reading" role="region" aria-label="Recipe" bind:this={reading}>
        {#if currentId === null}
          {#if !none}
            <ChooseRecipe />
          {/if}
        {/if}
        {@render children()}
      </div>
    </div>
  </div>
{:else}
  {@render children()}
{/if}

<style>
  /* The three panes fill the window beside the sidebar; each scrolls on its own. */
  :global(main:has(> .panes)) {
    gap: 0;
    padding: 0;
  }

  .panes {
    height: 100dvh;
    min-width: 0;
  }

  .row {
    display: flex;
    height: 100%;
    min-width: 0;
  }

  .row[hidden] {
    display: none;
  }

  /* The reading pane is the page's paper: white in light, a shade darker than the ground in dark. */
  /* `position: relative`: the screen-reader-only text that sits inside it scrolls with it,
     instead of pushing the page itself taller. */
  .reading {
    position: relative;
    flex: 1 1 0;
    min-width: 0;
    height: 100%;
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-width: thin;
    border-left: 1px solid var(--color-border);
    background: var(--color-chrome);
    --reading-card: var(--color-reading-card);
    --reading-chip: var(--color-reading-chip);
  }

  .offline {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: var(--space-10) var(--space-11);
  }

  .offline h1 {
    font-size: var(--text-title-desktop);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
    word-spacing: normal;
    line-height: 1.15;
  }
</style>
