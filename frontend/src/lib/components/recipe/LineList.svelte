<script lang="ts">
  // The ingredient lines and headings (cabledrawer 19 Oct, questions 11 to 14, editor brief item 10):
  // separate boxes for ingredient, amount, unit and note (in that order, cabledrawer 22 Oct); the ingredient box is the line's own
  // words, and the pick-list that opens under it while you type (a combobox with a listbox,
  // phone and computer alike; mockup RecipeLines) links them to an ingredient or to another
  // recipe. Enter in the last box adds a line. Lines are dragged by the handle, or moved with
  // Alt+↑ / Alt+↓.
  import '#lib/styles/fields.css';
  import { tick, untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import Icon from '../Icon.svelte';
  import Switch from '../Switch.svelte';
  import IngredientPicker, { type Pick } from './IngredientPicker.svelte';
  import { getFood } from '#lib/client/foods.js';
  import type { Blocked, RecipeBrief } from '#lib/client/recipes.js';
  import type { FoodRow } from '#lib/client/types.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import {
    blankLine,
    LINE_UNITS,
    MAX_LINES,
    type DraftLine,
    type Errors,
    type RecipeDraft
  } from '#lib/recipes/draft.svelte.js';
  import { linkedWords } from '#lib/recipes/linkedWords.js';
  import { move, reorder } from '#lib/recipes/reorder.js';
  import { undoHistory, type UndoEntry } from '#lib/undo.svelte.js';
  import { plural } from '#lib/words.js';

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
  /** The line whose pick-list is open. */
  let active = $state<string | null>(null);
  let picker = $state<{ key: (event: KeyboardEvent) => boolean }>();
  /** The option the arrow keys are on, for aria-activedescendant. */
  let activeOption = $state<string>();
  let root: HTMLElement;
  const removed: UndoEntry[] = [];

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

  /** An ingredient line with nothing in it yet. */
  const isBlank = (line: DraftLine | undefined) =>
    !!line &&
    line.kind === 'ingredient' &&
    !line.words.trim() &&
    !line.amount.trim() &&
    !line.unit &&
    !line.food &&
    !line.recipe &&
    !line.note.trim();

  async function add(kind: DraftLine['kind']) {
    // A blank last line is used rather than piling up another one.
    const last = draft.lines.at(-1);
    if (kind === 'ingredient' && last && isBlank(last)) return focusWords(last.key);
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
      label: `Removed ${name}`,
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

  /** "Pick an ingredient" under an unlinked line: opens the list with the box ready to type in. */
  function openAndFocus(line: DraftLine) {
    open(line);
    focusWords(line.key);
  }

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
    // The words stay as typed (cabledrawer 19 Oct, question 14); an empty box takes the name, and
    // only the start of the ingredient's name ("thu") becomes all of it (cabledrawer 25 Oct).
    if (!line.words.trim())
      line.words = (choice.kind === 'ingredient' ? choice.food : choice.recipe).name;
    else if (choice.kind === 'ingredient')
      line.words = linkedWords(line.words, { ...choice.food, other_names: choice.otherNames });
    close();
  }

  async function createIngredient(line: DraftLine, name: string) {
    // Both dialogs are modal: the sheet gives way while "Pantry keeps it by" is open.
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
      close(false);
    } else if (active === line.key && picker?.key(event)) {
      event.preventDefault();
    } else if (event.key === 'ArrowDown' && line.words.trim()) {
      open(line);
    }
  }

  /** The list closes when focus leaves the box (options take no focus, so a pick isn't a leave). */
  function leave(line: DraftLine, box: HTMLElement) {
    // A moment's grace: a tap on an option can reach it after the box has lost focus.
    setTimeout(() => {
      if (active === line.key && document.activeElement !== box) close(false);
    }, 200);
  }

  /** Enter in the last box of the last line adds a line, as the "+ Add line" button does. */
  function noteKey(event: KeyboardEvent, index: number) {
    if (event.key !== 'Enter' || event.isComposing || index !== draft.lines.length - 1) return;
    event.preventDefault();
    if (!full) void add('ingredient');
  }
</script>

<section class="lines" aria-labelledby="{uid}-title" bind:this={root}>
  <div class="title">
    <h2 id="{uid}-title">Ingredients</h2>
    <span class="count">
      {count}
      {plural(count, 'line', 'lines')} ·
      {#if phone}drag to reorder{:else}drag, or Alt+↑ / Alt+↓ to move{/if}
    </span>
  </div>

  {#if !phone && draft.lines.some((l) => l.kind === 'ingredient')}
    <div class="head" aria-hidden="true">
      <span class="h-words">Ingredient (your words)</span>
      <span class="h-amount">Amount</span>
      <span class="h-unit">Unit</span>
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
            onkeydown={(e) => noteKey(e, i)}
          />
        {:else}
          <div class="fields">
            <div class="words-wrap">
              {#if line.food || line.recipe}
                <span class="dot" aria-hidden="true"></span>
              {/if}
              <input
                class="mw-input words"
                class:linked-box={!!(line.food || line.recipe)}
                data-words
                role="combobox"
                aria-label="Ingredient {i + 1}"
                aria-autocomplete="list"
                aria-expanded={active === line.key}
                aria-controls={active === line.key ? `${uid}-list` : undefined}
                aria-activedescendant={active === line.key ? activeOption : undefined}
                maxlength="200"
                placeholder="Ingredient"
                autocomplete="off"
                aria-invalid={lineError ? true : undefined}
                aria-describedby={lineError ? `${uid}-${line.key}-error` : undefined}
                bind:value={line.words}
                oninput={() => open(line)}
                onkeydown={(e) => wordsKey(e, line)}
                onblur={(e) => leave(line, e.currentTarget)}
              />
              {#if active === line.key}
                <div class="popup">
                  <IngredientPicker
                    id="{uid}-list"
                    bind:this={picker}
                    bind:activeId={activeOption}
                    query={line.words}
                    {search}
                    {blocked}
                    onpick={(choice) => pick(line, choice)}
                    oncreate={(name) => void createIngredient(line, name)}
                  />
                </div>
              {/if}
            </div>

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
                  <button type="button" onclick={() => openAndFocus(line)}
                    >Pick an ingredient</button
                  >
                </span>
              {/if}
            </div>

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

            <input
              class="mw-input note"
              aria-label="Note for ingredient {i + 1}"
              maxlength="200"
              placeholder={phone ? 'Note (optional), e.g. rinsed' : 'Note'}
              autocomplete="off"
              bind:value={line.note}
              onkeydown={(e) => noteKey(e, i)}
            />
            <div class="opt">
              <Switch
                bind:checked={line.optional}
                label="Optional: ingredient {i + 1}"
                labelledby={undefined}
              />
              <span aria-hidden="true">Optional</span>
            </div>
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
          aria-label={line.kind === 'heading' ? 'Remove this heading' : 'Remove line'}
          onclick={() => takeOut(i)}
        >
          <Icon name="close" size={18} />
        </button>
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
      + Add line
    </button>
    <button type="button" class="mw-add" disabled={full} onclick={() => void add('heading')}
      >+ Add heading</button
    >
  </span>
  {#if full}<p class="mw-hint">
      A recipe can have up to {MAX_LINES} lines, headings included.
    </p>{/if}
  <p class="mw-hint">
    Pick a name from the list to link it (green dot). Enter on the last box adds a line.
  </p>
</section>

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
    order: 3;
    flex: 0 0 3.5rem;
    padding: 0 var(--space-3);
    text-align: center;
  }

  .unit {
    order: 4;
    flex: 0 0 5rem;
    padding: 0 var(--space-3);
  }

  .meta {
    flex: 1 1 100%;
    order: 2;
    font-size: var(--text-sm);
  }

  .meta:empty {
    display: none;
  }

  .note {
    flex: 1 1 8rem;
    order: 5;
    background: var(--color-fill);
    border-color: transparent;
  }

  .msg {
    flex: 1 1 100%;
    order: 7;
  }

  /* The Optional switch (R3): under the note. */
  .opt {
    display: flex;
    flex: 1 1 100%;
    order: 6;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
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

  /* The ingredient box, with the pick-list opening under it. */
  .words-wrap {
    position: relative;
    order: 1;
    flex: 1 1 100%;
    min-width: 7rem;
  }

  .words-wrap .words {
    width: 100%;
  }

  /* A line linked to an ingredient or a recipe: a green dot in the box (mockup RecipeLines). */
  .dot {
    position: absolute;
    top: calc(var(--touch-target) / 2 - 4px);
    left: var(--space-4);
    width: 8px;
    height: 8px;
    border-radius: 4px;
    background: var(--color-accent);
    pointer-events: none;
  }

  .linked-box {
    padding-left: calc(var(--space-4) + 8px + var(--space-3));
  }

  .popup {
    position: absolute;
    top: calc(var(--touch-target) + var(--space-2));
    /* From the box's left edge, over the columns beside it. Anchored to its right edge, a box
       narrower than the list (the editor at about 912 px) pushed the list left, half under the
       sidebar (F185). */
    left: 0;
    z-index: 5;
    width: min(24rem, calc(100vw - 4rem));
    max-height: 60vh;
    padding: var(--space-3);
    overflow-y: auto;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    box-shadow: var(--shadow-toast);
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
      grid-template-columns: minmax(0, 2fr) 4rem 6rem minmax(0, 1fr);
      align-items: start;
    }

    .amount,
    .unit,
    .words-wrap,
    .note {
      grid-row: 1;
      min-width: 0;
    }

    .meta {
      grid-column: 1;
      grid-row: 2;
    }

    .words-wrap {
      grid-column: 1;
    }

    .amount {
      grid-column: 2;
    }

    .unit {
      grid-column: 3;
    }

    .note {
      grid-column: 4;
    }

    .opt {
      grid-column: 4;
      grid-row: 2;
      min-width: 0;
    }

    .msg {
      grid-column: 1 / -1;
      grid-row: auto;
    }

    .head {
      display: grid;
      grid-template-columns: minmax(0, 2fr) 4rem 6rem minmax(0, 1fr);
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
