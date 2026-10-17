<script lang="ts">
  import '@fontsource-variable/plus-jakarta-sans';
  import '@fontsource-variable/newsreader';
  import '$lib/styles/tokens.css';
  import '$lib/styles/base.css';

  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
</script>

<main id="main">
  {@render children()}
</main>
