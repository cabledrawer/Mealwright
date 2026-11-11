<script lang="ts">
  // All recipes. On a phone, and where there is no room for three panes, this is the page; in
  // the desktop's three panes the layout (+layout.svelte) shows the list and this page adds
  // nothing beside it. Either way the list is the layout's.
  import { page } from '$app/state';
  import RecipeListScreen from '#lib/components/RecipeListScreen.svelte';
  import { recipePanes } from '#lib/recipePanes.svelte.js';
  import { RecipeList, filterFromSearch, sharedRecipeList } from '#lib/recipes.svelte.js';

  // The layout's list: one list for both layouts, so crossing the width where the panes fit
  // keeps its rows, its search and its filter (T1). This page stays while the width changes, so
  // this runs on arriving at All recipes, which follows the address for "Use soon": Pantry's
  // "Recipes for these" arrives with ?filter=use-soon, and a plain /recipes isn't left on it.
  const shared = sharedRecipeList();
  const fromAddress = filterFromSearch(new URLSearchParams(page.url.search));
  const list = shared ?? new RecipeList(fromAddress);
  if (fromAddress === 'soon') list.filter = 'soon';
  else if (list.filter === 'soon') list.filter = 'all';
</script>

{#if !recipePanes.fits}
  <RecipeListScreen {list} />
{/if}
