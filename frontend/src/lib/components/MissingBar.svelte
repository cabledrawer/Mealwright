<script lang="ts">
  // "1 missing · Add to the list" under a recipe's ingredients (mockup Recipe; cabledrawer 19 Oct,
  // question 23). The button adds each missing ingredient to the main shopping list the way
  // a tap on a staple does: it works offline, and one Undo takes them all back. It is only
  // there when something is left to add.
  let {
    count,
    onadd
  }: {
    count: number;
    onadd: () => void;
  } = $props();
</script>

<div class="bar">
  <span class="count">{count} missing</span>
  <button type="button" onclick={onadd}>Add to the list</button>
</div>

<style>
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-3) var(--space-3) 14px;
    border-radius: var(--radius-lg);
    background: var(--color-fill);
  }

  .count {
    flex: 1;
    min-width: 6em;
    color: var(--color-use-soon-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 14px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }
</style>
