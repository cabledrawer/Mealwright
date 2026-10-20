<script lang="ts">
  // One recipe (mockups Recipe and Dark-Phone-Recipe). The screen starts afresh for each
  // recipe, so a recipe opened from inside another begins at its own servings.
  import { page } from '$app/state';
  import RecipeScreen from './RecipeScreen.svelte';
</script>

{#key page.params.id}
  <RecipeScreen id={Number(page.params.id)} />
{/key}
