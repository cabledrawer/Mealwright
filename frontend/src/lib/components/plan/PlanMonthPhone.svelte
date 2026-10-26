<script lang="ts">
  // The month on a phone (mockup Month-Phone): a dot grid, a ring on cook days, and tapping a day
  // shows its meals underneath (the same rows as the week, with the long-press menu).
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';
  import { cookedOn, mealColour } from '#lib/planMeals.js';
  import PlanDays from './PlanDays.svelte';

  let {
    actions,
    selected,
    onselect
  }: { actions: PlanActions; selected: string; onselect: (day: string) => void } = $props();
  const model = $derived(actions.model);

  const inMonth = (day: string) => day.slice(0, 7) === model.anchor.slice(0, 7);
  const dots = (day: string) => (model.plan?.meals.filter((m) => m.date === day) ?? []).slice(0, 4);
  const colourOf = (meal: NonNullable<typeof model.plan>['meals'][number]) =>
    mealColour(model.plan, meal);
</script>

<div class="phone-month">
  <div class="grid" role="group" aria-label="Days">
    {#each model.days.slice(0, 7) as day (day)}
      <span class="head" aria-hidden="true">{dayShort(day).slice(0, 1)}</span>
    {/each}
    {#each model.days as day (day)}
      <button
        type="button"
        class="day"
        class:out={!inMonth(day)}
        class:today={day === model.today}
        class:cook={cookedOn(model.plan, day).length > 0}
        aria-pressed={day === selected}
        aria-current={day === model.today ? 'date' : undefined}
        aria-label={dayFull(day)}
        onclick={() => onselect(day)}
      >
        <span class="num">{dayOfMonth(day)}</span>
        <span class="dots" aria-hidden="true">
          {#each dots(day) as meal (meal.id)}
            {@const colour = colourOf(meal)}
            <span class="dot" style:background={colour ? `var(--batch-${colour})` : undefined}
            ></span>
          {/each}
        </span>
      </button>
    {/each}
  </div>

  <PlanDays {actions} days={[selected]} />
</div>

<style>
  .phone-month {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: var(--space-2) 0;
    padding: var(--space-6) var(--space-2);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .head {
    text-align: center;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .day {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    min-height: var(--touch-target);
    padding: var(--space-2) 0;
    border: 2px solid transparent;
    border-radius: var(--radius-full);
    background: none;
    color: var(--color-text);
    font: inherit;
    cursor: pointer;
  }

  /* Days of the next or last month: quieter, but still readable. */
  .day.out .num {
    color: var(--color-text-muted);
  }

  .day.cook {
    border-color: var(--color-inverse);
  }

  .day.today .num {
    color: var(--color-accent);
    font-weight: var(--weight-extrabold);
  }

  .day[aria-pressed='true'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .num {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .dots {
    display: flex;
    gap: 2px;
    height: 6px;
  }

  .dot {
    width: 6px;
    height: 6px;
    border-radius: var(--radius-full);
    background: var(--color-text-muted);
  }
</style>
