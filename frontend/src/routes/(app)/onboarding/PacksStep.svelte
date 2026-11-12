<script lang="ts">
  // Onboarding's "Start with common ingredients?" (0.9 U2; spec section 2 "Starter ingredient
  // packs": the optional onboarding step opens the same picker as Ingredients). Optional.
  import { network } from '#lib/network.svelte.js';
  import { starterPacks } from '#lib/starterPacks.svelte.js';
</script>

<p class="note">
  Ready-made ingredients with their aisle, usual UK pack sizes and other names. You see the list
  first and can untick anything.
</p>
<button type="button" class="add" disabled={network.offline} onclick={() => starterPacks.show()}
  >Add a starter pack</button
>
