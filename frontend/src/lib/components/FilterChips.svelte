<script lang="ts" generics="T extends string">
  // A row of round filter buttons, one chosen at a time (mockup Recipes-Phone: All · Can cook
  // now · the household's tags). They wrap onto more lines rather than scroll sideways.
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
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    max-width: 100%;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }
</style>
