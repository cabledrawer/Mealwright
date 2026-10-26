<script lang="ts">
  // The week on a computer or iPad (mockup Desktop-Plan): a column per day, a row per meal that
  // is on, the row's name running up the side. It fills the height. Nothing here needs a mouse:
  // every card opens a menu, and a finger can drag.
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';
  import { cookedOn } from '#lib/planMeals.js';
  import MealCell from './MealCell.svelte';

  let { actions }: { actions: PlanActions } = $props();
  const model = $derived(actions.model);
</script>

<div class="week" role="group" aria-label="Week plan">
  <div
    class="grid"
    style:grid-template-rows="auto repeat({model.slotsOn.length}, minmax(76px, 1fr))"
  >
    <span class="corner"></span>
    {#each model.days as day (day)}
      {@const cooking = cookedOn(model.plan, day)}
      <h3 class="day" class:today={day === model.today} aria-label={dayFull(day)}>
        <span class="dow">{dayShort(day).toUpperCase()}{day === model.today ? ' · TODAY' : ''}</span
        >
        <b>{dayOfMonth(day)}</b>
        {#if cooking.length}<span class="cook">COOK</span>{/if}
      </h3>
    {/each}

    {#each model.slotsOn as slot (slot.id)}
      <span class="row-label">{slot.name.toUpperCase()}</span>
      {#each model.days as day (day)}
        <MealCell {actions} {day} {slot} />
      {/each}
    {/each}
  </div>
</div>

<style>
  .week {
    flex: 1;
    min-height: 0;
    display: flex;
    padding: var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
    overflow-y: auto;
  }

  .grid {
    flex: 1;
    display: grid;
    grid-template-columns: 36px repeat(7, minmax(0, 1fr));
    gap: var(--space-4);
    min-height: min-content;
  }

  .day {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-md);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .day b {
    color: var(--color-text);
    font-size: var(--text-2xl);
  }

  .day.today {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .day.today b {
    color: var(--color-accent-on-soft);
  }

  .cook {
    padding: 1px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-xs);
    letter-spacing: var(--tracking-overline);
  }

  .row-label {
    writing-mode: vertical-rl;
    transform: rotate(180deg);
    align-self: center;
    justify-self: center;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    overflow: hidden;
    max-height: 100%;
  }
</style>
