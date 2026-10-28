<script lang="ts">
  // The month on a computer or iPad (mockup Month-Desktop): whole weeks of day cells, each with
  // a chip per meal ("+2 more" when full), a COOK tag on cook days, one colour per batch, and a
  // side panel with "Batches this month" and "Empty days ahead". A chip drags to another day
  // (it keeps its meal, so a dinner stays a dinner); Alt copies; the Leftovers zone plans
  // leftovers. A recipe from the tray dropped on a day goes to its last empty meal.
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayOfMonth, dayShort, monthWords } from '#lib/planDates.js';
  import { drag, pressable } from '#lib/planDrag.svelte.js';
  import { colourOfBatch, cookBatchOfItem, cookedOn, itemName, tubOf } from '#lib/planMeals.js';
  import type { PlanBatch, PlanItem, PlanMeal } from '#lib/client/plan.js';

  let { actions }: { actions: PlanActions } = $props();
  const model = $derived(actions.model);
  const can = $derived(actions.desktop && !actions.readonly);
  const SHOWN = 3;

  const inMonth = (day: string) => day.slice(0, 7) === model.anchor.slice(0, 7);
  const mealsOn = (day: string): PlanMeal[] =>
    (model.plan?.meals.filter((m) => m.date === day) ?? []).sort((a, b) => a.slot_id - b.slot_id);

  /** One chip is one thing in a meal (F45): a day's cooking never hides inside a meal's joined
   * names. `cook` is the batch it is the cooking of; `colour` is its batch's colour. */
  interface Chip {
    meal: PlanMeal;
    item: PlanItem;
    cook: PlanBatch | null;
    colour: number | null;
  }

  function chipOf(meal: PlanMeal, item: PlanItem): Chip {
    const cook = cookBatchOfItem(model.plan, meal, item);
    const batch = cook ?? tubOf(model.plan, item)?.batch ?? null;
    return { meal, item, cook, colour: batch ? colourOfBatch(batch) : null };
  }

  /** A day's chips: the cooking first, then the rest in meal order. */
  const chipsOn = (day: string): Chip[] => {
    const all = mealsOn(day).flatMap((meal) => meal.items.map((item) => chipOf(meal, item)));
    return [...all.filter((c) => c.cook), ...all.filter((c) => !c.cook)];
  };

  let fillNote = $state('');
  /** "Fill from freezer first": empty days ahead get a tub from the freezer. */
  async function fillFromFreezer() {
    const first = model.days.find((d) => d >= model.today);
    const last = model.days.at(-1);
    if (!first || !last) return;
    fillNote = '';
    const outcome = await model.fillFromFreezer(first, last);
    if (outcome.ok && outcome.value.change === null) {
      fillNote = 'Nothing to fill: no empty days ahead, or no tubs in the freezer.';
    }
  }

  /** Days from today on, in this month, with nothing planned. */
  const emptyAhead = $derived(
    model.days.filter((d) => inMonth(d) && d >= model.today && mealsOn(d).length === 0).slice(0, 6)
  );
  /** Batches cooked this month, and those whose tubs are eaten this month (F46). */
  const batches = $derived.by(() => {
    const plan = model.plan;
    if (!plan) return [];
    const tubBatch = new Map(plan.tubs.map((t) => [t.id, t.batch_id]));
    const eaten = new Set(
      plan.meals
        .filter((meal) => inMonth(meal.date))
        .flatMap((meal) => meal.items)
        .map((item) => (item.tub_id === null ? undefined : tubBatch.get(item.tub_id)))
        .filter((id) => id !== undefined)
    );
    return plan.batch_cooks
      .filter((b) => inMonth(b.cooked_on) || eaten.has(b.id))
      .sort((a, b) => a.cooked_on.localeCompare(b.cooked_on) || a.id - b.id);
  });
</script>

<div class="month">
  <div class="calendar" role="group" aria-label={monthWords(model.anchor)}>
    <div class="head" aria-hidden="true">
      {#each model.days.slice(0, 7) as day (day)}<span>{dayShort(day).toUpperCase()}</span>{/each}
    </div>
    <div class="cells">
      {#each model.days as day (day)}
        {@const chips = chipsOn(day)}
        {@const over = drag.isOver(day, null)}
        <div
          class="day"
          class:out={!inMonth(day)}
          class:today={day === model.today}
          class:over
          data-drop-day={day}
          data-testid="day-{day}"
          role="group"
          aria-label={dayFull(day)}
        >
          <div class="top">
            <button
              type="button"
              class="num"
              disabled={actions.readonly}
              aria-label="Add to {dayFull(day)}"
              onclick={() => actions.add(day, null)}>{dayOfMonth(day)}</button
            >
            {#if day === model.today}<span class="now">Today</span>{/if}
            {#if cookedOn(model.plan, day).length}
              <span class="cook" title="Cook day">COOK</span>
            {/if}
          </div>
          {#each chips.slice(0, SHOWN) as chip (chip.item.id)}
            {@const { meal, item, colour } = chip}
            {@const whole = meal.items.length === 1}
            <button
              type="button"
              class="chip"
              class:batch={colour !== null}
              class:solid={chip.cook !== null}
              style:--solid={colour ? `var(--batch-${colour})` : undefined}
              class:can
              style:--soft={colour ? `var(--batch-${colour}-soft)` : undefined}
              style:--soft-text={colour ? `var(--batch-${colour}-soft-text)` : undefined}
              disabled={actions.readonly}
              use:pressable={{
                carry: can
                  ? () => (whole ? actions.carryMeal(meal) : actions.carryItem(meal, item))
                  : null,
                open: () => (whole ? actions.openMeal(meal) : actions.openItem(meal, item))
              }}
              aria-label="{chip.cook ? 'Cooking ' : ''}{itemName(
                item,
                model.plan
              )}, {model.slotName(meal.slot_id)} on {dayFull(day)}. Open menu"
              ><span class="chip-name">{itemName(item, model.plan)}</span></button
            >
          {/each}
          {#if chips.length > SHOWN}
            <button type="button" class="more" onclick={() => actions.openDay(day)}
              >+{chips.length - SHOWN} more</button
            >
          {/if}
          {#if over && drag.carried}
            <div class="zones" class:one={!drag.carried.zones} aria-hidden="true">
              {#if drag.carried.zones}
                <span data-drop-zone="move" class:on={drag.over?.mode === 'move'}>Move</span>
                <span data-drop-zone="copy" class:on={drag.over?.mode === 'copy'}
                  >Copy <small>Alt</small></span
                >
                {#if drag.carried.leftoversOk?.(day, null) ?? true}
                  <span data-drop-zone="leftovers" class:on={drag.over?.mode === 'leftovers'}
                    >Leftovers here</span
                  >
                {/if}
              {:else}
                <span class="on">Drop a recipe</span>
              {/if}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </div>

  <aside class="side" aria-label="This month">
    <section>
      <h3>Batches this month</h3>
      {#if batches.length}
        <ul>
          {#each batches as batch (batch.id)}
            <li>
              <span class="dot" style:background="var(--batch-{colourOfBatch(batch)})"></span>
              <span class="b-name">{batch.recipe_name}</span>
              <span class="b-when">{dayShort(batch.cooked_on)} {dayOfMonth(batch.cooked_on)}</span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="none">No batch cooks this month.</p>
      {/if}
    </section>
    <section>
      <h3>Empty days ahead</h3>
      <button
        type="button"
        class="fill"
        disabled={actions.readonly ||
          emptyAhead.length === 0 ||
          model.tubsLeft.every((t) => t.place_kind !== 'freezer')}
        onclick={() => void fillFromFreezer()}>Fill from freezer first</button
      >
      {#if fillNote}<p class="none" role="status">{fillNote}</p>{/if}
      {#if emptyAhead.length}
        <ul class="empty">
          {#each emptyAhead as day (day)}
            <li>
              <button
                type="button"
                disabled={actions.readonly}
                onclick={() => actions.add(day, null)}>{dayShort(day)} {dayOfMonth(day)}</button
              >
            </li>
          {/each}
        </ul>
      {:else}
        <p class="none">Every day ahead has something planned.</p>
      {/if}
    </section>
  </aside>
</div>

<style>
  .month {
    flex: 1;
    min-height: 0;
    display: flex;
    gap: var(--space-6);
  }

  .calendar {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
    overflow-y: auto;
  }

  .head,
  .cells {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .head span {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
  }

  .cells {
    flex: 1;
    grid-auto-rows: minmax(104px, 1fr);
  }

  .day {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
    padding: var(--space-3);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
  }

  /* Days of the next or last month: quieter, but still readable. */
  .day.out .num {
    color: var(--color-text-muted);
    font-weight: var(--weight-bold);
  }

  .day.today {
    background: var(--color-accent-soft);
  }

  .day.over {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
  }

  .top {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .num {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-sm);
    background: none;
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
    text-align: left;
    cursor: pointer;
  }

  .now,
  .cook {
    padding: 1px var(--space-3);
    border-radius: var(--radius-full);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
  }

  .now {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .cook {
    margin-left: auto;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .chip {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    border-radius: var(--radius-sm);
    background: var(--soft, var(--color-ground));
    color: var(--soft-text, var(--color-text));
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    text-align: left;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
    min-width: 0;
  }

  .chip.solid {
    background: var(--solid);
    color: #fff;
  }

  .chip.can {
    touch-action: pan-y;
  }

  .chip-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .more {
    min-height: var(--touch-target);
    border: none;
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    text-align: left;
    cursor: pointer;
  }

  /* The three zones sit at the foot of the place, so the rest of it is a plain drop (a move, or
     a copy with Alt held). */
  .zones {
    position: absolute;
    inset: auto var(--space-2) var(--space-2) var(--space-2);
    z-index: 2;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-2);
    border: 2px solid var(--color-accent);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .zones span {
    flex: none;
    min-height: 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--space-3);
    border-radius: var(--radius-sm);
  }

  .zones span.on {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .zones.one {
    inset: var(--space-2);
  }

  .zones.one span {
    flex: 1;
    justify-content: center;
  }

  .zones small {
    font-weight: var(--weight-medium);
  }

  .side {
    flex: none;
    width: 240px;
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    overflow-y: auto;
  }

  .side section {
    padding: var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  h3 {
    margin-bottom: var(--space-4);
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .side ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .side li {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-md);
  }

  .dot {
    flex: none;
    width: 12px;
    height: 12px;
    border-radius: var(--radius-full);
  }

  .b-name {
    flex: 1;
    min-width: 0;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .b-when,
  .none {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .empty {
    flex-direction: row !important;
    flex-wrap: wrap;
  }

  .empty button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-full);
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .fill {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
