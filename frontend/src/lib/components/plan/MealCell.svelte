<script lang="ts">
  // One meal's place in the week grid (mockup Desktop-Plan): the meal's things as little cards
  // ("Dosa · Fresh · 230 kcal"), "2 recipes · 590 kcal" and a + under them, or a dashed "+ Add"
  // when nothing is planned. Every card can be dragged by mouse or finger, and opened (a click,
  // Enter, or a held finger) for the menu that does everything a drag does.
  import Icon from '#lib/components/Icon.svelte';
  import type { MealSlot, PlanItem, PlanMeal } from '#lib/client/plan.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull } from '#lib/planDates.js';
  import { drag, pressable } from '#lib/planDrag.svelte.js';
  import { weekCards } from '#lib/planCards.js';
  import { mealTotals } from '#lib/planMeals.js';

  let { actions, day, slot }: { actions: PlanActions; day: string; slot: MealSlot } = $props();

  const model = $derived(actions.model);
  const meal = $derived(model.mealAt(day, slot.id));
  const over = $derived(drag.isOver(day, slot.id) ? drag.over : null);
  const can = $derived(actions.desktop && !actions.readonly);

  function cardFor(m: PlanMeal, item: PlanItem, cook: boolean) {
    // One thing in the meal: the card is the meal. Several: each is itself.
    const whole = m.items.length === 1;
    return {
      carry: can
        ? () =>
            cook ? actions.carryCook(m) : whole ? actions.carryMeal(m) : actions.carryItem(m, item)
        : null,
      open: () => (whole ? actions.openMeal(m) : actions.openItem(m, item))
    };
  }

  const cards = $derived(meal ? weekCards(model.plan!, meal, model.people, model.slotsOn) : []);
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
      {#each cards as card (card.key)}
        {@const item = card.item}
        {@const solo = meal.items.length === 1 && card.role === 'fresh'}
        <button
          type="button"
          class="card {card.role}"
          class:can
          class:before={card.before}
          style:--soft={card.colour ? `var(--batch-${card.colour}-soft)` : undefined}
          style:--soft-text={card.colour ? `var(--batch-${card.colour}-soft-text)` : undefined}
          style:--dot={card.colour ? `var(--batch-${card.colour})` : undefined}
          disabled={actions.readonly}
          use:pressable={cardFor(meal, item, card.role === 'cook')}
          data-item={item.id}
          aria-label="{card.name}{card.role === 'cook'
            ? ' (cooking)'
            : card.role === 'eat' && !card.item.tub_id
              ? ' (eating)'
              : ''}, {where}{card.before ? ', before the cook day' : ''}. Open menu"
        >
          {#if item.recipe?.photo_url && solo}
            <img
              class="photo"
              src={item.recipe.photo_url}
              alt=""
              loading="lazy"
              draggable="false"
            />
          {/if}
          {#if card.eyebrow}
            <span class="eyebrow"
              ><Icon
                name={card.role === 'cook' ? 'pan' : 'plate'}
                size={13}
                stroke={2.4}
              />{card.eyebrow}</span
            >
          {/if}
          <span class="name">{card.shown}</span>
          {#if card.role === 'cook'}
            <span class="meta"><i class="dot" aria-hidden="true"></i>{card.meta}</span>
            {#if card.prep}<span class="meta">{card.prep}</span>{/if}
          {:else if card.meta}
            <span class="meta"
              >{#if card.role === 'fresh'}<Icon name="pan" size={13} stroke={2.4} />Fresh ·
              {/if}{card.meta}</span
            >
          {:else if card.role === 'fresh'}
            <span class="meta"><Icon name="pan" size={13} stroke={2.4} />Fresh</span>
          {/if}
          {#if card.who.length}
            <span class="who"
              >{#each card.who as person (person)}<span>{person}</span>{/each}</span
            >
          {/if}
          {#if card.before}<span class="early">Before the cook day</span>{/if}
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
          onclick={() => actions.add(day, slot.id)}
          ><Icon name="plus" size={20} stroke={2.6} /></button
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
    width: 100%;
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
    gap: var(--space-2);
    min-height: var(--touch-target);
    padding: var(--space-5) var(--space-6);
    border: 1px solid transparent;
    border-radius: var(--radius-md);
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

  .card.fresh,
  .card.plain {
    border-color: var(--color-border-strong);
    background: var(--color-surface);
  }

  /* COOK is blue, with a pan; the dot is the batch's colour, which its tubs wear. */
  .card.cook {
    background: var(--color-cook);
    color: var(--color-cook-text);
  }

  .card.eat {
    background: var(--soft);
    color: var(--soft-text);
  }

  .card.before {
    outline: 2px solid var(--batch-2);
    outline-offset: 1px;
  }

  .photo {
    pointer-events: none;
    -webkit-user-drag: none;
    display: block;
    width: calc(100% + 2 * var(--space-6));
    height: 54px;
    margin: calc(-1 * var(--space-5)) calc(-1 * var(--space-6)) var(--space-2);
    object-fit: cover;
  }

  .eyebrow {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .name {
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .meta {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-medium);
  }

  .card.cook .meta,
  .card.eat .meta {
    color: inherit;
  }

  .dot {
    flex: none;
    width: 10px;
    height: 10px;
    border-radius: var(--radius-full);
    background: var(--dot);
  }

  .who {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .who span {
    padding: 2px var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
  }

  .early {
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
  }

  .foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
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
    display: grid;
    place-items: center;
    padding: 0;
    cursor: pointer;
  }

  /* The three zones hang just below the place (cells are only as tall as their content, so the
     zones would cover all of a small one), and the whole place is a plain drop (a move, or a copy
     with Alt held). */
  .zones {
    position: absolute;
    inset: 100% var(--space-2) auto var(--space-2);
    margin-top: var(--space-2);
    box-shadow: 0 12px 28px rgb(23 32 28 / 0.2);
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
    margin: 0;
    box-shadow: none;
  }

  .zones.one span {
    flex: 1;
    justify-content: center;
  }
</style>
