<script lang="ts">
  import { page } from '$app/state';
  import RecipeEditor from '$lib/components/recipe/RecipeEditor.svelte';

  const id = $derived(Number(page.params.id));
</script>

<!-- A new editor for each recipe, so one never keeps another's boxes. -->
{#key id}
  <RecipeEditor recipeId={id} />
{/key}
