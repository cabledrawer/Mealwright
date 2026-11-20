<script lang="ts">
  // The catch part of a lazy await-import block that has to bind its props (so <Lazy> cannot
  // be used): says "Couldn’t open that. Try again." once, with nothing drawn (FE2).
  import { onMount } from 'svelte';
  import { couldntOpen } from '#lib/lazyCode.svelte.js';

  let { retry }: { retry?: () => void } = $props();

  onMount(() => couldntOpen(retry));
</script>
