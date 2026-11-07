<script lang="ts">
  // Stocktake (F118, 0.8; mockup Dark-Stocktake08-Phone): go through the home place by place,
  // and say how much of each ingredient there is: None · ¼ · ½ · ¾ · Full (or a count with
  // − / +, or "It's a staple"). The pack size is asked once. Every answer is saved as it is
  // tapped, with Undo in the toast; the server keeps the progress for the household, so
  // "Stop, carry on later" is only leaving, and Stocktake reopens at the first place not
  // finished, from any phone.
  import { onMount, untrack } from 'svelte';
  import { resolve } from '$app/paths';
  import FoodPicker from '#lib/components/FoodPicker.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import {
    countOf,
    countWords,
    fractionOf,
    moreOf,
    shareOf,
    StocktakeModel
  } from '#lib/stocktake.svelte.js';
  import type { StocktakeRow } from '#lib/client/stocktake.js';
  import type { PackSuggestion, Ref } from '#lib/client/types.js';
  import { live } from '#lib/live.svelte.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import { chipWords } from '#lib/restockWords.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import { blockedWhileDown } from '#lib/serverNeeded.js';

  const model = new StocktakeModel();

  const PICKS: readonly { value: number; label: string; aria: string }[] = [
    { value: 0, label: 'None', aria: 'None' },
    { value: 0.25, label: '¼', aria: '¼ left' },
    { value: 0.5, label: '½', aria: '½ left' },
    { value: 0.75, label: '¾', aria: '¾ left' },
    { value: 1, label: 'Full', aria: 'Full' }
  ];

  onMount(() => void model.open());

  // Another phone answered or finished a place: fetch again.
  let firstLive = true;
  $effect(() => {
    void live.pantry;
    if (firstLive) {
      firstLive = false;
      return;
    }
    untrack(() => void model.reload());
  });

  const place = $derived(model.place);
  const overview = $derived(model.overview);
  const done = $derived(overview?.complete ?? false);

  /** "bag · 1 kg": the way it is sold, from "Bag = 1 kg". */
  const packWords = (row: StocktakeRow) =>
    row.pack ? `${row.pack.name} · ${row.pack.display.split(' = ')[1] ?? ''}` : '';

  /** "A staple: not counted. Restocked 3 Nov." */
  const stapleWords = (row: StocktakeRow) =>
    row.restocked_on && row.restocked_days_ago !== null
      ? `A staple: not counted. ${chipWords(row.restocked_on, row.restocked_days_ago)}.`
      : 'A staple: not counted.';

  const counted = (row: StocktakeRow) => row.food.counted_as === 'count';

  function meta(row: StocktakeRow): string {
    if (row.staple) return 'staple';
    if (counted(row)) return 'counted';
    return row.pack ? packWords(row) : 'no pack size yet';
  }

  /** What the − / + shows: the answer, else what is there now. */
  const countNow = (row: StocktakeRow) => countOf(row) ?? row.stock.amount;

  // --- Typing a pack size ("Other…") ---------------------------------------------------------

  let otherFor = $state<number | null>(null);
  let otherAmount = $state('');
  let otherUnit = $state('g');

  function openOther(row: StocktakeRow) {
    otherFor = row.food.id;
    otherAmount = '';
    otherUnit = row.food.counted_as === 'volume' ? 'ml' : 'g';
  }

  function sendOther(row: StocktakeRow) {
    const amount = Number(otherAmount);
    if (!(amount > 0)) return;
    otherFor = null;
    void model.size(row.food.id, row.food.name, {
      name: 'pack',
      amount: { amount, unit: otherUnit }
    });
  }

  function pickSize(row: StocktakeRow, choice: PackSuggestion) {
    if (blockedWhileDown()) return;
    void model.size(
      row.food.id,
      row.food.name,
      { name: choice.name, amount: choice.amount },
      choice
    );
  }

  // --- Something else ------------------------------------------------------------------------

  let adding = $state(false);

  async function pickedFood(food: Ref) {
    adding = false;
    await model.addHere(food.id);
  }

  async function createdFood(name: string) {
    const made = await newIngredient.ask(name);
    adding = false;
    if (made) await model.addHere(made.id);
  }

  // --- Moving on -----------------------------------------------------------------------------

  async function next() {
    if (blockedWhileDown()) return;
    if (await model.next()) window.scrollTo({ top: 0 });
  }

  async function back(id: number) {
    if (await model.goTo(id)) window.scrollTo({ top: 0 });
  }

  async function again() {
    if (blockedWhileDown()) return;
    await model.restart();
  }
</script>

<svelte:head>
  <title>Stocktake · Mealwright</title>
</svelte:head>

{#if model.loading}
  <PageHeader title="Stocktake" />
  <p class="note">Loading…</p>
{:else if model.failed || !overview}
  <PageHeader title="Stocktake" />
  <div class="card">
    <p>Couldn’t open the stocktake. Try again.</p>
    <button type="button" class="strong" onclick={() => void model.open()}>Try again</button>
  </div>
{:else if done}
  <PageHeader title="Stocktake" />
  <div class="card done">
    <h2>Stocktake finished</h2>
    <p>Every place is counted. The pantry shows what you said.</p>
    <a class="strong" href={resolve('/(app)/pantry')}>Back to Pantry</a>
    <button type="button" class="quiet" onclick={() => void again()}>Start a new stocktake</button>
  </div>
{:else if place}
  <header class="top">
    <div class="bar">
      <a class="stop" href={resolve('/(app)/pantry')}>Stop, carry on later</a>
      <span class="count">Place {place.number} of {place.of}</span>
    </div>
    <h1>Stocktake · {place.place.name}</h1>
    <div
      class="progress"
      role="progressbar"
      aria-label="Place {place.number} of {place.of}"
      aria-valuemin={1}
      aria-valuemax={place.of}
      aria-valuenow={place.number}
      style:grid-template-columns="repeat({place.of}, minmax(0, 1fr))"
    >
      {#each overview.places as step, index (step.id)}
        <span class="seg" class:finished={step.finished} class:current={index + 1 === place.number}
        ></span>
      {/each}
    </div>
    <p class="hint">
      How much is there? A best guess is fine. {place.answered} of {place.total} done here.
    </p>
  </header>

  <ul class="rows" aria-label="Ingredients in the {place.place.name}">
    {#each place.rows as row (row.food.id)}
      {@const fraction = fractionOf(row)}
      <li class="item" class:asking={!row.staple && !counted(row) && !row.pack}>
        <div class="top-line">
          <b>{row.food.name}</b><span>{meta(row)}</span>
        </div>

        {#if row.staple}
          <p class="said">{stapleWords(row)}</p>
        {:else if counted(row)}
          <div class="stepper" role="group" aria-label="{row.food.name}: how many">
            <button
              type="button"
              aria-label="One fewer"
              disabled={countNow(row) <= 0}
              onclick={() => void model.count(row.food.id, row.food.name, countNow(row) - 1)}
              >−</button
            >
            <span class="number" class:unsaid={!row.answered}>{countWords(row, countNow(row))}</span
            >
            <button
              type="button"
              aria-label="One more"
              onclick={() => void model.count(row.food.id, row.food.name, countNow(row) + 1)}
              >+</button
            >
          </div>
        {:else}
          {#if !row.pack}
            <p class="said">What does it come in? Asked once.</p>
            <div class="chips" role="group" aria-label="Common sizes for {row.food.name}">
              {#each row.pack_suggestions as choice (choice.amount)}
                <button type="button" class="chip" onclick={() => pickSize(row, choice)}
                  >{choice.amount_text}</button
                >
              {/each}
              <button type="button" class="chip" onclick={() => openOther(row)}>Other…</button>
            </div>
            {#if otherFor === row.food.id}
              <form
                class="other"
                onsubmit={(event) => {
                  event.preventDefault();
                  sendOther(row);
                }}
              >
                <input
                  type="text"
                  inputmode="decimal"
                  aria-label="{row.food.name}: size of one pack"
                  placeholder="Size"
                  bind:value={otherAmount}
                />
                <select aria-label="Unit" bind:value={otherUnit}>
                  {#if row.food.counted_as === 'volume'}
                    <option value="ml">ml</option>
                    <option value="l">l</option>
                  {:else}
                    <option value="g">g</option>
                    <option value="kg">kg</option>
                  {/if}
                </select>
                <button type="submit" class="chip">Use this size</button>
              </form>
            {/if}
          {/if}
          <div
            class="seg-row"
            role="radiogroup"
            aria-label={row.food.name}
            use:radioKeys={{ select: false }}
          >
            {#each PICKS as pick (pick.value)}
              <button
                type="button"
                role="radio"
                aria-checked={fraction === pick.value}
                aria-label={pick.aria}
                disabled={pick.value > 0 && !row.pack}
                onclick={() =>
                  void model.pick(
                    row.food.id,
                    row.food.name,
                    pick.value,
                    pick.value === 0 ? 0 : moreOf(row)
                  )}>{pick.label}</button
              >
            {/each}
          </div>
          {#if row.pack && (shareOf(row) > 0 || moreOf(row) > 0)}
            {@const share = shareOf(row)}
            {@const more = moreOf(row)}
            <div class="stepper small" role="group" aria-label="{row.food.name}: more packets">
              <span class="label">More {row.pack.plural} besides this one</span>
              <button
                type="button"
                aria-label="One fewer {row.pack.name}"
                disabled={more <= 0}
                onclick={() => void model.pick(row.food.id, row.food.name, share, more - 1)}
                >−</button
              >
              <span class="number">{more}</span>
              <button
                type="button"
                aria-label="One more {row.pack.name}"
                disabled={more >= 20}
                onclick={() => void model.pick(row.food.id, row.food.name, share, more + 1)}
                >+</button
              >
            </div>
          {/if}
        {/if}

        {#if !row.staple}
          <button
            type="button"
            class="staple"
            onclick={() => void model.staple(row.food.id, row.food.name)}>It’s a staple</button
          >
        {/if}
      </li>
    {/each}
  </ul>

  {#if adding}
    <div class="adding">
      <FoodPicker
        label="Find an ingredient to count in the {place.place.name}"
        placeholder="e.g. toor dal"
        onpick={(food) => void pickedFood(food)}
        oncreate={(name) => void createdFood(name)}
        oncancel={() => (adding = false)}
      />
    </div>
  {:else}
    <button type="button" class="else" onclick={() => (adding = true)}
      >+ Something else in the {place.place.name}</button
    >
  {/if}

  <div class="foot">
    {#if place.previous}
      {@const previous = place.previous}
      <button type="button" class="back" onclick={() => void back(previous.id)}
        >← {previous.name}</button
      >
    {:else}
      <span></span>
    {/if}
    <button type="button" class="forward" onclick={() => void next()}>
      {place.next ? `Next: ${place.next.name} →` : 'Finish'}
    </button>
  </div>
{/if}

<style>
  .top {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding-bottom: var(--space-4);
    border-bottom: 1px solid var(--color-divider);
  }

  .bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .stop {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .count {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  h1 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    letter-spacing: -0.02em;
  }

  .progress {
    display: grid;
    gap: var(--space-2);
  }

  .seg {
    height: 5px;
    border-radius: 3px;
    background: var(--color-divider);
  }

  .seg.finished {
    background: var(--color-accent);
  }

  .seg.current {
    background: var(--color-accent);
    opacity: 0.6;
  }

  .hint,
  .note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .rows {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .item {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6) var(--space-6);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .item.asking {
    outline: 1px solid var(--color-accent);
  }

  .top-line {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-4);
  }

  .top-line b {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .top-line span {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    text-align: right;
  }

  .said {
    color: var(--color-text-soft);
    font-size: var(--text-sm);
  }

  .seg-row {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--space-3);
  }

  button {
    cursor: pointer;
  }

  .seg-row button {
    min-height: var(--touch-target);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .seg-row button:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .seg-row button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .other {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    align-items: center;
  }

  .other input {
    width: 7rem;
  }

  .stepper {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .stepper .label {
    flex: 1;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .stepper button {
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill-strong);
    color: var(--color-text);
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .stepper button:disabled {
    opacity: 0.45;
    cursor: default;
  }

  .number {
    min-width: 3.5rem;
    text-align: center;
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .stepper.small .number {
    min-width: 2rem;
    font-size: var(--text-lg);
  }

  .number.unsaid {
    color: var(--color-text-muted);
  }

  .staple {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: var(--color-accent-hover);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .else {
    min-height: 48px;
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-xl);
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .adding {
    padding: var(--space-4);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .foot {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 2fr);
    gap: var(--space-4);
  }

  .back,
  .forward {
    min-height: 56px;
    border: none;
    border-radius: 18px;
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .back {
    background: var(--color-fill-strong);
    color: var(--color-text);
  }

  .forward {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  .card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    padding: var(--space-8);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .done h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  .strong {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 18px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .quiet {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: var(--color-accent-hover);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  /* A computer: the stocktake is a column, not the whole width. */
  @media (min-width: 768px) {
    .top,
    .rows,
    .else,
    .adding,
    .foot,
    .card {
      width: 100%;
      max-width: 640px;
    }
  }
</style>
