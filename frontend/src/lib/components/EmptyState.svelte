<script lang="ts">
  // A calm card for a whole screen that has nothing on it yet (FE8): a title, a line of words and,
  // when there is one thing to do about it, a button (`action`). A short "nothing here" line inside
  // a screen that has other things is not this: it is a paragraph with the class `mw-quiet`.
  import type { Snippet } from 'svelte';

  let { title, children, action }: { title: string; children: Snippet; action?: Snippet } =
    $props();
</script>

<section class="empty">
  <h2>{title}</h2>
  <p>{@render children()}</p>
  {#if action}<div class="action">{@render action()}</div>{/if}
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

  .action {
    display: flex;
    align-self: flex-start;
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
