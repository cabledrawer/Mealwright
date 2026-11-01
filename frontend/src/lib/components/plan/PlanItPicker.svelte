<script lang="ts">
  // Plan it on the recipe page (spec "Plan views and cards", cabledrawer 31 Oct): the next 14 days from
  // today in two rows of seven, and at each meal what is already planned. Loaded when Plan it is
  // first pressed, so the Plan's own page does not carry it (size limit).
  import type { PlanModel } from '#lib/plan.svelte.js';
  import { addDays, dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';
  import { itemName } from '#lib/planMeals.js';

  let {
    model,
    day = $bindable(null),
    slotId = $bindable(null)
  }: { model: PlanModel; day: string | null; slotId: number | null } = $props();

  const days = $derived(
    model.today ? Array.from({ length: 14 }, (_, i) => addDays(model.today, i)) : []
  );

  /** What is planned at a meal, or "Nothing yet". */
  function planned(d: string, id: number): string {
    const meal = model.mealAt(d, id);
    return meal && meal.items.length
      ? meal.items.map((i) => itemName(i, model.plan)).join(' · ')
      : 'Nothing yet';
  }
  const anything = (d: string) => model.slotsOn.some((s) => planned(d, s.id) !== 'Nothing yet');
</script>

<div class="days" role="group" aria-label="Day">
  {#each days as d (d)}
    <button
      type="button"
      aria-pressed={day === d}
      aria-label={dayFull(d)}
      aria-describedby={anything(d) ? `plan-it-day-${d}` : undefined}
      onclick={() => (day = d)}
      ><span>{dayShort(d)}</span><b>{dayOfMonth(d)}</b>{#if anything(d)}<i
          class="dot"
          aria-hidden="true"
        ></i><span id="plan-it-day-{d}" class="sr">Something planned</span>{/if}</button
    >
  {/each}
</div>
<div class="slots" role="group" aria-label="Meal">
  {#each model.slotsOn as slot (slot.id)}
    <button
      type="button"
      aria-pressed={slotId === slot.id}
      aria-label={slot.name}
      aria-describedby={day !== null ? `plan-it-meal-${slot.id}` : undefined}
      onclick={() => (slotId = slot.id)}
      ><span>{slot.name}</span>{#if day !== null}<small id="plan-it-meal-{slot.id}"
          >{planned(day, slot.id)}</small
        >{/if}</button
    >
  {/each}
</div>

<style>
  .sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .days {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .days button {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 54px;
    padding: var(--space-3) 0;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  .days b {
    font-size: var(--text-lg);
  }

  .dot {
    position: absolute;
    top: 4px;
    right: 4px;
    width: 6px;
    height: 6px;
    border-radius: var(--radius-full);
    background: var(--color-accent);
  }

  .slots {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .slots button {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    max-width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-2) var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-align: left;
  }

  .slots small {
    max-width: 100%;
    overflow-wrap: anywhere;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  .days button[aria-pressed='true'],
  .slots button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .slots button[aria-pressed='true'] small {
    color: inherit;
  }

  .days button[aria-pressed='true'] .dot {
    background: var(--color-inverse-text);
  }
</style>
