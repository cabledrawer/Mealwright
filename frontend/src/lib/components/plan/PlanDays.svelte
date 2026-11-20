<script lang="ts">
  // Days as a list (mockup Plan, the phone): a card per day, a row per meal that is on. Press and
  // hold a meal (or tap it) for the menu: Move to… · Copy to… · Leftovers on… · Remove. Used for
  // the phone's week and for the day picked in the phone's Month.
  import Icon from '#lib/components/Icon.svelte';
  import BatchSessionCard from './BatchSessionCard.svelte';
  import type { PlanMeal } from '#lib/client/plan.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';
  import { pressable } from '#lib/planDrag.svelte.js';
  import {
    cookBatchOf,
    cookedOn,
    itemName,
    mealColour,
    mealTotals,
    sessionTagOfMeal,
    tubOf,
    whoseTub
  } from '#lib/planMeals.js';

  let { actions, days }: { actions: PlanActions; days: string[] } = $props();
  const model = $derived(actions.model);

  /** "Tub 2 of 4 · Wren" for a meal that holds tubs; the prep note on a cook day. */
  function batchLine(meal: PlanMeal): string | null {
    const tubs = meal.items.flatMap((i) => {
      const found = tubOf(model.plan, i);
      if (!found) return [];
      const who = whoseTub(found.tub, model.people, model.plan?.removed_people);
      return [`Tub ${found.tub.number} of ${found.batch.tub_count}${who ? ` · ${who}` : ''}`];
    });
    if (tubs.length) return tubs.join(', ');
    return cookBatchOf(model.plan, meal)?.prep_note ?? null;
  }
</script>

<div class="days">
  {#each days as day (day)}
    <section
      class="day"
      class:today={day === model.today}
      data-plan-day={day}
      aria-label={dayFull(day)}
    >
      <h3>
        <span class="dow">{dayShort(day).toUpperCase()}</span>
        <span class="num">{dayOfMonth(day)}</span>
        {#if day === model.today}<span class="now">Today</span>{/if}
        {#if cookedOn(model.plan, day).length}<span class="cook">Cook day</span>{/if}
      </h3>
      {#each model.sessionsOn(day) as session (session.id)}
        <BatchSessionCard {actions} {session} />
      {/each}
      <ul>
        {#each model.slotsOn as slot (slot.id)}
          {@const meal = model.mealAt(day, slot.id)}
          <li>
            {#if meal}
              <button
                type="button"
                class="meal"
                class:batch={mealColour(model.plan, meal) !== null}
                class:solid={cookBatchOf(model.plan, meal) !== null}
                style:--soft={`var(--batch-${mealColour(model.plan, meal)}-soft)`}
                style:--soft-text={`var(--batch-${mealColour(model.plan, meal)}-soft-text)`}
                style:--solid={`var(--batch-${mealColour(model.plan, meal)})`}
                disabled={actions.readonly}
                use:pressable={{ carry: null, open: () => actions.openMeal(meal) }}
                aria-label="{slot.name}: {meal.items
                  .map((i) => itemName(i, model.plan))
                  .join(', ')}. Open menu"
              >
                <span class="what">
                  <span class="name"
                    >{meal.items.map((i) => itemName(i, model.plan)).join(' · ')}</span
                  >
                  {#if batchLine(meal)}<span class="totals">{batchLine(meal)}</span>{/if}
                  {#if meal.items.length > 1 || meal.kcal !== null}
                    <span class="totals">{mealTotals(meal, model.plan)}</span>
                  {/if}
                </span>
                {#if sessionTagOfMeal(model.plan, meal)}
                  <span class="session">{sessionTagOfMeal(model.plan, meal)}</span>
                {/if}
                <span class="slot">{slot.name}</span>
              </button>
              <button
                type="button"
                class="plus"
                disabled={actions.readonly}
                aria-label="Add to {slot.name} on {dayFull(day)}"
                onclick={() => actions.add(day, slot.id)}
                ><Icon name="plus" size={20} stroke={2.6} /></button
              >
            {:else}
              <button
                type="button"
                class="add"
                disabled={actions.readonly}
                onclick={() => actions.add(day, slot.id)}>+ Add {slot.name.toLowerCase()}</button
              >
            {/if}
          </li>
        {/each}
      </ul>
    </section>
  {/each}
</div>

<style>
  .days {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .session {
    align-self: flex-start;
    padding: 2px 9px;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    white-space: nowrap;
  }

  .day {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .day.today {
    outline: var(--focus-width) solid var(--color-focus);
  }

  h3 {
    display: flex;
    align-items: baseline;
    gap: var(--space-4);
  }

  .dow {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
  }

  .num {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .now,
  .cook {
    padding: 1px var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    gap: var(--space-3);
  }

  .meal.batch {
    background: var(--soft);
    color: var(--soft-text);
  }

  .meal.solid {
    background: var(--solid);
    color: #fff;
  }

  .meal.batch .totals,
  .meal.batch .slot {
    color: inherit;
  }

  .meal {
    flex: 1;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
    min-height: var(--touch-target);
    padding: var(--space-4) var(--space-6);
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-ground);
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
  }

  .what {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: break-word;
  }

  .totals,
  .slot {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  .slot {
    flex: none;
  }

  .plus {
    flex: none;
    width: var(--touch-target);
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    display: grid;
    place-items: center;
    padding: 0;
    cursor: pointer;
  }

  .add {
    flex: 1;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-align: left;
    cursor: pointer;
  }

  .meal:disabled,
  .add:disabled,
  .plus:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
