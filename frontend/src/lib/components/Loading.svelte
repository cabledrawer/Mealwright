<script lang="ts">
  // The one "still loading" line. Every screen that waits on the server shows this, so the words,
  // the look and the screen-reader announcement are the same everywhere (FE15).
  let { what = 'Loading…' }: { what?: string } = $props();
</script>

<p class="loading" role="status">{what}</p>

<style>
  .loading {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }
</style>
