<script lang="ts">
  // Plan, Eat (mockups PlanEat07-Phone, Dark-PlanEat07-Phone): what each person eats at each meal
  // and where it comes from ("2 tubs from Thu · Tess, Wren"), a card for each day. A meal is
  // tapped (or held) for the same menu as everywhere on the Plan; a day with a cook has the link
  // "You cook today →" to the Cook view. Everything comes from the plan already on the page.
  import Icon from '#lib/components/Icon.svelte';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayWords } from '#lib/planDates.js';
  import { pressable } from '#lib/planDrag.svelte.js';
  import { eatDays } from '#lib/planEat.js';

  let {
    actions,
    days,
    oncook
  }: {
    actions: PlanActions;
    days: string[];
    /** The link "You cook today →": show the Cook view at that day. */
    oncook: (day: string) => void;
  } = $props();

  const model = $derived(actions.model);
  const shown = $derived(eatDays(model.plan, model.slotsOn, model.people, days));
</script>

<div class="eat">
  {#each shown as eat (eat.day)}
    {@const today = eat.day === model.today}
    <section
      class="day"
      class:today
      data-plan-day={eat.day}
      aria-label={dayFull(eat.day) + (today ? ', today' : '')}
    >
      <div class="head">
        <h3>{today ? `Today · ${dayWords(eat.day)}` : dayWords(eat.day)}</h3>
        {#if eat.cooks}
          <button type="button" class="cooklink" onclick={() => oncook(eat.day)}>
            <Icon name="pan" size={14} stroke={2.4} />{today
              ? 'You cook today →'
              : 'You cook this day →'}
          </button>
        {:else if eat.kcal !== null}
          <span class="kcal">{eat.kcal.toLocaleString('en-GB')} kcal each</span>
        {/if}
      </div>
      {#each eat.meals as { slot, meal, rows } (slot.id)}
        {#if meal && rows.length}
          <button
            type="button"
            class="meal"
            disabled={actions.readonly}
            use:pressable={{ carry: null, open: () => actions.openMeal(meal) }}
            aria-label="{slot.name}: {rows.map((r) => r.name).join(', ')}. Open menu"
          >
            <span class="slot">{slot.name}</span>
            <span class="dishes">
              {#each rows as row (row.key)}
                <span class="dish">
                  <span class="text">
                    <span class="name">{row.name}</span>
                    {#if row.source}
                      <span
                        class="source"
                        class:coloured={row.colour !== null}
                        style:--soft-text={row.colour === null
                          ? undefined
                          : `var(--batch-${row.colour}-soft-text)`}>{row.source}</span
                      >
                    {/if}
                  </span>
                  {#if row.fresh}
                    <span class="fresh">fresh</span>
                  {:else if row.colour !== null}
                    <span
                      class="dot"
                      class:solid={row.solid}
                      style:--solid={`var(--batch-${row.colour})`}
                      style:--soft={`var(--batch-${row.colour}-soft)`}
                      aria-hidden="true"
                    ></span>
                  {/if}
                </span>
              {/each}
            </span>
          </button>
        {:else}
          <button
            type="button"
            class="add"
            disabled={actions.readonly}
            onclick={() => actions.add(eat.day, slot.id)}>+ Add {slot.name.toLowerCase()}</button
          >
        {/if}
      {/each}
    </section>
  {/each}
</div>

<style>
  .eat {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 20rem), 1fr));
    gap: var(--space-6);
    align-items: start;
  }

  .day {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .day.today {
    outline: 2px solid var(--color-accent);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-2) var(--space-5);
  }

  h3 {
    margin: 0;
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .today h3 {
    color: var(--color-accent);
  }

  .kcal {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .cooklink {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-cook-on-soft);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .meal {
    display: flex;
    align-items: flex-start;
    gap: var(--space-5);
    min-height: var(--touch-target);
    padding: var(--space-3) 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
  }

  .meal:disabled {
    cursor: default;
  }

  /* In rem, so the label and the words beside it grow together with the text size. */
  .slot {
    flex: 0 0 5rem;
    padding-top: 0.2em;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .dishes {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .dish {
    display: flex;
    align-items: center;
    gap: var(--space-5);
  }

  .text {
    flex: 1;
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: break-word;
  }

  .source {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    overflow-wrap: break-word;
  }

  .source.coloured {
    color: var(--soft-text);
  }

  .fresh {
    flex: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .dot {
    flex: none;
    width: 10px;
    height: 10px;
    border-radius: 3px;
    border: 1px solid var(--solid);
    background: var(--soft);
  }

  .dot.solid {
    background: var(--solid);
  }

  .add {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text-muted);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    text-align: center;
    cursor: pointer;
  }

  .add:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
