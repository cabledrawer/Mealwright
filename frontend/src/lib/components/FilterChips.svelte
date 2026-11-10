<script lang="ts" generics="T extends string">
  // A row of round filter buttons, one chosen at a time (mockup Dark-RecipesTags08-Phone: All ·
  // Can cook now · the household's tags). One row that scrolls sideways inside itself and never
  // wraps (cabledrawer 9 Nov); every chip is a button, so the keyboard reaches them all and the
  // browser scrolls a focused one into view. The page itself never scrolls sideways.
  let {
    options,
    selected,
    label,
    onselect
  }: {
    options: { value: T; label: string }[];
    selected: T;
    /** What the group is, for a screen reader: "Show". */
    label: string;
    onselect: (value: T) => void;
  } = $props();
</script>

<div class="chips" role="group" aria-label={label}>
  {#each options as option (option.value)}
    <button
      type="button"
      class="chip"
      aria-pressed={selected === option.value}
      onclick={() => onselect(option.value)}>{option.label}</button
    >
  {/each}
</div>

<style>
  .chips {
    display: flex;
    flex-wrap: nowrap;
    gap: var(--space-3);
    min-width: 0;
    max-width: 100%;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scrollbar-width: none;
    /* Room for the focus ring, which the scrolling box would otherwise cut off. */
    padding: var(--space-2);
    margin: calc(var(--space-2) * -1);
  }

  .chips::-webkit-scrollbar {
    display: none;
  }

  .chip {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    flex: none;
    padding: 0 var(--space-6);
    white-space: nowrap;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }
</style>
