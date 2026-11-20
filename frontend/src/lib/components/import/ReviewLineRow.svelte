<script lang="ts">
  import Lazy from '#lib/components/Lazy.svelte';
  import { KEPT_BY, KEPT_BY_HINT, keptBySaid } from '#lib/keptByWords.js';
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
  import { tick } from 'svelte';
  import Icon from '#lib/components/Icon.svelte';
  import NewPlace, { NEW_PLACE } from '#lib/components/NewPlace.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import type { LinePick } from './PickLine.svelte';
  import ChangeLine from './ChangeLine.svelte';
  import OwnRecipeHead from './OwnRecipeHead.svelte';
  import { listFoods } from '#lib/client/foods.js';
  import { toasts } from '#lib/toast.svelte.js';
  import type { ReviewLine } from '#lib/client/imports.js';
  import type { CountedAs, Ref } from '#lib/client/types.js';
  import { readAmount } from '#lib/importAmount.js';
  import {
    amountWords,
    isBlank,
    type Choice,
    type ImportFlow,
    type NewIngredientBefore
  } from '#lib/import.svelte.js';
  import { focusOnMount } from '#lib/focusOnMount.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { LINE_UNITS } from '#lib/recipes/draft.svelte.js';
  import { unitFor } from '#lib/recipeAmounts.js';

  import '#lib/styles/fields.css';
  import { plural } from '#lib/words.js';
  let {
    flow,
    index,
    line,
    problem = null
  }: { flow: ImportFlow; index: number; line: ReviewLine; problem?: string | null } = $props();

  /** Edit the name read with no answer from the server (accepted, cabledrawer 11 Nov). */
  const RENAME_OFFLINE =
    'Name changed. Looking for an ingredient with that name needs a connection, so the row keeps its match.';

  const uid = $props.id();
  /** " · US pints" after a line that says pints: which pint it is read with. */
  const pintWords = $derived(line.pint_ml ? ` · ${flow.pints === 'us' ? 'US' : 'UK'} pints` : '');
  let picking = $state(false);
  /** Change (F214): the sheet under the row is open, and its Pick an ingredient list. */
  let changing = $state(false);
  let changePicking = $state(false);
  /** The pick-list starts with recipes only ("Made in another recipe"). */
  let pickingRecipes = $state(false);
  /** The New ingredient form: where it comes from (F188), the recipe picked and where kept. */
  let source = $state<'bought' | 'recipe'>('bought');
  let madeBy = $state<{ recipe: Ref; madeAhead: boolean } | null>(null);
  /** Where the pantry keeps it: undefined until the person picks, then the Fridge shows picked. */
  let keepPlace = $state<number | undefined>(undefined);
  let choosingRecipe = $state(false);
  let recipeError = $state(false);
  let addingPlace = $state(false);
  /** The amount, unit and note boxes are open. */
  let editing = $state(false);
  /** The New ingredient form is open (it closes with Done). */
  let formOpen = $state(false);
  let amountText = $state('');
  let amountError = $state(false);
  let nameError = $state(false);
  const choice = $derived(flow.choices[index] ?? null);
  /** A line added on Check (F187) that has no name yet: its name box is open. */
  const blank = $derived(isBlank(line));
  let addName = $state('');
  let addNameError = $state(false);
  let rowEl: HTMLElement | undefined = $state();
  /** A New ingredient or staple choice (has a name and a place), and "Made in this recipe" (F108). */
  const made = $derived(
    choice && (choice.kind === 'new' || choice.kind === 'staple') ? choice : null
  );
  const here = $derived(choice?.kind === 'here');
  /** The section this line stands for, when it was made its own recipe (F190). */
  const ownUse = $derived(line.kind === 'ingredient' && !choice ? flow.ownUseOf(index) : null);
  /** "Made in another recipe" (F188). */
  const recipeChoice = $derived(choice?.kind === 'recipe' ? choice : null);
  /** "Made in this recipe" is offered first (F108). */
  const hereFirst = $derived(flow.offersMadeHere(index));
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
  /** The other choice of an "or" line (F217), as the words after "or": "2 medium flat bread". */
  const orText = $derived.by(() => {
    const other = line.alternative;
    if (!other || choice) return '';
    const amount = other.amount_text
      ? [other.amount_text, other.unit ? unitFor(other.unit, other.amount ?? 1) : '']
          .join(' ')
          .trim()
      : '';
    return [amount, other.words].filter(Boolean).join(' ');
  });
  /** The note as a chip: not the "as written" copy the reader keeps. */
  const noteChip = $derived(line.note && !line.note.startsWith('as written:') ? line.note : '');
  const units = $derived(
    line.unit && !(LINE_UNITS as readonly string[]).includes(line.unit)
      ? [...LINE_UNITS, line.unit]
      : [...LINE_UNITS]
  );

  /** The name shown in bold: what it is (or will be) in your kitchen, else what was read. */
  const name = $derived.by(() => {
    if (choice?.kind === 'here') return line.words;
    if (choice?.kind === 'recipe') return choice.recipe.name;
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
  // A line made on another phone's new place (a saved draft): fetch them again.
  $effect(() => {
    void placesAndShops.reloadFor(made?.place_id);
  });

  // --- Split into two (F109) --------------------------------------------------------------
  let splitting = $state(false);
  let splitNames = $state<[string, string]>(['', '']);
  let splitError = $state(false);

  /** The line's name cut at its joiner ("water and broth"), else the whole name and a blank. */
  function twoNames(words: string): [string, string] {
    const cut = /\s(?:and|&|plus|\+)\s|\s*[,/]\s*/i.exec(words);
    if (!cut) return [words, ''];
    return [words.slice(0, cut.index).trim(), words.slice(cut.index + cut[0].length).trim()];
  }

  function openSplit() {
    splitNames = twoNames(line.words);
    splitError = false;
    splitting = !splitting;
  }

  async function doSplit() {
    splitError = !(await flow.splitLine(index, splitNames));
  }

  /** Remove line: taken out of the recipe, with Undo in the toast (F105). The cursor stays in the
   *  list, on the Remove of the line that took its place. */
  async function remove(button: HTMLElement) {
    const list = button.closest('ul');
    flow.removeLine(index);
    await tick();
    const buttons = list?.querySelectorAll<HTMLElement>('[data-remove-line]');
    (buttons?.[index] ?? buttons?.[index - 1])?.focus();
  }

  /** Add line: the name is given (an ingredient called that is used, else the line asks like any
   *  other), and the focus goes to the line's first choice. */
  async function nameIt() {
    addNameError = !(await flow.nameLine(index, addName));
    if (addNameError) return;
    editing = false;
    await tick();
    rowEl?.querySelector<HTMLElement>('.buttons button')?.focus();
  }

  /** Cancel on a line not named yet: it goes, with nothing to undo, and the cursor goes to the
   *  "Add a line" of its section, which follows it in See all. */
  async function giveUp() {
    const list = rowEl?.closest('ul');
    const ends = list ? [...list.querySelectorAll<HTMLElement>('li.add-line button')] : [];
    const mine = ends.findIndex(
      (b) => !!rowEl && !!(rowEl.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING)
    );
    flow.dropBlank(index);
    await tick();
    if (mine >= 0) list?.querySelectorAll<HTMLElement>('li.add-line button')[mine]?.focus();
  }

  /** Something picked from the list: an ingredient ("Same as"), or a recipe that makes it. */
  function pick(picked: LinePick) {
    picking = false;
    if (picked.kind === 'ingredient') flow.sameAs(index, picked.food);
    else flow.useRecipe(index, picked.recipe);
  }

  /** The words of the button that opened the pick-list: Cancel puts the cursor back on that
   *  button (drawn again when the list closes, so found by its words). */
  let opener: string | null = null;

  function openPick(recipesOnly: boolean) {
    opener = document.activeElement?.textContent?.trim() || null;
    pickingRecipes = recipesOnly;
    picking = true;
  }

  async function closePick() {
    picking = false;
    await tick();
    const back = [...(rowEl?.querySelectorAll<HTMLElement>('button') ?? [])].find(
      (b) => b.textContent?.trim() === opener
    );
    back?.focus();
    opener = null;
  }

  function openChange() {
    picking = false;
    splitting = false;
    changePicking = false;
    changing = !changing;
  }

  /** Change's Pick an ingredient: the same pick-list, for any row. A pick replaces what the row
   *  had; Cancel leaves the row as it was. */
  function changePick(picked: LinePick) {
    changePicking = false;
    changing = false;
    pick(picked);
  }

  /** Change's Edit the name read: the corrected name is matched again (F214). */
  async function changeName(typed: string): Promise<boolean> {
    const done = await flow.renameLine(index, typed, (q) =>
      listFoods({ q, limit: 8 }).then((list) => list.foods)
    );
    if (done === 'empty') return false;
    changing = false;
    // The name is kept, but no ingredient could be looked up: the row keeps what it had.
    if (done === 'offline') toasts.show(RENAME_OFFLINE);
    return true;
  }

  /** What the row (and the rows that took its choice) had before New ingredient: Cancel puts it back. */
  let before: NewIngredientBefore | null = null;

  function makeNew(staple: boolean) {
    before = flow.newIngredientUndoable(index, staple);
    formOpen = true;
    nameError = false;
    source = 'bought';
    madeBy = null;
    choosingRecipe = false;
    recipeError = false;
    keepPlace = undefined;
  }

  /** Where a made-ahead dish usually goes: the Fridge, as the mockup starts it. */
  const keepId = $derived(
    keepPlace ?? placesAndShops.places.find((p) => p.kind === 'fridge')?.id ?? null
  );

  function edit(change: Partial<Extract<Choice, { kind: 'new' | 'staple' }>>) {
    if (made) {
      flow.choose(index, { ...made, ...change });
      for (const at of flow.followers(index)) {
        const other = flow.choices[at];
        if (other && (other.kind === 'new' || other.kind === 'staple'))
          flow.choose(at, { ...other, ...change });
      }
    }
  }

  function doneForm() {
    if (source === 'recipe') {
      if (!madeBy) {
        recipeError = true;
        return;
      }
      flow.useRecipe(index, madeBy.recipe, madeBy.madeAhead ? keepId : null);
      formOpen = false;
      return;
    }
    if (made && !made.name.trim()) {
      nameError = true;
      return;
    }
    nameError = false;
    formOpen = false;
  }

  function cancelForm() {
    formOpen = false;
    if (before) flow.restoreBefore(before);
    else flow.unchoose(index);
    before = null;
  }

  function openEditor() {
    if (!editing) {
      amountText = storedAmount();
      amountError = false;
    }
    editing = !editing;
  }

  /** The amount as it is stored on the line, as the box shows it. */
  function storedAmount(): string {
    return line.amount_text ?? (line.amount === null ? '' : amountWords(line.amount));
  }

  /** Done: a box that couldn't be read goes back to the amount that is stored (the error goes);
   *  Done again closes the boxes. */
  function doneEditor() {
    if (amountError) {
      amountText = storedAmount();
      amountError = false;
      return;
    }
    editing = false;
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

  /** "also called …": the name the line matched by, when it is not the name shown in bold (the
   *  ingredient's own, or on an open line the line's own words): it never repeats it (F103). A
   *  ready line shows the ingredient's name, so "Toor dal · also called thuvaram paruppu" stays. */
  const alsoCalled = $derived.by(() => {
    const matched = line.matched_by;
    if (!matched || !line.food) return null;
    const same = (a: string, b: string) =>
      a.trim().replace(/\s+/g, ' ').toLowerCase() === b.trim().replace(/\s+/g, ' ').toLowerCase();
    return same(matched, line.food.name) || same(matched, name) ? null : matched;
  });
  const followers = $derived(flow.followers(index));
  /** What a new ingredient would be, for the buttons: “Milk”. */
  const guess = $derived(flow.guessFor(index));
  const sharedFrom = $derived(flow.sharedFrom[index]);
</script>

{#if line.kind === 'heading'}
  <li class="heading">
    <h3>{line.words}</h3>
    <OwnRecipeHead {flow} heading={index} />
  </li>
{:else if ownUse}
  <!-- The line that stands for a section made its own recipe (F190): saved as the link to it. -->
  <li class="line ready">
    <span class="dot ready" role="img" aria-label="Ready"></span>
    <div class="main">
      <p class="written"><span class="visually-hidden">As written: </span>{line.written}</p>
      <p class="read">
        <span class="made">Made in its own recipe:</span>
        {ownUse.own.name}
      </p>
    </div>
  </li>
{:else}
  <li
    class="line {status}"
    class:editing={editing || blank}
    class:pints={!!line.pint_ml && flow.offersPints}
    data-added={line.written === '' ? '' : undefined}
    bind:this={rowEl}
  >
    <span class="dot {status}" role="img" aria-label={STATUS_WORDS[status]}></span>
    <div class="main">
      {#if blank}
        <p class="written">Added by you</p>
        <div class="fields">
          <label class="field" for="{uid}-add-name">
            <span>What is it?</span>
            <input
              id="{uid}-add-name"
              class="mw-input"
              type="text"
              maxlength="100"
              autocomplete="off"
              aria-invalid={addNameError ? true : undefined}
              bind:value={addName}
              use:focusOnMount
              onkeydown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void nameIt();
                }
              }}
            />
          </label>
        </div>
        {#if addNameError}<p class="error" role="alert">Type a name.</p>{/if}
      {:else if line.written === ''}
        <p class="written">Added by you</p>
      {:else}
        <p class="written">
          <span class="visually-hidden">As written: </span>{line.written}{pintWords}
        </p>
      {/if}

      {#if !blank}
        <p class="read">
          <span class="what">
            {#if made}
              <span class="made">{made.kind === 'staple' ? 'New staple' : 'New ingredient'}:</span>
            {:else if here}
              <span class="made">Made in this recipe:</span>
            {:else if recipeChoice}
              <span class="made">Made in another recipe:</span>
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
            aria-label="{quantity
              ? `Amount ${quantity}`
              : 'No amount'}. Fix the amount, unit or note"
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
          <!-- Change (F214): on every row, beside what it was read as. -->
          <button
            type="button"
            class="chip-small"
            aria-expanded={changing}
            aria-label="Change: {line.written}"
            onclick={openChange}>Change</button
          >
        </p>
      {/if}

      {#if orText}
        <p class="or-choice">
          <span class="muted">or</span>
          <b>{orText}</b>
          <button
            type="button"
            class="chip-small"
            aria-label="Use this instead: {orText}"
            onclick={() => flow.useAlternative(index)}>Use this instead</button
          >
        </p>
      {/if}

      {#if editing || blank}
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
        {#if blank}
          <p class="done-row">
            <span class="hint">The amount and note can be left empty.</span>
            <span class="two-buttons">
              <button type="button" class="quiet" onclick={giveUp}>Cancel</button>
              <button type="button" class="done" onclick={() => void nameIt()}>Add line</button>
            </span>
          </p>
        {:else}
          <p class="done-row">
            <span class="hint">Tap the amount or note on any line to fix what was read.</span>
            <button type="button" class="done" onclick={doneEditor}>Done</button>
          </p>
        {/if}
      {/if}

      {#if !blank}
        {#if splitting}
          <div class="fields">
            <label class="field" for="{uid}-split-1">
              <span>First ingredient</span>
              <input
                id="{uid}-split-1"
                class="mw-input"
                type="text"
                maxlength="100"
                autocomplete="off"
                bind:value={splitNames[0]}
              />
            </label>
            <label class="field" for="{uid}-split-2">
              <span>Second ingredient</span>
              <input
                id="{uid}-split-2"
                class="mw-input"
                type="text"
                maxlength="100"
                autocomplete="off"
                bind:value={splitNames[1]}
              />
            </label>
          </div>
          {#if splitError}<p class="error" role="alert">Type two different names.</p>{/if}
          <p class="done-row">
            <span class="hint"
              >{line.amount === null
                ? 'Two lines, one for each.'
                : `Each gets no amount: “${quantity} together” goes in its note.`}</span
            >
            <span class="two-buttons">
              <button type="button" class="quiet" onclick={() => (splitting = false)}>Cancel</button
              >
              <button type="button" class="done" onclick={() => void doSplit()}>Split</button>
            </span>
          </p>
        {/if}

        {#if choice && choice.kind === 'ingredient'}
          {#if line.learn_name}
            <p class="hint">
              Adds “{line.learn_name}” as another name for {choice.food.name} when you save.
            </p>
          {/if}
        {:else if made && formOpen}
          <div class="fields">
            <!-- Where it comes from (F188, mockup Dark-NewIngredient08-Phone). -->
            <div class="field wide">
              <span id="{uid}-source">Where does it come from?</span>
              <div class="source" role="radiogroup" aria-labelledby="{uid}-source">
                <button
                  type="button"
                  role="radio"
                  class="radio"
                  aria-checked={source === 'bought'}
                  onclick={() => (source = 'bought')}>Bought</button
                >
                <button
                  type="button"
                  role="radio"
                  class="radio"
                  aria-checked={source === 'recipe'}
                  onclick={() => (source = 'recipe')}>Made in another recipe</button
                >
              </div>
            </div>
            {#if source === 'recipe'}
              <div class="field wide">
                <span>Which recipe makes it?</span>
                {#if madeBy && !choosingRecipe}
                  <p class="made-by">
                    <b>{madeBy.recipe.name}</b>
                    <button type="button" class="chip" onclick={() => (choosingRecipe = true)}
                      >Change</button
                    >
                  </p>
                  <span class="hint"
                    >{madeBy.madeAhead
                      ? 'Made ahead · that recipe says how long it keeps'
                      : 'That recipe isn’t made ahead, so nothing is kept in the pantry.'}</span
                  >
                {:else}
                  <Lazy
                    load={() => import('./PickLine.svelte')}
                    written=""
                    words={made.name}
                    recipesOnly
                    onpick={(picked) => {
                      if (picked.kind === 'recipe') {
                        madeBy = { recipe: picked.recipe, madeAhead: picked.madeAhead };
                        choosingRecipe = false;
                        recipeError = false;
                      }
                    }}
                    oncancel={() => {
                      choosingRecipe = false;
                      // Nothing picked yet: back to Bought.
                      if (!madeBy) source = 'bought';
                    }}
                  />
                {/if}
              </div>
              {#if madeBy && !choosingRecipe && madeBy.madeAhead}
                <div class="field wide">
                  <span id="{uid}-keeps">Pantry keeps it in</span>
                  <div class="source wrap" role="radiogroup" aria-labelledby="{uid}-keeps">
                    {#each placesAndShops.places as place (place.id)}
                      <button
                        type="button"
                        role="radio"
                        class="radio small"
                        aria-checked={keepId === place.id}
                        onclick={() => (keepPlace = place.id)}>{place.name}</button
                      >
                    {/each}
                  </div>
                </div>
              {/if}
              {#if recipeError}<p class="error" role="alert">Pick the recipe that makes it.</p>{/if}
              <span class="hint"
                >No recipe for it yet? Choose <b>Bought</b> for now, or save this one and import the other.</span
              >
            {:else}
              <label class="field" for="{uid}-name">
                <span>Name</span>
                <input
                  id="{uid}-name"
                  class="mw-input"
                  type="text"
                  maxlength="100"
                  aria-invalid={nameError ? true : undefined}
                  value={made.name}
                  oninput={(e) => edit({ name: e.currentTarget.value })}
                />
              </label>
              <label class="field" for="{uid}-how">
                <span>{KEPT_BY}</span>
                <select
                  id="{uid}-how"
                  class="mw-input"
                  aria-describedby="{uid}-how-hint"
                  value={made.counted_as}
                  onchange={(e) => edit({ counted_as: e.currentTarget.value as CountedAs })}
                >
                  {#each COUNTED as option (option.value)}
                    <option value={option.value}>{option.label}</option>
                  {/each}
                </select>
              </label>
              <span class="hint" id="{uid}-how-hint">{KEPT_BY_HINT}</span>
              <label class="field" for="{uid}-place">
                <span>Usually kept in</span>
                <select
                  id="{uid}-place"
                  class="mw-input"
                  value={made.place_id ?? ''}
                  onchange={(e) => {
                    if (e.currentTarget.value === NEW_PLACE) {
                      addingPlace = true;
                      e.currentTarget.value = String(made.place_id ?? '');
                    } else
                      edit({
                        place_id: e.currentTarget.value ? Number(e.currentTarget.value) : null
                      });
                  }}
                >
                  <option value="">Nowhere in particular</option>
                  {#each placesAndShops.places as place (place.id)}
                    <option value={place.id}>{place.name}</option>
                  {/each}
                  <option value={NEW_PLACE}>+ Place</option>
                </select>
              </label>
              {#if addingPlace}
                <NewPlace
                  onadded={(place) => {
                    addingPlace = false;
                    edit({ place_id: place.id });
                  }}
                  oncancel={() => (addingPlace = false)}
                />
              {/if}
            {/if}
          </div>
          {#if source === 'bought'}
            {#if nameError}<p class="error" role="alert">Type a name.</p>{/if}
            <p class="hint">
              {made.kind === 'staple'
                ? 'Made a staple when you save. It never counts towards stock.'
                : 'Made when you save. Nothing is added to the pantry.'}
            </p>
          {/if}
          <div class="done-row">
            {#if source === 'bought'}
              <span class="staple-switch">
                <Switch
                  checked={made.kind === 'staple'}
                  labelledby="{uid}-staple"
                  onchange={(on) => flow.setStaple(index, on)}
                />
                <span id="{uid}-staple">Treat as staple (never counted)</span>
              </span>
            {/if}
            <span class="two-buttons">
              <button type="button" class="quiet" onclick={cancelForm}>Cancel</button>
              <button type="button" class="done" onclick={doneForm}>Done</button>
            </span>
          </div>
        {:else if made}
          <p class="hint">
            {made.kind === 'staple'
              ? 'Made a staple when you save. It never counts towards stock.'
              : 'Made when you save. Nothing is added to the pantry.'}
            {keptBySaid(made.counted_as)} · kept in
            {placesAndShops.places.find((p) => p.id === made.place_id)?.name ??
              'nowhere in particular'}.
          </p>
        {:else if here}
          <p class="hint">
            Made in this recipe: saved as words only, never taken from your pantry.
          </p>
        {:else if recipeChoice}
          <p class="hint">
            Uses the recipe “{recipeChoice.recipe.name}” when you save{recipeChoice.place_id
              ? `, kept in ${placesAndShops.places.find((p) => p.id === recipeChoice.place_id)?.name ?? 'the pantry'}`
              : ''}.
          </p>
        {/if}

        {#if choice && (followers.length > 0 || sharedFrom !== undefined)}
          <p class="also" role="status">
            {#if followers.length > 0}
              Also used for {followers.length} more {plural(followers.length, 'line', 'lines')}: “{followers
                .map((j) => flow.review?.lines[j]?.written)
                .join('”, “')}”
            {:else}
              Same choice as “{flow.review?.lines[sharedFrom!]?.written}” above.
            {/if}
          </p>
        {/if}

        {#if changing}
          {#if changePicking}
            <Lazy
              load={() => import('./PickLine.svelte')}
              written={line.written}
              words={line.words}
              onpick={changePick}
              onnew={() => {
                changePicking = false;
                changing = false;
                makeNew(false);
              }}
              oncancel={() => (changePicking = false)}
            />
          {:else}
            <ChangeLine
              {name}
              words={line.words}
              chosen={!!choice}
              onpick={() => (changePicking = true)}
              onnew={() => {
                changing = false;
                makeNew(false);
              }}
              onname={changeName}
              onback={() => {
                changing = false;
                flow.unchoose(index);
              }}
              oncancel={() => (changing = false)}
            />
          {/if}
        {/if}
        {#if open && !choice}
          {#if picking}
            <Lazy
              load={() => import('./PickLine.svelte')}
              written={line.written}
              words={line.words}
              recipesOnly={pickingRecipes}
              onpick={pick}
              onnew={() => {
                picking = false;
                makeNew(false);
              }}
              oncancel={closePick}
            />
          {:else}
            <p class="buttons">
              {#if hereFirst}
                <button type="button" class="chip primary" onclick={() => flow.madeHere(index)}
                  >Made in this recipe</button
                >
              {/if}
              {#if line.label === 'to_confirm' && line.food}
                <button
                  type="button"
                  class="chip"
                  class:primary={!hereFirst}
                  onclick={() => flow.sameAs(index, line.food!)}>Same as “{line.food.name}”</button
                >
                <button type="button" class="chip" onclick={() => openPick(false)}
                  >Pick another</button
                >
                <button type="button" class="chip" onclick={() => makeNew(false)}
                  >New ingredient</button
                >
              {:else}
                <button
                  type="button"
                  class="chip needs"
                  class:primary={!hereFirst}
                  onclick={() => makeNew(false)}
                  >New ingredient{guess?.name ? ` “${guess.name}”` : ''}</button
                >
                <button type="button" class="chip" onclick={() => openPick(false)}
                  >Pick an ingredient</button
                >
              {/if}
              {#if !hereFirst}
                <button type="button" class="chip" onclick={() => flow.madeHere(index)}
                  >Made in this recipe</button
                >
              {/if}
              <button type="button" class="chip" onclick={() => openPick(true)}
                >Made in another recipe</button
              >
              <button type="button" class="chip" onclick={() => makeNew(true)}
                >Treat as staple</button
              >
            </p>
            {#if line.label === 'to_confirm' && line.food && line.learn_name}
              <p class="hint">
                “Same as” adds “{line.learn_name}” as another name for {line.food.name} when you save.
              </p>
            {/if}
          {/if}
        {/if}
        {#if made && !formOpen}
          <p class="buttons">
            <button
              type="button"
              class="chip"
              onclick={() => {
                before = null; // Cancel then takes the whole New ingredient back, as it always did
                formOpen = true;
              }}>Edit</button
            >
          </p>
        {/if}
        <!-- Optional (R3, F151): "(optional)" in the line, or under "For serving", switches it on;
             the person can switch it either way. Saved with the recipe's line. -->
        <p class="optional-row">
          <Switch
            checked={!!line.optional}
            labelledby="{uid}-optional"
            onchange={(on) => flow.editLine(index, { optional: on })}
          />
          <span id="{uid}-optional">Optional</span>
        </p>
      {/if}
      {#if problem}<p class="error" role="alert">{problem}</p>{/if}
    </div>
    {#if !blank}
      <div class="side">
        <span class="state" class:staple={status === 'staple'}>
          {#if choice}
            {choice.kind === 'ingredient'
              ? 'Same as'
              : choice.kind === 'here'
                ? 'Made here'
                : choice.kind === 'recipe'
                  ? 'Recipe'
                  : choice.kind === 'staple'
                    ? 'New staple'
                    : 'New ingredient'}
          {:else if line.label === 'staple'}
            Staple
          {:else if line.label === 'matched'}
            <Icon name="check" size={14} stroke={2.6} />{line.place ?? 'In your ingredients'}
          {/if}
        </span>
        <button
          type="button"
          class="remove"
          aria-expanded={splitting}
          aria-label="Split into two: {line.written}"
          onclick={openSplit}>Split into two</button
        >
        <button
          type="button"
          class="remove"
          data-remove-line
          aria-label="Remove line: {line.written}"
          onclick={(e) => void remove(e.currentTarget)}>Remove line</button
        >
      </div>
    {/if}
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
    border-radius: var(--radius-button);
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

  .or-choice {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3) var(--space-4);
    align-items: baseline;
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
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

  .optional-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .side {
    display: flex;
    flex: none;
    flex-direction: column;
    gap: var(--space-2);
    align-items: flex-end;
  }

  .remove {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
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

  .chip.primary {
    border-color: transparent;
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
  }

  .chip.primary.needs {
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

  .field.wide {
    grid-column: 1 / -1;
  }

  /* Bought · Made in another recipe, and where the pantry keeps it (F188). */
  .source {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .radio {
    flex: 1 1 9rem;
    min-height: 52px;
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-lg);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .radio.small {
    flex: none;
    min-height: var(--touch-target);
    border-radius: var(--radius-full);
  }

  .radio[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
  }

  .made-by {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    color: var(--color-text);
    font-size: var(--text-lg);
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
