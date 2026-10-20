<script lang="ts">
  // All recipes. On a phone, and where there is no room for three panes, this is the page; in
  // the desktop's three panes the layout (+layout.svelte) holds the list and this page adds
  // nothing beside it.
  import RecipeListScreen from '$lib/components/RecipeListScreen.svelte';
  import { recipePanes } from '$lib/recipePanes.svelte';
</script>

{#if !recipePanes.fits}
  <RecipeListScreen />
{/if}
