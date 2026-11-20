<script lang="ts">
  // The buttons at the foot of a sheet or dialog (FE16): stacked and full width on a phone, the
  // main one first (on top); side by side on a computer, the main one last (on the right), the
  // way every dialog in the mockups ends. Put the main Button first in the source.
  import type { Snippet } from 'svelte';

  let { children }: { children: Snippet } = $props();
</script>

<div class="buttons">{@render children()}</div>

<style>
  .buttons {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  @media (min-width: 768px) {
    .buttons {
      flex-direction: row-reverse;
      flex-wrap: wrap;
      justify-content: flex-start;
      align-items: center;
      padding-top: var(--space-3);
    }

    .buttons :global(.mw-button) {
      width: auto;
      min-height: var(--touch-target);
      padding: 0 var(--space-7);
    }
  }
</style>
