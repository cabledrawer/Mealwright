<script lang="ts">
  // The month on a computer or iPad (mockup Month07-Desktop): whole weeks of day cells that share
  // the height, so the month fits one screen (F47), each with up to three chips (the cooking
  // first, then "+N more"), a COOK tag on cook days, one colour per batch, and a side panel with
  // "Batches this month" and "Empty days ahead". A click anywhere in a day opens it (F53). A chip
  // drags to another day (it keeps its meal, so a dinner stays a dinner); Alt copies; the
  // Leftovers zone plans leftovers. There is no recipe tray here: the day's own sheet offers the
  // recipes and the tubs left.
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayOfMonth, dayShort, monthWords } from '#lib/planDates.js';
  import { drag, pressable } from '#lib/planDrag.svelte.js';
  import { colourOfBatch, cookBatchOfItem, cookedOn, itemName, tubOf } from '#lib/planMeals.js';
  import { chipsThatFit } from '#lib/planMonthFit.js';
  import type { PlanBatch, PlanItem, PlanMeal } from '#lib/client/plan.js';

  let { actions }: { actions: PlanActions } = $props();
  const model = $derived(actions.model);
  const can = $derived(actions.desktop && !actions.readonly);

  // The month fits one screen (F47): the days share the height, and a short day shows fewer than
  // three things (the rest are "+N more"), so nothing is cut off.
  let cellsHeight = $state(0);
  let scale = $state(1);
  $effect(() => {
    void cellsHeight; // measured again whenever the text size or the window changes
    scale = parseFloat(getComputedStyle(document.documentElement).fontSize) / 16 || 1;
  });
  const dayHeight = $derived.by(() => {
    const rows = model.days.length / 7;
    return rows > 0 && cellsHeight > 0 ? (cellsHeight - (rows - 1) * 3 * scale) / rows : 0;
  });

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
    <div class="cells" style:--rows={model.days.length / 7} bind:clientHeight={cellsHeight}>
      {#each model.days as day (day)}
        {@const chips = chipsOn(day)}
        {@const shown = chipsThatFit(dayHeight, chips.length, scale)}
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
          <!-- The whole day is one button (F53); the number, the tags and the chips sit above it. -->
          <button
            type="button"
            class="hit"
            disabled={actions.readonly}
            aria-label="Add to {dayFull(day)}"
            onclick={() => actions.add(day, null)}
          ></button>
          <div class="top">
            <span class="num">{dayOfMonth(day)}</span>
            {#if day === model.today}<span class="now">Today</span>{/if}
            {#if cookedOn(model.plan, day).length}
              <span class="cook" title="Cook day">COOK</span>
            {/if}
          </div>
          {#each chips.slice(0, shown) as chip (chip.item.id)}
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
          {#if chips.length > shown}
            <button type="button" class="more" onclick={() => actions.openDay(day)}
              >+{chips.length - shown} more</button
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
    gap: var(--space-2);
    padding: var(--space-5);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .head,
  .cells {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: 3px;
  }

  .head span {
    padding: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
  }

  /* The weeks share the height (F47): the month fits one screen, whether it has five weeks or six. */
  .cells {
    flex: 1;
    min-height: 0;
    grid-template-rows: repeat(var(--rows), minmax(0, 1fr));
  }

  .day {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    min-height: 0;
    padding: 4px;
    overflow: hidden;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
  }

  /* The day itself is a button, so a click anywhere in it opens it (F53). */
  .hit {
    position: absolute;
    inset: 0;
    border: none;
    border-radius: inherit;
    background: none;
    cursor: pointer;
  }

  .hit:hover:not(:disabled) {
    background: var(--color-accent-soft);
  }

  .day > :not(.hit, .zones) {
    position: relative;
    pointer-events: none;
  }

  .day .chip,
  .day .more {
    pointer-events: auto;
  }

  /* Days of the next or last month: quieter, but still readable. */
  .day.out .num {
    color: var(--color-text-muted);
  }

  .day.today {
    background: var(--color-accent-soft);
  }

  .day.over {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
  }

  /* The number and its tags (Today, COOK) wrap onto a second line in a narrow day, so none of
     them reaches into the next day (F84). */
  .top {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 var(--space-2);
    min-width: 0;
    min-height: 18px;
  }

  .num {
    padding: 0 var(--space-2);
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
    line-height: 18px;
  }

  .now,
  .cook {
    padding: 0 var(--space-3);
    border-radius: var(--radius-full);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    line-height: 16px;
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

  /* A chip is small (the mockup's 24 px, 18 here to fit six weeks); the whole day is the target. */
  .chip {
    flex: none;
    display: flex;
    align-items: center;
    height: 18px;
    padding: 0 var(--space-3);
    border: none;
    border-radius: var(--radius-sm);
    background: var(--soft, var(--color-ground));
    color: var(--soft-text, var(--color-text));
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    line-height: 14px;
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
    flex: none;
    height: 15px;
    padding: 0 var(--space-2);
    border: none;
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    line-height: 15px;
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
