<script lang="ts">
  // The one "still loading" line. Every screen that waits on the server shows this, so the words,
  // the look and the screen-reader announcement are the same everywhere (FE15).
  // `spin` (F258, proposed, for cabledrawer): a long wait, such as Import from Mealie reading its
  // file, also shows the turning ring before the words.
  import Spinner from './Spinner.svelte';

  let { what = 'Loading…', spin = false }: { what?: string; spin?: boolean } = $props();
</script>

<p class="loading" class:spin role="status">
  {#if spin}<Spinner />{/if}{what}
</p>

<style>
  .loading {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .spin {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }
</style>
