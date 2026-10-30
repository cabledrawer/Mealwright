<script lang="ts">
  // One ingredient line on the review, as a card (mockup Dark-ImportCheck07-Desktop, spec "The
  // labels", "Learning", "New ingredient from an import", "Treat as staple" and "Importer
  // consistency"): a status dot, the line as written, the name it read with its amount and note as
  // chips (tap one to fix the amount, unit or note, F30.6), and what it is in your kitchen.
  //
  //   Ready (matched)   nothing to do: the ingredient and where it lives.
  //   Staple            nothing to do: a staple never counts towards stock.
  //   To confirm        Same as … · Pick another · New ingredient · Treat as staple.
  //   Needs you         New ingredient · Pick an ingredient · Treat as staple.
  //
  // A choice shows what it will do, can be changed right here, and is only made when Save is
  // pressed. A New ingredient opens its form, which closes with Done (F10) and shows as a settled
  // line; a choice made on one line is taken by the lines of the same import that read as the
  // same thing (F6).
  import FoodPicker from '#lib/components/FoodPicker.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import type { ReviewLine } from '#lib/client/imports.js';
  import type { CountedAs, Ref } from '#lib/client/types.js';
  import { readAmount } from '#lib/importAmount.js';
  import { amountWords, type Choice, type ImportFlow } from '#lib/import.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { LINE_UNITS } from '#lib/recipes/draft.svelte.js';
  import { unitFor } from '#lib/recipeAmounts.js';

  import '#lib/styles/fields.css';
  let {
    flow,
    index,
    line,
    problem = null
  }: { flow: ImportFlow; index: number; line: ReviewLine; problem?: string | null } = $props();

  const uid = $props.id();
  /** " · US pints" after a line that says pints: which pint it is read with. */
  const pintWords = $derived(line.pint_ml ? ` · ${flow.pints === 'us' ? 'US' : 'UK'} pints` : '');
  let picking = $state(false);
  /** The amount, unit and note boxes are open. */
  let editing = $state(false);
  /** The New ingredient form is open (it closes with Done). */
  let formOpen = $state(false);
  let amountText = $state('');
  let amountError = $state(false);
  let nameError = $state(false);
  const choice = $derived(flow.choices[index] ?? null);
  const open = $derived(line.label === 'to_confirm' || line.label === 'needs_you');
  const COUNTED: { value: CountedAs; label: string }[] = [
    { value: 'weight', label: 'By weight' },
    { value: 'volume', label: 'By volume' },
    { value: 'count', label: 'One by one' }
  ];

  /** The dot: what state the line is in. Colour never carries it alone: it has words too. */
  const status = $derived.by(() => {
    if (choice) return choice.kind === 'staple' ? 'staple' : 'ready';
    if (line.label === 'matched') return 'ready';
    if (line.label === 'staple') return 'staple';
    return line.label === 'to_confirm' ? 'confirm' : 'needs';
  });
  const STATUS_WORDS = {
    ready: 'Ready',
    confirm: 'To confirm',
    needs: 'Needs you',
    staple: 'Staple'
  } as const;

  /** "200 g", "3", "1½ cups": the amount as it will be saved. */
  const quantity = $derived(
    line.amount_text
      ? [line.amount_text, line.unit ? unitWord(line.unit) : ''].join(' ').trim()
      : ''
  );
  /** The note as a chip: not the "as written" copy the reader keeps. */
  const noteChip = $derived(line.note && !line.note.startsWith('as written:') ? line.note : '');
  const units = $derived(
    line.unit && !(LINE_UNITS as readonly string[]).includes(line.unit)
      ? [...LINE_UNITS, line.unit]
      : [...LINE_UNITS]
  );

  /** The name shown in bold: what it is (or will be) in your kitchen, else what was read. */
  const name = $derived.by(() => {
    if (choice) return choice.kind === 'ingredient' ? choice.food.name : choice.name;
    if (!open) return line.food?.name ?? line.words;
    return line.words;
  });

  function unitWord(unit: string): string {
    return line.amount === null ? unit : unitFor(unit, line.amount);
  }

  $effect(() => {
    if (!placesAndShops.places.length) void placesAndShops.load().catch(() => {});
  });

  function pick(food: Ref) {
    picking = false;
    flow.sameAs(index, food);
  }

  function makeNew(staple: boolean) {
    flow.newIngredient(index, staple);
    formOpen = true;
    nameError = false;
  }

  function edit(change: Partial<Extract<Choice, { kind: 'new' | 'staple' }>>) {
    if (choice && choice.kind !== 'ingredient') {
      flow.choose(index, { ...choice, ...change });
      for (const at of flow.followers(index)) {
        const other = flow.choices[at];
        if (other && other.kind !== 'ingredient') flow.choose(at, { ...other, ...change });
      }
    }
  }

  function doneForm() {
    if (choice && choice.kind !== 'ingredient' && !choice.name.trim()) {
      nameError = true;
      return;
    }
    nameError = false;
    formOpen = false;
  }

  function cancelForm() {
    formOpen = false;
    flow.unchoose(index);
  }

  function openEditor() {
    if (!editing) {
      amountText = line.amount_text ?? (line.amount === null ? '' : amountWords(line.amount));
      amountError = false;
    }
    editing = !editing;
  }

  function typeAmount(value: string) {
    amountText = value;
    const read = readAmount(value);
    amountError = !read;
    if (read) {
      flow.editLine(index, {
        amount: read.amount,
        amount_text: read.amount === null ? null : value.trim()
      });
    }
  }

  const alsoCalled = $derived(
    line.matched_by && line.food && line.matched_by.toLowerCase() !== line.food.name.toLowerCase()
      ? line.matched_by
      : null
  );
  const followers = $derived(flow.followers(index));
  /** What a new ingredient would be, for the buttons: “Milk”. */
  const guess = $derived(flow.guessFor(index));
  const sharedFrom = $derived(flow.sharedFrom[index]);
</script>

{#if line.kind === 'heading'}
  <li class="heading"><h3>{line.words}</h3></li>
{:else}
  <li class="line {status}" class:editing class:pints={!!line.pint_ml && flow.offersPints}>
    <span class="dot {status}" role="img" aria-label={STATUS_WORDS[status]}></span>
    <div class="main">
      <p class="written">
        <span class="visually-hidden">As written: </span>{line.written}{pintWords}
      </p>

      <p class="read">
        <span class="what">
          {#if choice && choice.kind !== 'ingredient'}
            <span class="made">{choice.kind === 'staple' ? 'New staple' : 'New ingredient'}:</span>
          {/if}
          {#if !choice && open && !line.readable}
            <b class="bad">Couldn’t read this line</b>
          {:else}
            <b>{name}</b>
          {/if}
        </span>
        <button
          type="button"
          class="chip-small"
          class:dashed={!quantity}
          aria-expanded={editing}
          aria-label="{quantity ? `Amount ${quantity}` : 'No amount'}. Fix the amount, unit or note"
          onclick={openEditor}>{quantity || 'No amount'}</button
        >
        {#if noteChip}
          <button
            type="button"
            class="chip-small dashed"
            aria-expanded={editing}
            aria-label="Note {noteChip}. Fix the amount, unit or note"
            onclick={openEditor}>{noteChip}</button
          >
        {/if}
        {#if alsoCalled && !choice}<span class="muted">· also called {alsoCalled}</span>{/if}
        {#if choice && choice.kind === 'ingredient'}
          <span class="muted">· same as “{line.learn_name ?? line.words}”</span>
        {/if}
        {#if !choice && open && line.readable && line.label === 'needs_you'}
          <span class="bad">· not in your ingredients</span>
        {/if}
        {#if !choice && !line.counts && line.label === 'matched'}
          <span class="muted">· not counted</span>
        {/if}
      </p>

      {#if editing}
        <div class="fields edit">
          <label class="field" for="{uid}-amount">
            <span>Amount</span>
            <input
              id="{uid}-amount"
              class="mw-input"
              type="text"
              inputmode="decimal"
              maxlength="20"
              autocomplete="off"
              aria-invalid={amountError ? true : undefined}
              value={amountText}
              oninput={(e) => typeAmount(e.currentTarget.value)}
            />
          </label>
          <label class="field" for="{uid}-unit">
            <span>Unit</span>
            <select
              id="{uid}-unit"
              class="mw-input"
              value={line.unit ?? ''}
              onchange={(e) => flow.editLine(index, { unit: e.currentTarget.value || null })}
            >
              <option value="">none</option>
              {#each units as unit (unit)}
                <option value={unit}>{unit}</option>
              {/each}
            </select>
          </label>
          <label class="field" for="{uid}-note">
            <span>Note</span>
            <input
              id="{uid}-note"
              class="mw-input"
              type="text"
              maxlength="200"
              autocomplete="off"
              value={line.note ?? ''}
              oninput={(e) =>
                flow.editLine(index, {
                  note: e.currentTarget.value.trim() ? e.currentTarget.value : null
                })}
            />
          </label>
        </div>
        {#if amountError}
          <p class="error" role="alert">Type a number, like 2 or ½.</p>
        {/if}
        <p class="done-row">
          <span class="hint">Tap the amount or note on any line to fix what was read.</span>
          <button type="button" class="done" onclick={() => (editing = false)}>Done</button>
        </p>
      {/if}

      {#if choice && choice.kind === 'ingredient'}
        {#if line.learn_name}
          <p class="hint">
            Adds “{line.learn_name}” as another name for {choice.food.name} when you save.
          </p>
        {/if}
      {:else if choice && formOpen}
        <div class="fields">
          <label class="field" for="{uid}-name">
            <span>Name</span>
            <input
              id="{uid}-name"
              class="mw-input"
              type="text"
              maxlength="100"
              aria-invalid={nameError ? true : undefined}
              value={choice.name}
              oninput={(e) => edit({ name: e.currentTarget.value })}
            />
          </label>
          <label class="field" for="{uid}-how">
            <span>How it’s counted</span>
            <select
              id="{uid}-how"
              class="mw-input"
              value={choice.counted_as}
              onchange={(e) => edit({ counted_as: e.currentTarget.value as CountedAs })}
            >
              {#each COUNTED as option (option.value)}
                <option value={option.value}>{option.label}</option>
              {/each}
            </select>
          </label>
          <label class="field" for="{uid}-place">
            <span>Usually kept in</span>
            <select
              id="{uid}-place"
              class="mw-input"
              value={choice.place_id ?? ''}
              onchange={(e) =>
                edit({ place_id: e.currentTarget.value ? Number(e.currentTarget.value) : null })}
            >
              <option value="">Nowhere in particular</option>
              {#each placesAndShops.places as place (place.id)}
                <option value={place.id}>{place.name}</option>
              {/each}
            </select>
          </label>
        </div>
        {#if nameError}<p class="error" role="alert">Type a name.</p>{/if}
        <p class="hint">
          {choice.kind === 'staple'
            ? 'Made a staple when you save. It never counts towards stock.'
            : 'Made when you save. Nothing is added to the pantry.'}
        </p>
        <div class="done-row">
          <span class="staple-switch">
            <Switch
              checked={choice.kind === 'staple'}
              labelledby="{uid}-staple"
              onchange={(on) => flow.setStaple(index, on)}
            />
            <span id="{uid}-staple">Treat as staple (never counted)</span>
          </span>
          <span class="two-buttons">
            <button type="button" class="quiet" onclick={cancelForm}>Cancel</button>
            <button type="button" class="done" onclick={doneForm}>Done</button>
          </span>
        </div>
      {:else if choice}
        <p class="hint">
          {choice.kind === 'staple'
            ? 'Made a staple when you save. It never counts towards stock.'
            : 'Made when you save. Nothing is added to the pantry.'}
          Counted {COUNTED.find((c) => c.value === choice.counted_as)?.label.toLowerCase()} · kept in
          {placesAndShops.places.find((p) => p.id === choice.place_id)?.name ??
            'nowhere in particular'}.
        </p>
      {/if}

      {#if choice && (followers.length > 0 || sharedFrom !== undefined)}
        <p class="also" role="status">
          {#if followers.length > 0}
            Also used for {followers.length} more {followers.length === 1 ? 'line' : 'lines'}: “{followers
              .map((j) => flow.review?.lines[j]?.written)
              .join('”, “')}”
          {:else}
            Same choice as “{flow.review?.lines[sharedFrom!]?.written}” above.
          {/if}
        </p>
      {/if}

      {#if open && !choice}
        {#if picking}
          <FoodPicker
            label="Pick an ingredient for {line.written}"
            onpick={pick}
            oncancel={() => (picking = false)}
          />
        {:else}
          <p class="buttons">
            {#if line.label === 'to_confirm' && line.food}
              <button type="button" class="chip main" onclick={() => flow.sameAs(index, line.food!)}
                >Same as “{line.food.name}”</button
              >
              <button type="button" class="chip" onclick={() => (picking = true)}
                >Pick another</button
              >
              <button type="button" class="chip" onclick={() => makeNew(false)}
                >New ingredient</button
              >
            {:else}
              <button type="button" class="chip main needs" onclick={() => makeNew(false)}
                >New ingredient{guess?.name ? ` “${guess.name}”` : ''}</button
              >
              <button type="button" class="chip" onclick={() => (picking = true)}
                >Pick an ingredient</button
              >
            {/if}
            <button type="button" class="chip" onclick={() => makeNew(true)}>Treat as staple</button
            >
          </p>
          {#if line.label === 'to_confirm' && line.food && line.learn_name}
            <p class="hint">
              “Same as” adds “{line.learn_name}” as another name for {line.food.name} when you save.
            </p>
          {/if}
        {/if}
      {/if}
      {#if choice && !formOpen}
        <p class="buttons">
          {#if choice.kind !== 'ingredient'}
            <button type="button" class="chip" onclick={() => (formOpen = true)}>Edit</button>
          {/if}
          <button type="button" class="chip" onclick={() => flow.unchoose(index)}>Change</button>
        </p>
      {/if}
      {#if problem}<p class="error" role="alert">{problem}</p>{/if}
    </div>
    <span class="state" class:staple={status === 'staple'}>
      {#if choice}
        {choice.kind === 'ingredient'
          ? 'Same as'
          : choice.kind === 'staple'
            ? 'New staple'
            : 'New ingredient'}
      {:else if line.label === 'staple'}
        Staple
      {:else if line.label === 'matched'}
        <Icon name="check" size={14} stroke={2.6} />{line.place ?? 'In your ingredients'}
      {/if}
    </span>
  </li>
{/if}

<style>
  li {
    list-style: none;
  }

  .heading h3 {
    padding: var(--space-5) 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
    overflow-wrap: anywhere;
  }

  /* Each line is its own card (mockup Dark-ImportCheck07-Desktop). */
  .line {
    display: flex;
    gap: var(--space-5);
    align-items: flex-start;
    padding: 12px 14px;
    border: 1px solid var(--color-border);
    border-radius: 16px;
    background: var(--color-surface);
  }

  .line.confirm {
    border-color: var(--color-maybe-chip-border);
  }

  .line.needs {
    border-color: var(--color-warning-border);
  }

  .line.editing {
    border: 2px solid var(--color-accent);
    padding: 11px 13px;
  }

  /* A line the US-pints switch changes (mockup ImportPints-*). */
  .line.pints {
    background: var(--color-changed);
  }

  .main {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .dot {
    flex: none;
    box-sizing: border-box;
    width: 12px;
    height: 12px;
    margin-top: 5px;
    border-radius: 6px;
  }

  .dot.ready {
    background: var(--color-accent);
  }

  .dot.confirm {
    background: var(--color-maybe-text);
  }

  .dot.needs {
    background: var(--color-warning-text);
  }

  .dot.staple {
    border: 2px solid var(--color-text-muted);
  }

  .written {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    overflow-wrap: anywhere;
  }

  .read {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3) var(--space-4);
    align-items: baseline;
    font-size: var(--text-base);
  }

  .what {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .made {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  /* The amount and the note: tap one to fix what was read. */
  /* The mockup draws these 28 px tall; a touch target is 44 px (the UX rule), so they are. */
  .chip-small {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 2px 10px;
    border: 1px solid var(--color-border-strong);
    border-radius: 8px;
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .chip-small.dashed {
    border-style: dashed;
    color: var(--color-text-soft);
    font-weight: var(--weight-semibold);
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .bad {
    color: var(--color-warning-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  b.bad {
    font-size: var(--text-base);
  }

  .state {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .state.staple {
    color: var(--color-text-soft);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    flex: none;
    max-width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .chip.main {
    border-color: transparent;
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
  }

  .chip.main.needs {
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .also {
    padding: 7px 10px;
    border-radius: 10px;
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .fields {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: var(--space-4);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  /* Boxes are 16 px or more, so a phone doesn't zoom in on them. */
  .field :is(input, select) {
    font-size: 1rem;
  }

  .done-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    align-items: center;
    justify-content: space-between;
  }

  .staple-switch,
  .two-buttons {
    display: inline-flex;
    gap: var(--space-4);
    align-items: center;
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .done,
  .quiet {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    font-size: var(--text-md);
    font-weight: var(--weight-extrabold);
    cursor: pointer;
  }

  .done {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .quiet {
    background: transparent;
    color: var(--color-text-muted);
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }
</style>
