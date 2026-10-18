<script lang="ts">
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();
  const Gallery = $derived(data.Gallery);
</script>

<svelte:head><title>Component gallery</title></svelte:head>

<Gallery />
