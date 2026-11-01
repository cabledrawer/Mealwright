<script lang="ts">
  // "Leftovers on…" (0.7 P1; mockup Leftovers07-Phone; cabledrawer 28 Oct): tick several meals at
  // once, see the portions left, and when there are none left choose Cook more (a bigger batch;
  // amounts and the shopping list follow) or Add anyway (the meal is planned; the batch stays the
  // same). Only meals after the cook and before the use-by are listed. Words marked "proposed,
  // for cabledrawer" are in docs/dev/words.md section 28.
  import { onMount } from 'svelte';
  import {
    getPlan,
    getPortions,
    type Plan,
    type PlanItem,
    type PlanMeal,
    type Portions,
    type WhenNoneLeft
  } from '#lib/client/plan.js';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayWords } from '#lib/planDates.js';
  import { itemName } from '#lib/planMeals.js';
  import {
    barLabel,
    leftoverRows,
    offeredDays,
    planWords,
    portionBar,
    portionsLine,
    rowKey,
    shortRows
  } from '#lib/portions.js';

  let {
    actions,
    meal,
    item,
    onback,
    onclose
  }: {
    actions: PlanActions;
    /** The meal the recipe is cooked in. */
    meal: PlanMeal;
    item: PlanItem;
    onback: () => void;
    onclose: () => void;
  } = $props();

  const model = $derived(actions.model);
  let portions = $state<Portions | null>(null);
  let range = $state<Plan | null>(null);
  let problem = $state<string | null>(null);
  let picked = $state<string[]>([]);
  /** What to do for the meals the portions left don't reach; chosen from the alert. */
  let choice = $state<Exclude<WhenNoneLeft, 'ask'> | null>(null);
  let sending = $state(false);

  async function load(): Promise<void> {
    try {
      const found = await getPortions(item.id);
      const { first, last } = offeredDays(meal.date, model.today, found.use_by);
      range = await getPlan(first, last);
      portions = found;
      problem = null;
    } catch (error) {
      problem = cantReach(error) ? cantReachWords() : 'Couldn’t load the leftovers. Try again.';
    }
  }
  onMount(() => void load());

  const name = $derived(itemName(item, model.plan));
  const rows = $derived(
    portions
      ? leftoverRows({
          cook: meal,
          today: model.today,
          useBy: portions.use_by,
          slotsOn: model.slotsOn,
          plan: range,
          batchId: portions.batch_id
        })
      : []
  );
  const chosen = $derived(new Set(picked));
  const left = $derived(portions?.has_batch ? (portions.left ?? 0) : picked.length);
  const short = $derived(portions?.has_batch ? shortRows(rows, chosen, left) : []);
  const ready = $derived(
    picked.length > 0 && (short.length === 0 || choice !== null) && !actions.readonly && !sending
  );

  /** The ticked and already-planned rows that are tubs, in date order: a tub's number is its place. */
  const tubbed = $derived(
    rows.filter(
      (r) =>
        r.state === 'planned' ||
        (chosen.has(rowKey(r)) && !short.some((s) => rowKey(s) === rowKey(r)))
    )
  );

  function tick(key: string): void {
    picked = chosen.has(key) ? picked.filter((k) => k !== key) : [...picked, key];
    if (short.length === 0) choice = null;
  }

  $effect(() => {
    // Un-ticking until nothing is short clears the choice, so it is asked again if needed.
    if (short.length === 0 && choice !== null) choice = null;
  });

  const cookDay = $derived(dayWords(meal.date));
  const cookSlot = $derived(model.slotName(meal.slot_id).toLowerCase());
  const keeps = $derived(portions ? `keeps in the fridge until ${dayWords(portions.use_by)}` : '');

  const alertWords = $derived.by(() => {
    if (!short.length) return '';
    const first = short[0]!;
    return short.length === 1
      ? `No portions left for ${dayWords(first.day)} ${model.slotName(first.slotId).toLowerCase()}.`
      : `No portions left for ${short.length} of these meals.`;
  });

  async function plan(): Promise<void> {
    if (!ready || !portions) return;
    const spots = rows
      .filter((r) => chosen.has(rowKey(r)))
      .map((r) => ({ date: r.day, slot_id: r.slotId }));
    sending = true;
    const outcome = await model.leftoversOn(item, spots, short.length ? (choice ?? 'ask') : 'ask');
    sending = false;
    if (outcome.ok) {
      onclose();
    } else if (outcome.error instanceof ApiError && outcome.error.code === 'no_portions_left') {
      // Someone else took the last portion: ask again with the new numbers.
      choice = null;
      await load();
    }
  }
</script>

<div class="leftovers">
  <header>
    <p class="sub">Cooked {cookDay} · {cookSlot}{keeps ? ` · ${keeps}` : ''}</p>
    <h3>Leftovers of {name}</h3>
  </header>

  {#if problem}
    <p class="note problem" role="alert">{problem}</p>
    <button type="button" class="back" onclick={load}>Try again</button>
  {:else if !portions}
    <p class="note" role="status">Loading the leftovers…</p>
  {:else}
    {#if portions.has_batch}
      <div class="bar-wrap">
        <div class="bar" role="img" aria-label={barLabel(portions)}>
          {#each portionBar(portions, picked.length) as part, i (i)}
            <span class={part}></span>
          {/each}
        </div>
        <p class="line">
          {#if short.length}
            {@const words = portionsLine(
              portions,
              picked.length,
              dayWords(meal.date).split(' ')[0]!
            )}
            {words.slice(0, words.lastIndexOf('·') + 2)}<b class="short"
              >{words.slice(words.lastIndexOf('·') + 2)}</b
            >
          {:else}
            {portionsLine(portions, picked.length, dayWords(meal.date).split(' ')[0]!)}
          {/if}
        </p>
      </div>
    {/if}

    <ul class="meals" aria-label="Meals">
      {#each rows as row (rowKey(row))}
        {@const key = rowKey(row)}
        {@const on = chosen.has(key)}
        {@const over = short.some((s) => rowKey(s) === key)}
        {@const planned = row.state === 'planned'}
        <li>
          <label class:planned class:on={on && !over} class:over>
            <input
              type="checkbox"
              checked={planned || on}
              disabled={planned || actions.readonly}
              onchange={() => tick(key)}
            />
            <span class="what"
              >{dayWords(row.day)} · {model.slotName(
                row.slotId
              )}{#if row.state === 'has' && row.what}<small>{row.what}</small>{/if}</span
            >
            <span class="tag">
              {#if planned}
                planned
              {:else if over}
                {choice === 'cook_more'
                  ? 'new tub'
                  : choice === 'add_anyway'
                    ? 'recipe for 1'
                    : 'no portion left'}
              {:else if on}
                tub {tubbed.findIndex((r) => rowKey(r) === key) + 1}
              {:else if row.last}
                last day
              {/if}
            </span>
          </label>
        </li>
      {/each}
    </ul>
    <p class="hint">
      Only meals after the cook and before the use-by are shown. To keep it longer, send a tub to
      the freezer.
    </p>

    {#if short.length}
      <div class="shortage" role="alert">
        <p>{alertWords}</p>
        <div class="choices">
          <button
            type="button"
            class="more"
            aria-pressed={choice === 'cook_more'}
            disabled={actions.readonly}
            onclick={() => (choice = 'cook_more')}
          >
            <span class="top"
              ><svg
                aria-hidden="true"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.4"
                stroke-linecap="round"
                stroke-linejoin="round"
                ><path d="M4 11h13v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z" /><path d="M17 13h3" /></svg
              >Cook more</span
            >
            <small>Makes {(portions.portions ?? 0) + short.length} · list updates</small>
          </button>
          <button
            type="button"
            class="anyway"
            aria-pressed={choice === 'add_anyway'}
            disabled={actions.readonly}
            onclick={() => (choice = 'add_anyway')}
          >
            Add anyway
            <small
              >{short.length === 1 ? 'Plans it' : 'Plans them'}; the batch stays at {portions.portions}</small
            >
          </button>
        </div>
      </div>
    {/if}
  {/if}

  <div class="buttons">
    <button type="button" class="back" onclick={onback}>Back</button>
    <button type="button" class="go" disabled={!ready} onclick={plan}
      >{planWords(picked.length || 0)}</button
    >
  </div>
</div>

<style>
  .leftovers {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    text-align: left;
  }

  .sub {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  h3 {
    margin: 0;
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .note {
    margin: 0;
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-base);
  }

  .note.problem {
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .bar-wrap {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .bar {
    display: flex;
    gap: 4px;
  }

  .bar span {
    flex: 1;
    height: 10px;
    border-radius: 5px;
    background: var(--color-border-strong);
  }

  .bar .cook {
    background: var(--color-accent-hover);
  }

  .bar .planned {
    background: var(--color-accent);
    opacity: 0.6;
  }

  .bar .picked {
    background: var(--color-on-list-dot);
  }

  .bar .over {
    border: 1px dashed var(--color-check-border);
    background: repeating-linear-gradient(
      45deg,
      var(--color-tub-chip),
      var(--color-tub-chip) 4px,
      var(--color-surface) 4px,
      var(--color-surface) 8px
    );
  }

  .line {
    margin: 0;
    color: var(--color-text-soft);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .short {
    color: var(--color-tub-chip-text);
  }

  .meals {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  label {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3) var(--space-6);
    min-height: var(--touch-target);
    padding: var(--space-2) var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    font-size: var(--text-base);
    cursor: pointer;
  }

  label.planned {
    border-color: transparent;
    background: var(--color-fill);
    color: var(--color-text-muted);
    cursor: default;
  }

  label.on {
    border: 2px solid var(--color-accent-hover);
    font-weight: var(--weight-bold);
  }

  label.over {
    border: 2px solid var(--color-check-border);
    font-weight: var(--weight-bold);
  }

  input[type='checkbox'] {
    width: 20px;
    height: 20px;
    margin: 0;
    accent-color: var(--color-accent-hover);
  }

  .what {
    flex: 1 1 8rem;
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .what small {
    display: block;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  .tag {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  label.on .tag {
    color: var(--color-accent-hover);
    font-weight: var(--weight-bold);
  }

  label.over .tag {
    color: var(--color-tub-chip-text);
    font-weight: var(--weight-bold);
  }

  .hint {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .shortage {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-tub-chip);
    color: var(--color-tub-chip-text);
  }

  .shortage p {
    margin: 0;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .choices {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
    gap: var(--space-3);
  }

  .choices button {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    min-height: 64px;
    padding: var(--space-3);
    border-radius: 14px;
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
    cursor: pointer;
    text-align: center;
  }

  .choices small {
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .choices .top {
    display: inline-flex;
    align-items: center;
    gap: 5px;
  }

  .more {
    border: 2px solid var(--batch-4);
    background: var(--batch-4);
    color: var(--color-batch-on);
  }

  .anyway {
    border: 2px solid var(--color-check-border);
    background: var(--color-surface);
    color: var(--color-tub-chip-text);
  }

  .choices button[aria-pressed='true'] {
    outline: 3px solid var(--color-focus);
    outline-offset: 2px;
  }

  .buttons {
    display: flex;
    gap: var(--space-4);
  }

  .back,
  .go {
    min-height: 54px;
    border: none;
    border-radius: var(--radius-button);
    font: inherit;
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .back {
    padding: 0 var(--space-8);
    background: var(--color-fill-strong);
    color: var(--color-text);
  }

  .go {
    flex: 1;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
