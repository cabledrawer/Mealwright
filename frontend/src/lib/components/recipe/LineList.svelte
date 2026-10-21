<script lang="ts">
  // The ingredient lines and headings (cabledrawer 19 Oct, questions 11 to 14, editor brief item 10):
  // separate boxes for amount, unit, ingredient and note; the ingredient box is the line's own
  // words, and the picker (a sheet on a phone, under the line on a computer) links them to an
  // ingredient or to another recipe. Lines are dragged by the handle, or moved with Alt+↑ / Alt+↓.
  import '$lib/styles/fields.css';
  import { tick, untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import Icon from '../Icon.svelte';
  import IngredientPicker, { type Pick } from './IngredientPicker.svelte';
  import { getFood } from '$lib/client/foods';
  import type { Blocked, RecipeBrief } from '$lib/client/recipes';
  import type { FoodRow } from '$lib/client/types';
  import { newIngredient } from '$lib/newIngredient.svelte';
  import {
    blankLine,
    LINE_UNITS,
    MAX_LINES,
    type DraftLine,
    type Errors,
    type RecipeDraft
  } from '$lib/recipes/draft.svelte';
  import { move, reorder } from '$lib/recipes/reorder';
  import { undoHistory, type UndoEntry } from '$lib/undo.svelte';

  let {
    draft,
    phone,
    errors,
    blocked = [],
    search,
    announce
  }: {
    draft: RecipeDraft;
    phone: boolean;
    errors: Errors;
    blocked?: Blocked[];
    search: (q: string) => Promise<{ foods: FoodRow[]; recipes: RecipeBrief[] }>;
    announce: (message: string) => void;
  } = $props();

  const uid = $props.id();
  /** The line whose picker is open. */
  let active = $state<string | null>(null);
  let sheet: HTMLDialogElement;
  let root: HTMLElement;
  const removed: UndoEntry[] = [];

  const activeLine = $derived(draft.lines.find((l) => l.key === active) ?? null);
  const count = $derived(draft.lines.filter((l) => l.kind === 'ingredient').length);
  const full = $derived(draft.lines.length >= MAX_LINES);

  // --- Sizes ("1 packet") of the ingredients on the lines --------------------------------------

  const asked = new SvelteSet<number>();

  function loadSizes(foodId: number): void {
    if (asked.has(foodId)) return;
    asked.add(foodId);
    getFood(foodId)
      .then((food) => {
        draft.sizes[foodId] = food.sizes.map((s) => ({ id: s.id, name: s.name, plural: s.plural }));
      })
      .catch(() => asked.delete(foodId));
  }

  // The ingredients already on the lines: ask for their sizes, a few at a time.
  $effect(() => {
    const ids = [...new Set(draft.lines.flatMap((l) => (l.food ? [l.food.id] : [])))];
    untrack(() => {
      ids
        .filter((id) => !asked.has(id))
        .slice(0, 40)
        .forEach(loadSizes);
    });
  });

  const sizesOf = (line: DraftLine) => (line.food ? (draft.sizes[line.food.id] ?? []) : []);

  // --- Adding, taking out ----------------------------------------------------------------------

  async function add(kind: DraftLine['kind']) {
    const line = blankLine(kind);
    draft.lines.push(line);
    await tick();
    focusWords(line.key);
  }

  function focusWords(key: string) {
    root.querySelector<HTMLElement>(`[data-line="${key}"] [data-words]`)?.focus();
  }

  function takeOut(index: number) {
    const [line] = draft.lines.splice(index, 1);
    if (!line) return;
    if (active === line.key) close();
    const name = line.words.trim() || (line.kind === 'heading' ? 'the heading' : 'the line');
    const entry: UndoEntry = {
      label: `Took out ${name}`,
      undo: () => {
        draft.lines.splice(Math.min(index, draft.lines.length), 0, line);
      }
    };
    removed.push(entry);
    undoHistory.record(entry);
    // Focus goes to the next line's handle, else the one before, else the add button.
    void tick().then(() => {
      const rows = [
        ...root.querySelectorAll<HTMLElement>('[data-reorder-row] [data-reorder-handle]')
      ];
      (rows[index] ?? rows[index - 1] ?? root.querySelector<HTMLElement>('[data-add]'))?.focus();
    });
  }

  // The Undo entries are for this editor only.
  $effect(() => () => removed.forEach((entry) => undoHistory.forget(entry)));

  // --- The picker ------------------------------------------------------------------------------

  function open(line: DraftLine) {
    active = line.key;
  }

  function close(refocus = true) {
    const key = active;
    active = null;
    if (key && refocus) void tick().then(() => focusWords(key));
  }

  $effect(() => {
    if (!sheet) return;
    if (active && phone && !sheet.open) sheet.showModal();
    else if ((!active || !phone) && sheet.open) sheet.close();
  });

  function pick(line: DraftLine, choice: Pick) {
    const sized = line.unit.startsWith('size:');
    if (choice.kind === 'ingredient') {
      line.food = choice.food;
      line.recipe = null;
      loadSizes(choice.food.id);
    } else {
      line.recipe = choice.recipe;
      line.food = null;
    }
    line.recipeRemoved = false;
    // A size belongs to its ingredient; a recipe has none.
    if (sized) line.unit = '';
    // The words stay as typed (cabledrawer 19 Oct, question 14); an empty box takes the name.
    if (!line.words.trim())
      line.words = (choice.kind === 'ingredient' ? choice.food : choice.recipe).name;
    close();
  }

  async function createIngredient(line: DraftLine, name: string) {
    // Both dialogs are modal: the sheet gives way while "How do you count it?" is open.
    const made = await newIngredient.ask(name);
    if (made) pick(line, { kind: 'ingredient', food: { id: made.id, name: made.name } });
  }

  function sameName(line: DraftLine): boolean {
    const linked = line.food?.name ?? line.recipe?.name ?? '';
    return linked.trim().toLocaleLowerCase() === line.words.trim().toLocaleLowerCase();
  }

  function wordsKey(event: KeyboardEvent, line: DraftLine) {
    if (event.key === 'Escape' && active === line.key) {
      event.preventDefault();
      event.stopPropagation();
      close();
    } else if (event.key === 'ArrowDown') {
      open(line);
      void tick().then(() =>
        root.querySelector<HTMLElement>(`[data-line="${line.key}"] .inline .item`)?.focus()
      );
    }
  }

  function backdrop(event: MouseEvent) {
    if (event.target === sheet) close();
  }
</script>

<section class="lines" aria-labelledby="{uid}-title" bind:this={root}>
  <div class="title">
    <h2 id="{uid}-title">Ingredients</h2>
    <span class="count">
      {count}
      {count === 1 ? 'line' : 'lines'} ·
      {#if phone}drag to reorder{:else}drag, or Alt+↑ / Alt+↓ to move{/if}
    </span>
  </div>

  {#if !phone && draft.lines.some((l) => l.kind === 'ingredient')}
    <div class="head" aria-hidden="true">
      <span class="h-amount">Amount</span>
      <span class="h-unit">Unit</span>
      <span class="h-words">Ingredient (your words)</span>
      <span class="h-note">Note</span>
    </div>
  {/if}

  <ol>
    {#each draft.lines as line, i (line.key)}
      {@const lineError = errors[`line:${line.key}`]}
      {@const amountError = errors[`line:${line.key}.amount`]}
      <li class="row" class:heading={line.kind === 'heading'} data-reorder-row data-line={line.key}>
        <button
          type="button"
          class="mw-icon handle"
          data-reorder-handle
          aria-label="Move {line.kind === 'heading' ? 'heading' : 'ingredient'} {i +
            1}. Alt and the up or down arrow moves it."
          aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown"
          use:reorder={{
            index: () => draft.lines.indexOf(line),
            count: () => draft.lines.length,
            move: (from, to) => move(draft.lines, from, to),
            announce
          }}
        >
          <Icon name="grip" size={18} />
        </button>

        {#if line.kind === 'heading'}
          <input
            class="mw-input head-input"
            aria-label="Heading {i + 1}"
            data-words
            maxlength="200"
            placeholder="e.g. For the tempering"
            bind:value={line.words}
          />
        {:else}
          <div class="fields">
            <input
              class="mw-input amount"
              aria-label="Amount for ingredient {i + 1}"
              placeholder="–"
              maxlength="20"
              autocomplete="off"
              aria-invalid={amountError ? true : undefined}
              aria-describedby={amountError ? `${uid}-${line.key}-amount` : undefined}
              bind:value={line.amount}
            />
            <select
              class="mw-input unit"
              aria-label="Unit for ingredient {i + 1}"
              bind:value={line.unit}
            >
              <option value="">none</option>
              {#each sizesOf(line) as size (size.id)}
                <option value="size:{size.id}">{size.name}</option>
              {/each}
              {#each LINE_UNITS as unit (unit)}
                <option value={unit}>{unit}</option>
              {/each}
            </select>

            {#if phone}
              <button
                type="button"
                class="mw-input words"
                data-words
                aria-haspopup="dialog"
                aria-label="Ingredient {i + 1}: {line.words || 'empty'}"
                aria-describedby={lineError ? `${uid}-${line.key}-error` : undefined}
                onclick={() => open(line)}
              >
                {#if line.words}{line.words}{:else}<span class="placeholder">Ingredient</span>{/if}
              </button>
            {:else}
              <input
                class="mw-input words"
                data-words
                aria-label="Ingredient {i + 1}"
                maxlength="200"
                placeholder="Ingredient"
                autocomplete="off"
                aria-invalid={lineError ? true : undefined}
                aria-describedby={lineError ? `${uid}-${line.key}-error` : undefined}
                bind:value={line.words}
                oninput={() => open(line)}
                onclick={() => open(line)}
                onkeydown={(e) => wordsKey(e, line)}
              />
            {/if}

            <div class="meta">
              {#if line.recipe}
                <span class="tag" class:gone={line.recipeRemoved}>
                  <Icon name="recipes" size={14} />{line.recipeRemoved
                    ? 'recipe removed'
                    : 'recipe'}
                </span>
              {:else if line.food && !sameName(line)}
                <span class="linked">Linked to <i>{line.food.name}</i></span>
              {:else if line.words.trim() && !line.food}
                <span class="unlinked">
                  Not linked
                  <button type="button" onclick={() => open(line)}>Pick an ingredient</button>
                </span>
              {/if}
            </div>

            <input
              class="mw-input note"
              aria-label="Note for ingredient {i + 1}"
              maxlength="200"
              placeholder={phone ? 'Note (optional), e.g. rinsed' : 'Note'}
              autocomplete="off"
              bind:value={line.note}
            />
            {#if amountError}<p class="mw-error msg" id="{uid}-{line.key}-amount">
                {amountError}
              </p>{/if}
            {#if lineError}<p class="mw-error msg" id="{uid}-{line.key}-error" role="alert">
                {lineError}
              </p>{/if}
          </div>
        {/if}

        <button
          type="button"
          class="mw-icon take-out"
          aria-label={line.kind === 'heading' ? 'Take out this heading' : 'Take out of this recipe'}
          onclick={() => takeOut(i)}
        >
          <Icon name="close" size={18} />
        </button>

        {#if active === line.key && !phone && line.kind === 'ingredient'}
          <div class="inline-row">
            <div class="inline" role="group" aria-label="Pick an ingredient">
              <IngredientPicker
                query={line.words}
                {search}
                {blocked}
                onpick={(choice) => pick(line, choice)}
                oncreate={(name) => void createIngredient(line, name)}
                onback={() => focusWords(line.key)}
              />
              <button type="button" class="mw-pill close" onclick={() => close()}>Close</button>
            </div>
          </div>
        {/if}
      </li>
    {/each}
  </ol>

  <span class="adds">
    <button
      type="button"
      class="mw-add"
      data-add
      disabled={full}
      onclick={() => void add('ingredient')}
    >
      + Add ingredient
    </button>
    <button type="button" class="mw-add" disabled={full} onclick={() => void add('heading')}
      >+ Add heading</button
    >
  </span>
  {#if full}<p class="mw-hint">
      A recipe can have up to {MAX_LINES} lines, headings included.
    </p>{/if}
</section>

<!-- Phone: the picker is a sheet from the bottom, with its own search box that edits the line's words. -->
<dialog
  bind:this={sheet}
  class="sheet"
  aria-label="Pick an ingredient"
  oncancel={(e) => {
    e.preventDefault();
    close();
  }}
  onclick={backdrop}
>
  {#if activeLine && phone}
    <span class="grip" aria-hidden="true"></span>
    <div class="sheet-title">
      <h2>Pick an ingredient</h2>
      <button type="button" class="done" onclick={() => close()}>Done</button>
    </div>
    <label class="search">
      <Icon name="search" size={18} />
      <input
        type="search"
        aria-label="Search ingredients and recipes"
        autocomplete="off"
        maxlength="200"
        bind:value={activeLine.words}
      />
    </label>
    <IngredientPicker
      query={activeLine.words}
      {search}
      {blocked}
      onpick={(choice) => pick(activeLine, choice)}
      oncreate={(name) => void createIngredient(activeLine, name)}
    />
  {/if}
</dialog>

<style>
  .lines {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .title {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: var(--space-2) var(--space-6);
  }

  h2 {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
  }

  .count {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  ol {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-1) var(--space-4) var(--space-3);
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }

  .row.heading {
    padding: var(--space-2) 0 0;
    border: none;
    background: transparent;
    flex-wrap: nowrap;
    align-items: center;
  }

  /* While it is being dragged. */
  .row:global([data-dragging]) {
    box-shadow: var(--shadow-toast);
    outline: 2px solid var(--color-focus);
  }

  .handle,
  .take-out {
    position: relative;
    touch-action: none;
  }

  .handle {
    width: 28px;
    height: var(--touch-target);
    margin-top: 0;
    border-radius: var(--radius-sm);
    cursor: grab;
  }

  .take-out {
    width: 36px;
    height: var(--touch-target);
    touch-action: manipulation;
  }

  /* A touch area of at least 44 × 44 px around the narrower buttons. */
  .handle::before {
    content: '';
    position: absolute;
    inset: 0 -8px;
  }

  .take-out::before {
    content: '';
    position: absolute;
    inset: 0 -4px;
  }

  .fields {
    display: flex;
    flex: 1 1 0;
    flex-wrap: wrap;
    gap: var(--space-3);
    min-width: 0;
  }

  .amount {
    flex: 0 0 3.5rem;
    padding: 0 var(--space-3);
    text-align: center;
  }

  .unit {
    flex: 0 0 5rem;
    padding: 0 var(--space-3);
  }

  .words {
    flex: 1 1 7rem;
    min-width: 7rem;
  }

  button.words {
    height: auto;
    padding: var(--space-4) var(--space-5);
    line-height: 1.25;
    text-align: left;
    overflow-wrap: anywhere;
    cursor: text;
  }

  .placeholder {
    color: var(--color-text-muted);
  }

  .meta {
    flex: 1 1 100%;
    order: 4;
    font-size: var(--text-sm);
  }

  .meta:empty {
    display: none;
  }

  .note {
    flex: 1 1 100%;
    order: 5;
    background: var(--color-fill);
    border-color: transparent;
  }

  .msg {
    flex: 1 1 100%;
    order: 6;
  }

  .linked {
    color: var(--color-text-muted);
  }

  .linked i {
    font-weight: var(--weight-bold);
  }

  .tag {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 3px var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .tag.gone {
    background: var(--color-tub-chip);
    color: var(--color-tub-chip-text);
  }

  .unlinked {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
    color: var(--color-tub-chip-text);
    font-weight: var(--weight-bold);
  }

  .unlinked button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-tub-chip);
    color: var(--color-maybe-chip-text);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
    cursor: pointer;
  }

  .head-input {
    flex: 1;
    border-style: dashed;
    background: transparent;
    font-weight: var(--weight-extrabold);
  }

  .adds {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
    padding-top: var(--space-2);
  }

  .head {
    display: none;
  }

  /* The picker, under the line (computers). */
  .inline-row {
    flex: 1 1 100%;
  }

  .inline {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-3);
    max-width: 440px;
    margin-left: 36px;
    padding: var(--space-4);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
    box-shadow: var(--shadow-toast);
  }

  .inline > :global(.picker) {
    width: 100%;
  }

  /* The picker, a sheet from the bottom (phones). */
  .sheet {
    inset: auto 0 0 0;
    width: 100%;
    max-width: none;
    max-height: min(640px, calc(100dvh - 80px));
    margin: 0;
    padding: var(--space-5) var(--space-7) max(28px, env(safe-area-inset-bottom));
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
    overflow-y: auto;
    overscroll-behavior: contain;
    scrollbar-width: none;
  }

  .sheet[open] {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .sheet::backdrop {
    background: var(--color-overlay);
  }

  .grip {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .sheet-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-5);
    padding: var(--space-2) var(--space-2) var(--space-3);
  }

  .sheet-title h2 {
    font-size: var(--text-3xl);
  }

  .done {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .search {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 48px;
    padding: 0 var(--space-6);
    border: 2px solid var(--color-accent);
    border-radius: var(--radius-lg);
    background: var(--color-field);
    color: var(--color-text-muted);
  }

  .search input {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .search input::-webkit-search-cancel-button {
    display: none;
  }

  .search input:focus-visible {
    outline: none;
  }

  .search:focus-within {
    outline: 2px solid var(--color-focus);
    outline-offset: 2px;
  }

  @media (min-width: 768px) {
    .row {
      padding: 0;
      border: none;
      background: transparent;
    }

    .row.heading {
      padding-top: var(--space-3);
    }

    .fields {
      display: grid;
      grid-template-columns: 4rem 6rem minmax(0, 2fr) minmax(0, 1fr);
      align-items: start;
    }

    .amount,
    .unit,
    .words,
    .note {
      grid-row: 1;
      min-width: 0;
    }

    .meta {
      grid-column: 3 / -1;
      grid-row: 2;
    }

    .note {
      grid-column: 4;
    }

    .msg {
      grid-column: 1 / -1;
      grid-row: auto;
    }

    .head {
      display: grid;
      grid-template-columns: 4rem 6rem minmax(0, 2fr) minmax(0, 1fr);
      gap: var(--space-3);
      margin-right: calc(36px + var(--space-3));
      padding-left: calc(28px + var(--space-3));
      color: var(--color-text-muted);
      font-size: var(--text-sm);
      font-weight: var(--weight-bold);
    }

    .h-amount {
      text-align: center;
    }
  }
</style>
