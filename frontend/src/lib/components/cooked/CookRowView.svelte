<script lang="ts">
  // One ingredient of the "Cooked it" review (mockups Cooked-Desktop, Cooked-Phone): its name, where
  // it is, Before → After, what is taken and its Use switch. Under it, what the row needs from
  // you: a question in the pantry's unit (F106), "Bought some — used them", a tick for the
  // shopping list. The words are proposed, for cabledrawer (words.md section 28).
  import { askOnce } from '#lib/askOnce.svelte.js';
  import type { CookRow } from '#lib/client/cook.js';
  import {
    amountWords,
    conversionAnswer,
    hasSwitch,
    numberWords,
    parseAmountText,
    ownTake,
    recipeSays,
    shown,
    sizeAnswer,
    unitLabel,
    unitsDiffer,
    roundForScreen,
    listAmountWords,
    nameInSentence,
    upperFirst,
    type RowState
  } from '#lib/cookRows.js';
  import type { CookReview, CookTab } from '#lib/cookReview.svelte.js';
  import Switch from '../Switch.svelte';

  let {
    review,
    tab,
    row,
    disabled = false
  }: { review: CookReview; tab: CookTab; row: CookRow; disabled?: boolean } = $props();

  const uid = $props.id();
  const mine = $derived(tab.state(row.key));
  const name = $derived(upperFirst(row.food?.name ?? row.recipe?.name ?? recipeSays(row)));
  const view = $derived(shown(row, mine));
  const counted = $derived(row.unit === 'count');
  const own = $derived(ownTake(row));
  const standIns = $derived(row.takes.filter((t) => t.stand_in));
  const switchy = $derived(hasSwitch(row));
  const places = $derived.by(() => {
    const names: string[] = [];
    for (const take of row.takes)
      for (const lot of take.lots)
        if (lot.place && !names.includes(lot.place.name)) names.push(lot.place.name);
    return names.join(', ');
  });
  const nothing = $derived(
    row.status === 'none_in_pantry' || (row.takes.length === 0 && row.status === 'take')
  );

  let editing = $state(false);
  let typed = $state('');
  let remember = $state(true);
  let skipped = $state(false);

  function patch(change: Partial<RowState>) {
    tab.patch(row.key, change);
  }

  /** What the box starts with: what would be taken now. */
  const startValue = $derived(view.taken);

  function openEdit() {
    typed = numberText(startValue);
    editing = true;
  }

  const numberText = (n: number) => String(roundForScreen(n, row.unit));
  const parse = parseAmountText;
  const typedNumber = $derived(parse(typed));

  function setTyped(text: string) {
    typed = text;
    const n = parse(text);
    if (text.trim() !== '' && Number.isFinite(n) && n >= 0) patch({ value: n });
  }

  function step(by: number) {
    const current = mine?.value ?? view.taken;
    const next = Math.max(0, Math.round((current + by) * 2) / 2);
    patch({ value: next });
  }

  // The question, in the pantry's unit (F106). The conversion is worked out from the answer.
  const ask = $derived(row.status === 'ask' ? row.ask : null);
  const derivable = $derived(
    ask !== null && conversionAnswer(ask, row.ask_need, row.unit, 1, true) !== null
  );
  const countNote = $derived(row.status === 'no_amount' ? row.count_note : null);
  const asking = $derived((derivable || countNote !== null) && !skipped);
  const unit = $derived(unitLabel(row));
  /** A line with no amount, switched on: the amount is typed in the pantry's unit. */
  const manual = $derived(row.status === 'no_amount' && countNote === null && view.use);

  /** The figure was too far from sensible to learn from (a cup that weighs 10 kg). */
  let unlikely = $state(false);

  async function answer(value: number) {
    if (!(value > 0)) return;
    unlikely = false;
    if (ask && derivable) {
      const given = conversionAnswer(ask, row.ask_need, row.unit, value, remember);
      if (given) await review.addAnswer(given);
      else unlikely = true;
    } else if (countNote && row.food) {
      patch({ value, mode: 'used', use: true });
      const size = remember ? sizeAnswer(row.food.id, countNote, value) : null;
      if (size) await review.addAnswer(size, false);
    }
  }

  async function oldWay() {
    if (!ask) return;
    const given = await askOnce.ask(ask);
    if (given) await review.addAnswer(given);
  }

  const listTick = $derived(mine?.addToList ?? row.add_to_list);
  const fromFreezer = $derived(mine?.fromFreezer ?? false);
</script>

<li class="row" class:off={switchy && !view.use} data-testid="cook-row" data-key={row.key}>
  <div class="name">
    <b>{name}</b>
    {#if row.status === 'not_linked'}
      <span class="says">Not linked to an ingredient, so nothing is taken.</span>
    {:else if unitsDiffer(row) || row.status === 'no_amount'}
      <span class="says">Recipe says {recipeSays(row)}</span>
    {/if}
  </div>

  <div class="from">
    {#if row.status === 'none_in_pantry' || (nothing && !row.in_freezer && row.food)}
      <b class="none">Not in pantry</b>
    {:else if places}
      {places}
    {/if}
    {#each standIns as take (take.food.id)}
      <span class="says">Instead: {take.food.name}</span>
    {/each}
  </div>

  <div class="ba">
    {#if view.before !== null && own}
      <span class="visually-hidden"
        >Before {amountWords(view.before, row.unit)}, after {amountWords(
          view.after ?? 0,
          row.unit
        )}</span
      >
      <span aria-hidden="true"
        >{numberWords(view.before, row.unit)} →
        <b>{amountWords(view.after ?? 0, row.unit)}</b></span
      >
    {:else if row.needed}
      <span class="says">needs {amountWords(row.needed.amount, row.unit)}</span>
    {/if}
  </div>

  <div class="take">
    {#if view.use && view.taken > 0}
      {#if counted}
        <span class="used-left" role="group" aria-label="Enter amount as">
          <button
            type="button"
            aria-pressed={(mine?.mode ?? 'used') === 'used'}
            {disabled}
            onclick={() => patch({ mode: 'used' })}>Used</button
          >
          <button
            type="button"
            aria-pressed={mine?.mode === 'left'}
            {disabled}
            onclick={() => patch({ mode: 'left' })}>Left</button
          >
        </span>
        <span class="stepper">
          <button type="button" aria-label="Fewer {name}" {disabled} onclick={() => step(-0.5)}
            >−</button
          >
          <b aria-live="polite"
            >{numberWords(
              mine?.value ?? (mine?.mode === 'left' ? (view.after ?? 0) : view.taken)
            )}</b
          >
          <button type="button" aria-label="More {name}" {disabled} onclick={() => step(0.5)}
            >+</button
          >
        </span>
      {:else}
        <button
          type="button"
          class="amount"
          {disabled}
          aria-expanded={editing}
          aria-label="−{amountWords(view.taken, row.unit)} {name}. Change how much"
          onclick={() => (editing ? (editing = false) : openEdit())}
          >−{amountWords(view.taken, row.unit)}</button
        >
      {/if}
      {#if row.estimate}<span class="estimate" title="Worked out by changing units">estimate</span
        >{/if}
    {:else if view.use && switchy}
      <span class="says">nothing to take</span>
    {/if}
  </div>

  <div class="use">
    {#if switchy}
      <Switch
        checked={view.use}
        label="Take {name} from the pantry"
        disabled={disabled ||
          (nothing && !row.in_freezer && row.status !== 'ask' && row.status !== 'no_amount')}
        onchange={(on) => patch({ use: on, bought: on ? false : (mine?.bought ?? false) })}
      />
    {/if}
  </div>

  {#if (editing && !counted && view.use) || manual}
    <div class="extra edit">
      <span class="used-left" role="group" aria-label="Enter amount as">
        <button
          type="button"
          aria-pressed={(mine?.mode ?? 'used') === 'used'}
          {disabled}
          onclick={() => patch({ mode: 'used' })}>Used</button
        >
        <button
          type="button"
          aria-pressed={mine?.mode === 'left'}
          {disabled}
          onclick={() => patch({ mode: 'left' })}>Left</button
        >
      </span>
      <label>
        <span class="visually-hidden"
          >{mine?.mode === 'left' ? 'How much is left' : 'How much was used'}, in {unit ||
            'units'}</span
        >
        <input
          type="text"
          inputmode="decimal"
          maxlength="20"
          value={typed}
          {disabled}
          oninput={(e) => setTyped(e.currentTarget.value)}
        />
      </label>
      <span class="unit" aria-hidden="true">{unit}</span>
      {#if mine?.value != null}
        <button
          type="button"
          class="link"
          onclick={() => {
            patch({ value: null });
            editing = false;
          }}>As worked out</button
        >
      {/if}
    </div>
  {/if}

  {#if asking}
    <div class="extra ask" role="group" aria-labelledby="{uid}-q">
      <p id="{uid}-q" class="q">
        {#if countNote}
          {#if counted}
            {numberWords(countNote.count)}
            {countNote.word}{countNote.count === 1 ? '' : 's'} is how many {row.unit_word
              ? `${row.unit_word} of ${name}`
              : name}?
          {:else}
            How much is {numberWords(countNote.count)}
            {countNote.word}{countNote.count === 1 ? '' : 's'} of {nameInSentence(name)}?
          {/if}
        {:else}
          How much {name} did you use?
        {/if}
      </p>
      <div class="answer">
        <label>
          <span class="visually-hidden">Your answer, in {unit || 'units'}</span>
          <input type="text" inputmode="decimal" maxlength="20" bind:value={typed} {disabled} />
        </label>
        <span class="unit" aria-hidden="true">{unit}</span>
        <button
          type="button"
          class="pill dark"
          disabled={disabled || !(typedNumber > 0)}
          onclick={() => answer(typedNumber)}>Use this</button
        >
        {#if row.half}
          <button
            type="button"
            class="pill"
            {disabled}
            onclick={() => answer(row.half?.amount ?? 0)}>About half</button
          >
        {/if}
        <button
          type="button"
          class="pill"
          {disabled}
          onclick={() => {
            skipped = true;
            patch({ use: false });
          }}>Skip</button
        >
      </div>
      {#if unlikely}
        <p class="q" role="alert">That doesn’t look right. Try another amount.</p>
      {/if}
      <div class="remember">
        <span id="{uid}-r">Remember for next time</span>
        <Switch bind:checked={remember} labelledby="{uid}-r" {disabled} />
      </div>
    </div>
  {:else if row.status === 'ask' && !derivable && !skipped}
    <div class="extra ask">
      <p class="q">{row.ask?.question}</p>
      <div class="answer">
        <button type="button" class="pill dark" {disabled} onclick={oldWay}>Answer</button>
        <button
          type="button"
          class="pill"
          {disabled}
          onclick={() => {
            skipped = true;
            patch({ use: false });
          }}>Skip</button
        >
      </div>
    </div>
  {:else if skipped && (row.status === 'ask' || countNote)}
    <div class="extra">
      <span class="says">Skipped</span>
      <button type="button" class="link" onclick={() => (skipped = false)}>Ask again</button>
    </div>
  {/if}

  {#if row.status === 'none_in_pantry'}
    <div class="extra">
      <button
        type="button"
        class="pill"
        aria-pressed={mine?.bought ?? false}
        {disabled}
        onclick={() => patch({ bought: !(mine?.bought ?? false), use: false })}
        >Bought some — used them</button
      >
    </div>
  {/if}

  {#if row.in_freezer && row.status !== 'staple'}
    <div class="extra tick">
      <span id="{uid}-f"
        >Take from the freezer too ({amountWords(row.in_freezer.amount, row.unit)})</span
      >
      <Switch
        checked={fromFreezer}
        labelledby="{uid}-f"
        {disabled}
        onchange={(on) => patch({ fromFreezer: on, ...(on ? { use: true } : {}) })}
      />
    </div>
  {/if}

  {#if row.make_first}
    <div class="extra"><span class="says">Make {row.recipe?.name ?? 'it'} first?</span></div>
  {/if}

  {#if row.list_amount && !mine?.bought}
    <div class="extra tick">
      <span id="{uid}-l">
        {row.short
          ? `Short by ${amountWords(row.short.amount, row.unit)}.`
          : row.running_low
            ? 'Running low.'
            : ''} Add {listAmountWords(
          row.list_amount.as_sold
            ? (row.list_amount.short ?? '')
            : amountWords(row.list_amount.amount, row.unit),
          name
        )}
        to the shopping list
      </span>
      <Switch
        checked={listTick}
        labelledby="{uid}-l"
        {disabled}
        onchange={(on) => patch({ addToList: on })}
      />
    </div>
  {/if}
</li>

<style>
  .row {
    display: grid;
    align-items: center;
    column-gap: var(--space-4);
    row-gap: var(--space-2);
    padding: var(--space-4) 0;
    border-top: 1px solid var(--color-divider);
    list-style: none;
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      'name use'
      'from use'
      'ba take'
      'extra extra';
  }

  .name {
    grid-area: name;
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .name b {
    font-size: var(--text-lg);
  }

  .from {
    grid-area: from;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .ba {
    grid-area: ba;
    font-size: var(--text-md);
    color: var(--color-text-muted);
  }

  .take {
    grid-area: take;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: flex-end;
    gap: var(--space-2);
    font-weight: var(--weight-extrabold);
  }

  .use {
    grid-area: use;
    display: flex;
    justify-content: flex-end;
  }

  .extra {
    grid-column: 1 / -1;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .off .name b,
  .off .ba {
    color: var(--color-text-muted);
  }

  .none {
    color: var(--color-warning-text);
  }

  .says {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-medium);
  }

  .estimate {
    padding: 2px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-info);
    color: var(--color-info-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  button {
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .amount {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: none;
    color: var(--color-text);
    font-weight: var(--weight-extrabold);
    text-decoration: underline dotted;
    text-underline-offset: 4px;
  }

  .used-left {
    display: flex;
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-segment-track);
  }

  .used-left button {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .used-left button[aria-pressed='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }

  .stepper {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }

  .stepper button {
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill-strong);
    color: var(--color-text);
    font-size: var(--text-xl);
  }

  .stepper b {
    min-width: 2.2rem;
    text-align: center;
  }

  input {
    width: 7rem;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
  }

  .unit {
    font-weight: var(--weight-bold);
  }

  .ask {
    flex-direction: column;
    align-items: stretch;
    padding: var(--space-5);
    border-radius: var(--radius-xl);
    background: var(--color-note);
    color: var(--color-note-text);
  }

  .ask .q {
    font-weight: var(--weight-bold);
  }

  .answer {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .remember {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .pill {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: inherit;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .pill.dark {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .pill[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: none;
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
    text-decoration: underline;
  }

  .tick {
    justify-content: space-between;
    font-size: var(--text-md);
  }

  @media (min-width: 768px) {
    .row {
      grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.9fr) minmax(0, 1fr) minmax(0, 1.3fr) 60px;
      grid-template-areas:
        'name from ba take use'
        'extra extra extra extra extra';
    }

    .take {
      justify-self: end;
    }
  }
</style>
