<script lang="ts">
  // A bar between the editor's top bar and its boxes: "You’re offline…", "Couldn’t save. Try
  // again." with its button, "Wren changed this recipe…" with its two buttons.
  import type { Snippet } from 'svelte';
  import Icon from '../Icon.svelte';

  let {
    tone,
    children
  }: {
    /** offline: calm · trouble: something didn't save · conflict: someone else saved first. */
    tone: 'offline' | 'trouble' | 'conflict' | 'draft';
    children: Snippet;
  } = $props();
</script>

<div class="note {tone}" role={tone === 'offline' || tone === 'draft' ? 'status' : 'alert'}>
  {#if tone === 'offline'}<Icon name="cloud-off" size={18} />{/if}
  {#if tone === 'trouble'}<Icon name="alert" size={18} />{/if}
  {@render children()}
</div>

<style>
  .note {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-5);
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-lg);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .offline,
  .draft {
    background: var(--color-fill);
    font-weight: var(--weight-semibold);
  }

  .draft :global(span) {
    flex: 1;
  }

  .trouble {
    border: 1px solid var(--color-warning-border);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .trouble :global(span:not(.choices)) {
    flex: 1;
  }

  .trouble :global(.mw-pill) {
    color: var(--color-text);
  }

  .conflict {
    flex-direction: column;
    align-items: flex-start;
    border: 1px solid var(--color-maybe-chip-border);
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
  }
</style>
