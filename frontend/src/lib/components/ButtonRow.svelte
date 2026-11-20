<script lang="ts">
  // The buttons at the foot of a sheet or dialog (FE16). The order in the source is the order on
  // the screen and the Tab order, at every width (cabledrawer 20 Nov): the other choice(s) first,
  // the main one last, on the right, the way the mockups' dialogs end. Never reverse it with CSS.
  // `stack` is for the few sheets whose mockup stacks them full width, main first on top.
  import type { Snippet } from 'svelte';

  let { stack = false, children }: { stack?: boolean; children: Snippet } = $props();
</script>

<div class="buttons" class:stack>{@render children()}</div>

<style>
  .buttons {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    align-items: center;
    gap: var(--space-4);
  }

  .buttons :global(.mw-button) {
    flex: 1 1 auto;
    width: auto;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
  }

  .stack {
    flex-direction: column;
    flex-wrap: nowrap;
    align-items: stretch;
  }

  .stack :global(.mw-button) {
    flex: none;
    width: 100%;
    min-height: 52px;
  }

  @media (min-width: 768px) {
    .buttons:not(.stack) {
      padding-top: var(--space-3);
    }

    .buttons:not(.stack) :global(.mw-button) {
      flex: none;
    }
  }
</style>
