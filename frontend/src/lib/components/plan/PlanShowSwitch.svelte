<script lang="ts">
  // The switch Both · Eat · Cook (spec "The Plan redesign, 0.7.0"; mockups PlanEat07-Phone,
  // PlanCook07-*). It says which of the three the Plan shows; the page keeps the choice.
  import type { PlanShow } from '#lib/planShow.js';

  let { value, onchange }: { value: PlanShow; onchange: (show: PlanShow) => void } = $props();

  // "Both" is the cards as before; "Eat" is what is eaten; "Cook" is the cooking by day.
  const BUTTONS: { show: PlanShow; words: string }[] = [
    { show: 'both', words: 'Both' },
    { show: 'eat', words: 'Eat' },
    { show: 'cook', words: 'Cook' }
  ];
</script>

<div class="show" role="group" aria-label="Show">
  {#each BUTTONS as button (button.show)}
    <button type="button" aria-pressed={value === button.show} onclick={() => onchange(button.show)}
      >{button.words}</button
    >
  {/each}
</div>

<style>
  .show {
    display: flex;
    padding: var(--space-2);
    border-radius: var(--radius-full);
    background: var(--color-fill-strong);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  button[aria-pressed='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }
</style>
