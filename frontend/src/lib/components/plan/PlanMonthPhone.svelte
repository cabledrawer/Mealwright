<script lang="ts">
  // The month on a phone (mockups Month-Phone, Dark-PlanMonth08-Phone; F149): a grid with a dot for
  // each meal (Eat) and a blue ring on cook days (Cook), both in Both. Tapping a day shows what
  // that switch says underneath: what is eaten, what is cooked (with Start cooking), or both.
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';
  import { cookedOn, mealColour } from '#lib/planMeals.js';
  import PlanDays from './PlanDays.svelte';
  import type { PlanShow } from '#lib/planShow.js';
  import type { CookEntry } from '#lib/planCook.js';

  let {
    actions,
    show,
    selected,
    onselect,
    onstart,
    oncook
  }: {
    actions: PlanActions;
    show: PlanShow;
    selected: string;
    onselect: (day: string) => void;
    /** Start cooking: Cook mode for this recipe in this meal. */
    onstart: (entry: CookEntry) => void;
    /** "You cook today →": show Cook. */
    oncook: () => void;
  } = $props();
  const model = $derived(actions.model);

  const inMonth = (day: string) => day.slice(0, 7) === model.anchor.slice(0, 7);
  const dots = (day: string) => (model.plan?.meals.filter((m) => m.date === day) ?? []).slice(0, 4);
  const eating = $derived(show !== 'cook');
  const cooking = $derived(show !== 'eat');
  const cooksOnSelected = $derived(cookedOn(model.plan, selected).length > 0);
  /** What the marks mean (the mockup's words). */
  const legend = $derived(
    show === 'eat'
      ? 'Dots: meals planned, in each batch’s colour.'
      : show === 'cook'
        ? 'Blue ring: a day you cook.'
        : 'Blue ring: a day you cook. Dots: meals planned.'
  );
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
        class:cook={cooking && cookedOn(model.plan, day).length > 0}
        aria-pressed={day === selected}
        aria-current={day === model.today ? 'date' : undefined}
        aria-label={dayFull(day)}
        onclick={() => onselect(day)}
      >
        <span class="num">{dayOfMonth(day)}</span>
        {#if eating}
          <span class="dots" aria-hidden="true">
            {#each dots(day) as meal (meal.id)}
              {@const colour = colourOf(meal)}
              <span class="dot" style:background={colour ? `var(--batch-${colour})` : undefined}
              ></span>
            {/each}
          </span>
        {/if}
      </button>
    {/each}
    <p class="legend" data-testid="month-legend">{legend}</p>
  </div>

  <div class="list">
    <!-- Loaded when first asked for, so the Plan's first load stays small (size limit). -->
    {#if show === 'cook' || (show === 'both' && cooksOnSelected)}
      {#await import('./PlanCook.svelte') then { default: Cook }}
        <Cook {actions} days={[selected]} {onstart} summary={false} />
      {/await}
    {/if}
    {#if show === 'eat'}
      {#await import('./PlanEat.svelte') then { default: Eat }}
        <Eat {actions} days={[selected]} {oncook} />
      {/await}
    {:else if show === 'both'}
      <!-- Both keeps the day's meals with their + (the phone's Both list), under the cooking. -->
      <PlanDays {actions} days={[selected]} />
    {/if}
  </div>
</div>

<style>
  .phone-month {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
  }

  /* From a tablet's width (768 px) the day's meals sit beside the grid, so the month and the day
     fit one screen (F47): the day's list scrolls on its own. */
  @media (min-width: 768px) {
    .phone-month {
      flex-direction: row;
      align-items: flex-start;
    }

    .grid,
    .list {
      flex: 1 1 0;
      min-width: 0;
    }

    .list {
      max-height: calc(100dvh - 2 * var(--space-10) - 140px);
      overflow-y: auto;
      overscroll-behavior: contain;
    }
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

  /* The blue ring: a day you cook. */
  .day.cook {
    border-color: var(--color-cook-on-soft);
  }

  .legend {
    grid-column: 1 / -1;
    margin: var(--space-2) var(--space-2) 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
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
