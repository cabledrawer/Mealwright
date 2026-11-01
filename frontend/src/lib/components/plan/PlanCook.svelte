<script lang="ts">
  // Plan, Cook (mockups PlanCook07-Desktop, Dark-PlanCook07-Phone, Dark-PlanCook07-Desktop):
  // cooking by day. Fresh meals and batches, how much (× scale, makes N, eat N now, where each
  // tub goes, spare tubs), prep ahead, what is still to buy, and Start cooking, which opens Cook
  // mode for that plan item so "Cooked it" is there at the end.
  import Icon from '#lib/components/Icon.svelte';
  import { getRecipeStock } from '#lib/client/recipes.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { cookDays, stillToBuy, type CookEntry } from '#lib/planCook.js';
  import { colourOfBatch } from '#lib/planMeals.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayWords } from '#lib/planDates.js';
  import { timeWords } from '#lib/timeWords.js';
  import { untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';

  let {
    actions,
    days,
    onstart
  }: {
    actions: PlanActions;
    days: string[];
    /** Start cooking: Cook mode for this recipe in this meal. */
    onstart: (entry: CookEntry) => void;
  } = $props();

  const model = $derived(actions.model);
  const shown = $derived(cookDays(model.plan, model.slotsOn, days, model.slots));
  /** Every day of the week on show, for the summary beside the days. */
  const week = $derived(cookDays(model.plan, model.slotsOn, model.days, model.slots));

  // --- Still to buy: the recipe's stock check, asked once for each recipe on show ------------

  let toBuy = $state<Record<string, string[]>>({});
  const asked = new SvelteSet<string>();
  const stockKey = (entry: CookEntry) => `${entry.recipeId}:${servingsOf(entry) ?? ''}`;
  /** How many the stock is asked for: a batch's portions, else who it is for. */
  const servingsOf = (entry: CookEntry) => entry.makes ?? entry.serves;

  $effect(() => {
    void kitchen.version;
    untrack(() => {
      asked.clear();
      toBuy = {};
    });
  });

  $effect(() => {
    const entries = shown.flatMap((d) => d.entries).filter((e) => e.recipeId !== null && !e.cooked);
    if (network.offline) return;
    untrack(() => {
      for (const entry of entries) {
        const key = stockKey(entry);
        if (asked.has(key)) continue;
        asked.add(key);
        getRecipeStock(entry.recipeId!, servingsOf(entry))
          .then((stock) => (toBuy[key] = stillToBuy(stock)))
          .catch(() => asked.delete(key)); // a failed ask leaves the line out; asked again later
      }
    });
  });

  const buyLine = (entry: CookEntry) => {
    const names = toBuy[stockKey(entry)];
    return names?.length ? `Still to buy: ${names.join(', ')}` : null;
  };

  const things = (n: number) => (n === 1 ? '1 thing to cook' : `${n} things to cook`);

  // --- The week at a glance, beside the days ------------------------------------------------

  const batches = $derived(week.flatMap((d) => d.entries).filter((e) => e.batch));
  const fresh = $derived(week.flatMap((d) => d.entries).filter((e) => !e.batch));
  const portions = $derived(batches.reduce((sum, e) => sum + (e.makes ?? 0), 0));
  const stove = $derived(
    week.flatMap((d) => (d.minutes === null ? [] : [d.minutes])).reduce((a, b) => a + b, 0)
  );
</script>

<div class="cook">
  <div class="days">
    {#each shown as cook (cook.day)}
      {@const today = cook.day === model.today}
      <section class="day" class:today id="cook-{cook.day}" aria-label={dayFull(cook.day)}>
        <div class="head">
          <h3>{today ? `Today · ${dayWords(cook.day)}` : dayWords(cook.day)}</h3>
          <span class="total"
            >{things(cook.entries.length)}{cook.minutes === null
              ? ''
              : ` · ${timeWords(cook.minutes)}`}</span
          >
        </div>
        {#each cook.entries as entry (entry.key)}
          <div class="entry" class:batch={entry.batch !== null}>
            <div class="top">
              <span class="icon" aria-hidden="true"><Icon name="pan" size={18} stroke={2.2} /></span
              >
              <span class="what">
                <span class="tag">{entry.batch ? 'Cook · Batch' : 'Fresh'} · {entry.slotName}</span>
                <span class="name">
                  {entry.name}
                  {#if entry.batch}
                    <!-- The batch's own colour: it links this cook to its tubs on the other views. -->
                    <i
                      class="dot"
                      style:background={`var(--batch-${colourOfBatch(entry.batch)})`}
                      aria-hidden="true"
                    ></i>
                  {/if}
                </span>
                <span class="sub">
                  {#if entry.batch}
                    Makes {entry.makes}{entry.scale ? ` · cook × ${entry.scale}` : ''}{entry.minutes
                      ? ` · ${timeWords(entry.minutes)}`
                      : ''}
                  {:else}
                    {[
                      entry.serves ? `Serves ${entry.serves}` : null,
                      entry.minutes ? timeWords(entry.minutes) : null
                    ]
                      .filter((part) => part)
                      .join(' · ')}
                  {/if}
                </span>
              </span>
              {#if entry.cooked}
                <span class="done">Cooked</span>
              {:else if entry.recipeId !== null}
                <button
                  type="button"
                  class="start"
                  class:primary={today}
                  aria-label="Start cooking {entry.name}"
                  disabled={actions.readonly}
                  onclick={() => onstart(entry)}
                >
                  <Icon name="play" size={16} stroke={2} />
                  <span>Start cooking</span>
                </button>
              {/if}
            </div>
            {#if entry.batch}
              <div class="chips">
                {#if entry.eatNow > 0}<span class="chip">Eat {entry.eatNow} now</span>{/if}
                {#each entry.tubs as place, i (i)}<span class="chip">Tub → {place}</span>{/each}
                {#if entry.spare > 0}
                  <button
                    type="button"
                    class="chip spare"
                    disabled={actions.readonly}
                    onclick={() => actions.openItem(entry.meal, entry.item)}
                    >+ {entry.spare} spare {entry.spare === 1 ? 'tub' : 'tubs'}</button
                  >
                {/if}
              </div>
            {/if}
            {#if entry.prep}
              <p class="line"><b>Prep ahead:</b> {entry.prep}</p>
            {/if}
            {#if buyLine(entry)}
              <p class="line">{buyLine(entry)}</p>
            {/if}
          </div>
        {/each}
      </section>
    {:else}
      <p class="empty">Nothing to cook in these days.</p>
    {/each}
  </div>

  {#if week.length}
    <aside class="week" aria-label="This week’s cooking">
      <h3>This week’s cooking</h3>
      <dl>
        <div>
          <dt>{batches.length === 1 ? 'batch' : 'batches'}</dt>
          <dd>{batches.length}{portions ? ` · ${portions} portions` : ''}</dd>
        </div>
        <div>
          <dt>fresh {fresh.length === 1 ? 'meal' : 'meals'}</dt>
          <dd>{fresh.length}</dd>
        </div>
        {#if stove > 0}
          <div>
            <dt>at the stove</dt>
            <dd>{timeWords(stove)}</dd>
          </div>
        {/if}
      </dl>
    </aside>
  {/if}
</div>

<style>
  .cook {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: var(--space-7);
    align-items: start;
  }

  /* Beside the days only where there is room; under them on a phone and a narrow window. */
  @media (min-width: 1100px) {
    .cook {
      grid-template-columns: minmax(0, 1fr) 17rem;
    }
  }

  .days {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
  }

  .day {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
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

  .total {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .entry {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
    padding: var(--space-6);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
  }

  .entry.batch {
    border-color: transparent;
    background: var(--color-cook-soft);
  }

  .top {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-6);
  }

  .icon {
    flex: none;
    display: grid;
    place-items: center;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-md);
    background: var(--color-cook-soft);
    color: var(--color-cook-on-soft);
  }

  .entry.batch .icon {
    background: var(--color-cook);
    color: var(--color-cook-text);
  }

  .what {
    flex: 1 1 10rem;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .tag {
    color: var(--color-cook-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: break-word;
  }

  .entry.batch .name {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
  }

  .dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    margin-left: var(--space-2);
    border-radius: 5px;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    overflow-wrap: break-word;
  }

  .start {
    flex: none;
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .start.primary,
  .entry.batch .start {
    border-color: var(--color-cook);
    background: var(--color-cook);
    color: var(--color-cook-text);
  }

  .start:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .done {
    flex: none;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    padding: var(--space-2) var(--space-5);
    border: 1px solid transparent;
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .chip.spare {
    min-height: var(--touch-target);
    border: 1px dashed var(--color-cook-on-soft);
    background: transparent;
    color: var(--color-cook-on-soft);
    cursor: pointer;
  }

  .chip.spare:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .line {
    margin: 0;
    color: var(--color-text);
    font-size: var(--text-md);
    overflow-wrap: break-word;
  }

  .empty {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .week {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    min-width: 0;
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .week h3 {
    font-size: var(--text-lg);
  }

  dl {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
  }

  dl div {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: var(--space-2) var(--space-5);
  }

  dt {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  dd {
    margin: 0;
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
  }
</style>
