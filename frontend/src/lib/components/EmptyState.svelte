<script lang="ts">
  // A calm card for a page that has nothing on it yet.
  import type { Snippet } from 'svelte';

  let { title, children }: { title: string; children: Snippet } = $props();
</script>

<section class="empty">
  <h2>{title}</h2>
  <p>{@render children()}</p>
</section>

<style>
  .empty {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    max-width: 860px;
    padding: var(--space-8);
    border-radius: var(--radius-3xl);
    background: var(--color-surface);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    line-height: 1.5;
  }

  @media (min-width: 768px) {
    .empty {
      padding: 28px;
    }
  }
</style>
