<script lang="ts">
  // Serves − N + (0.7 P1; spec "The Plan redesign": "Click a meal → Serves − N + (amounts and the
  // list follow)", F57). It works on meals planned before the update too: with no number set,
  // it starts from the recipe's own Serves (`eating`). A few quick presses are one change, sent
  // a moment after the last press (or when the menu closes), so there is one Undo, not five.
  import { onDestroy } from 'svelte';
  import type { PlanItem } from '#lib/client/plan.js';
  import type { PlanModel } from '#lib/plan.svelte.js';
  import { itemName } from '#lib/planMeals.js';

  let {
    model,
    item,
    named = false,
    after = false,
    disabled = false
  }: {
    model: PlanModel;
    item: PlanItem;
    named?: boolean;
    /** Name the recipe after the word, "Serves · Lentil soup" (a meal cooked in parts, F166). */
    after?: boolean;
    disabled?: boolean;
  } = $props();

  /** The most people a recipe can be planned for (the server's limit). */
  const MOST = 99;
  /** What the server holds, and what the buttons have made it since (null: no press yet). */
  let draft = $state<number | null>(null);
  // The item as the plan holds it now (the menu's own copy goes stale after a change).
  const live = $derived(
    model.plan?.meals.flatMap((m) => m.items).find((i) => i.id === item.id) ?? item
  );
  const shown = $derived(draft ?? live.eating ?? 1);
  let timer: ReturnType<typeof setTimeout> | undefined;

  function send(): void {
    clearTimeout(timer);
    timer = undefined;
    const wanted = draft;
    draft = null;
    if (wanted !== null && wanted !== (live.eating ?? 1)) void model.setServings(live, wanted);
  }

  function change(by: number): void {
    const next = Math.min(MOST, Math.max(1, shown + by));
    if (next === shown) return;
    draft = next;
    clearTimeout(timer);
    timer = setTimeout(send, 700);
  }

  // Closing the menu sends what is waiting.
  onDestroy(() => {
    if (timer !== undefined) send();
  });

  const label = $derived(
    after
      ? `Serves · ${itemName(item, model.plan)}`
      : named
        ? `${itemName(item, model.plan)} serves`
        : 'Serves'
  );
</script>

<div class="serves" role="group" aria-label={label}>
  <span class="label">{label}</span>
  <button
    type="button"
    aria-label="One fewer"
    disabled={disabled || shown <= 1}
    onclick={() => change(-1)}>−</button
  >
  <output aria-live="polite" data-testid="serves-{item.id}">{shown}</output>
  <button
    type="button"
    aria-label="One more"
    disabled={disabled || shown >= MOST}
    onclick={() => change(1)}>+</button
  >
</div>

<style>
  .serves {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-4) var(--space-6);
    min-height: 54px;
    padding: var(--space-3) var(--space-7);
    border-radius: var(--radius-button);
    background: var(--color-fill);
  }

  .label {
    flex: 1 1 6rem;
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    overflow-wrap: break-word;
  }

  button {
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-3xl);
    font-weight: var(--weight-bold);
    line-height: 1;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  output {
    min-width: 2ch;
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    text-align: center;
  }
</style>
