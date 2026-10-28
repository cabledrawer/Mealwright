<script lang="ts">
  // One meal's place in the week grid (mockup Desktop-Plan): the meal's things as little cards
  // ("Dosa · Fresh · 230 kcal"), "2 recipes · 590 kcal" and a + under them, or a dashed "+ Add"
  // when nothing is planned. Every card can be dragged by mouse or finger, and opened (a click,
  // Enter, or a held finger) for the menu that does everything a drag does.
  import type { MealSlot, PlanItem, PlanMeal } from '#lib/client/plan.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull } from '#lib/planDates.js';
  import { drag, pressable } from '#lib/planDrag.svelte.js';
  import {
    colourOfBatch,
    cookBatchOfItem,
    itemName,
    mealTotals,
    tubOf,
    whoseTub
  } from '#lib/planMeals.js';

  let { actions, day, slot }: { actions: PlanActions; day: string; slot: MealSlot } = $props();

  const model = $derived(actions.model);
  const meal = $derived(model.mealAt(day, slot.id));
  const over = $derived(drag.isOver(day, slot.id) ? drag.over : null);
  const can = $derived(actions.desktop && !actions.readonly);

  /** A tub: "Tub 2 of 4 · Wren". */
  function tubMeta(item: PlanItem): string {
    const found = tubOf(model.plan, item);
    if (!found) return 'Tub';
    const who = whoseTub(found.tub, model.people);
    return `Tub ${found.tub.number} of ${found.batch.tub_count}${who ? ` · ${who}` : ''}`;
  }

  /** The batch colour a card wears: light on a tub, solid on the day it was cooked. */
  function colourOf(m: PlanMeal, item: PlanItem): { n: number; solid: boolean } | null {
    const found = tubOf(model.plan, item);
    if (found) return { n: colourOfBatch(found.batch), solid: false };
    const cooked = cookBatchOfItem(model.plan, m, item);
    return cooked ? { n: colourOfBatch(cooked), solid: true } : null;
  }

  function meta(item: PlanItem): string {
    if (item.kind === 'tub') return tubMeta(item);
    const parts: string[] = [];
    if (item.recipe?.time_minutes) parts.push(`${item.recipe.time_minutes} min`);
    if (item.recipe?.kcal != null) parts.push(`${item.recipe.kcal} kcal`);
    return parts.join(' · ');
  }

  function cardFor(m: PlanMeal, item: PlanItem) {
    // One thing in the meal: the card is the meal. Several: each is itself.
    const whole = m.items.length === 1;
    return {
      carry: can ? () => (whole ? actions.carryMeal(m) : actions.carryItem(m, item)) : null,
      open: () => (whole ? actions.openMeal(m) : actions.openItem(m, item))
    };
  }

  const where = $derived(`${slot.name} on ${dayFull(day)}`);
</script>

<div
  class="cell"
  class:over={over !== null}
  data-drop-day={day}
  data-drop-slot={slot.id}
  data-testid="cell-{day}-{slot.id}"
>
  {#if meal}
    <div class="meal" class:one={meal.items.length === 1}>
      {#each meal.items as item (item.id)}
        {@const batch = colourOf(meal, item)}
        {@const cooked = batch?.solid ? cookBatchOfItem(model.plan, meal, item) : null}
        <button
          type="button"
          class="card"
          class:can
          class:tub={item.kind === 'tub'}
          class:batch={batch !== null}
          class:solid={batch?.solid}
          style:--soft={batch ? `var(--batch-${batch.n}-soft)` : undefined}
          style:--soft-text={batch ? `var(--batch-${batch.n}-soft-text)` : undefined}
          style:--solid={batch ? `var(--batch-${batch.n})` : undefined}
          disabled={actions.readonly}
          use:pressable={cardFor(meal, item)}
          aria-label="{itemName(item, model.plan)}, {where}. Open menu"
        >
          {#if item.recipe?.photo_url && meal.items.length === 1}
            <img class="photo" src={item.recipe.photo_url} alt="" loading="lazy" />
          {/if}
          <span class="name">{itemName(item, model.plan)}</span>
          {#if meta(item)}<span class="meta">{meta(item)}</span>{/if}
          {#if cooked}
            <span class="meta"
              >{cooked.prep_note ??
                `Cook once · ${cooked.tub_count} ${cooked.tub_count === 1 ? 'tub' : 'tubs'}`}</span
            >
          {/if}
        </button>
      {/each}
      <div class="foot">
        <button
          type="button"
          class="totals"
          class:can
          disabled={actions.readonly}
          use:pressable={{
            carry: can ? () => actions.carryMeal(meal) : null,
            open: () => actions.openMeal(meal)
          }}
          aria-label="{mealTotals(meal)}, {where}. Open menu">{mealTotals(meal)}</button
        >
        <button
          type="button"
          class="plus"
          disabled={actions.readonly}
          aria-label="Add to {where}"
          title="Add to this meal"
          onclick={() => actions.add(day, slot.id)}>+</button
        >
      </div>
    </div>
  {:else}
    <button
      type="button"
      class="add"
      disabled={actions.readonly}
      aria-label="Add to {where}"
      onclick={() => actions.add(day, slot.id)}>+ Add</button
    >
  {/if}

  {#if over && drag.carried}
    {#if drag.carried.zones}
      <div class="zones" aria-hidden="true">
        <span data-drop-zone="move" class:on={over.mode === 'move'}>Move</span>
        <span data-drop-zone="copy" class:on={over.mode === 'copy'}>Copy <small>Alt</small></span>
        {#if drag.carried.leftoversOk?.(day, slot.id) ?? true}
          <span data-drop-zone="leftovers" class:on={over.mode === 'leftovers'}>Leftovers here</span
          >
        {/if}
      </div>
    {:else}
      <div class="zones one" aria-hidden="true"><span class="on">Drop here</span></div>
    {/if}
  {/if}
</div>

<style>
  .cell {
    position: relative;
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    border-radius: var(--radius-lg);
  }

  .cell.over {
    outline: 2px solid var(--color-accent);
    outline-offset: 1px;
    background: var(--color-accent-soft);
  }

  .add {
    flex: 1;
    min-height: var(--touch-target);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .add:disabled,
  .plus:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .meal {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    min-width: 0;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-height: var(--touch-target);
    padding: var(--space-4) var(--space-5);
    border: none;
    border-radius: var(--radius-sm);
    background: var(--color-ground);
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
    overflow: hidden;
  }

  /* A finger can still scroll the page; it picks a card up only after a long press. */
  .card.can {
    touch-action: pan-y;
    cursor: grab;
  }

  .card.tub {
    background: var(--color-tub-chip);
    color: var(--color-tub-chip-text);
  }

  .photo {
    display: block;
    width: calc(100% + 2 * var(--space-5));
    height: 54px;
    margin: calc(-1 * var(--space-4)) calc(-1 * var(--space-5)) var(--space-2);
    object-fit: cover;
  }

  .name {
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .meta {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
  }

  .card.batch {
    background: var(--soft);
    color: var(--soft-text);
  }

  .card.solid {
    background: var(--solid);
    color: #fff;
  }

  .card.tub .meta,
  .card.batch .meta {
    color: inherit;
  }

  .foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    margin-top: auto;
  }

  .totals {
    min-height: var(--touch-target);
    padding: 0 var(--space-2);
    border: none;
    background: none;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
    text-align: left;
    cursor: pointer;
  }

  .totals.can {
    touch-action: pan-y;
  }

  .plus {
    flex: none;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font: inherit;
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
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
    border-radius: var(--radius-md);
    border: 2px solid var(--color-accent);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .zones span {
    flex: none;
    min-height: 22px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 var(--space-4);
    border-radius: var(--radius-sm);
  }

  .zones span.on {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .zones small {
    font-weight: var(--weight-medium);
    opacity: 0.8;
  }

  .zones.one {
    inset: var(--space-2);
  }

  .zones.one span {
    flex: 1;
    justify-content: center;
  }
</style>
