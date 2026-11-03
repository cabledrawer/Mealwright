<script lang="ts">
  // One at a time (F141): built in the next commit. Until then it shows nothing.
  import type { ImportFlow } from '#lib/import.svelte.js';

  /* eslint-disable svelte/no-unused-props -- a stand-in until the next commit */
  let {
    flow
  }: {
    flow: ImportFlow;
    closing: boolean;
    onclose: () => void;
    onsave: () => void;
    onseeall: () => void;
  } = $props();
</script>

<p class="visually-hidden">{flow.name}</p>
