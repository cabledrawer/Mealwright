<script lang="ts">
  // All recipes. On a phone, and where there is no room for three panes, this is the page; in
  // the desktop's three panes the layout (+layout.svelte) holds the list and this page adds
  // nothing beside it.
  import { page } from '$app/state';
  import RecipeListScreen from '$lib/components/RecipeListScreen.svelte';
  import { recipePanes } from '$lib/recipePanes.svelte';
  import { RecipeList, filterFromSearch } from '$lib/recipes.svelte';

  // Pantry's "Recipes for these" arrives with ?filter=use-soon, which starts the list on "Use soon".
  const list = new RecipeList(filterFromSearch(new URLSearchParams(page.url.search)));
</script>

{#if !recipePanes.fits}
  <RecipeListScreen {list} />
{/if}
