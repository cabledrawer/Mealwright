<script lang="ts">
  // "Add to Dinner · Mon 19": pick a recipe (searched by name, tag or ingredient) or, once
  // something is typed, a plain ingredient ("Fruit") to put in a meal. A meal that already has
  // things gets it alongside. In Month, with no meal chosen, it asks which meal first.
  import { downLine } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import { untrack } from 'svelte';
  import { listFoods } from '#lib/client/foods.js';
  import type { TubLeft } from '#lib/client/plan.js';
  import type { StepWait } from '#lib/timeWords.js';
  import { useByWords } from '#lib/planMeals.js';
  import { cookTargetOf } from '#lib/cookHere.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { tubsForDay, tubsListed } from '#lib/planTubs.js';
  import type { FoodRow } from '#lib/client/types.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull, dayLong, dayOfMonth } from '#lib/planDates.js';
  import { RecipeList } from '#lib/recipes.svelte.js';
  import { timePlusWait } from '#lib/timeWords.js';

  let {
    actions,
    target,
    onclose
  }: {
    actions: PlanActions;
    target: { day: string; slotId: number | null } | null;
    onclose: () => void;
  } = $props();

  const model = $derived(actions.model);
  const recipes = new RecipeList();
  let dialog: HTMLDialogElement;
  let query = $state('');
  let foods = $state<FoodRow[]>([]);
  let slotId = $state<number | null>(null);
  let problem = $state<string | null>(null);
  let asked = 0;
  // A note ("Eating out", "At Amma’s"; 0.7 P1) instead of a recipe or an ingredient.
  let noting = $state(false);
  let noteText = $state('');
  // "Cook once here…" (F52): the recipe picked is planned in this meal and Cook once opens for it.
  let cooking = $state(false);

  $effect(() => {
    if (target !== null && !dialog.open) dialog.showModal();
    else if (target === null && dialog.open) dialog.close();
  });

  // A new target starts again: nothing typed, its meal (or none yet).
  $effect(() => {
    if (!target) return;
    const wanted = target.slotId;
    untrack(() => {
      query = '';
      foods = [];
      noting = false;
      noteText = '';
      cooking = false;
      allTubs = false;
      slotId = wanted ?? (model.slotsOn.length === 1 ? (model.slotsOn[0]?.id ?? null) : null);
      recipes.query = '';
      void recipes.load();
    });
  });

  // Typing: ask again shortly after the last key.
  $effect(() => {
    const typed = query.trim();
    if (!target) return;
    const timer = setTimeout(() => {
      const mine = ++asked;
      recipes.query = typed;
      void recipes.load();
      if (!typed) {
        foods = [];
        return;
      }
      listFoods({ q: typed, limit: 8 })
        .then((list) => {
          if (mine === asked) {
            foods = list.foods;
            problem = null;
          }
        })
        .catch(() => {
          if (mine === asked) problem = 'Couldn’t look up ingredients. Try again.';
        });
    }, 200);
    return () => clearTimeout(timer);
  });

  // F127 (cabledrawer's words, proposed 2 Nov): before a meal is picked, small "Pick a meal, then
  // what to add" over the full day; after, small "Add to" over "Dinner · Wednesday 11". The
  // small line is what explains the greyed recipes.
  const heading = $derived(
    !target
      ? { sub: '', title: '' }
      : slotId === null
        ? { sub: 'Pick a meal, then what to add', title: dayFull(target.day) }
        : {
            sub: 'Add to',
            title: `${model.slotName(slotId)} · ${dayLong(target.day)} ${dayOfMonth(target.day)}`
          }
  );

  function pick(what: Parameters<typeof model.add>[0]) {
    if (!target || slotId === null || actions.readonly) return;
    void model.add(what, target.day, slotId);
    onclose();
  }

  /** Quick notes, so the common ones are one tap (words proposed, for cabledrawer). */
  const QUICK_NOTES = ['Eating out', 'Takeaway'];

  const noteReady = $derived(
    noteText.trim().length > 0 && slotId !== null && !actions.readonly && target !== null
  );

  function addNote(text: string) {
    const clean = text.trim();
    if (!target || slotId === null || actions.readonly || !clean) return;
    void model.addNote(clean, target.day, slotId);
    onclose();
  }

  let allTubs = $state(false);

  /** The tubs this day offers: the oldest freezer tub first; fridge tubs past their use-by left out. */
  const offer = $derived(tubsForDay(model.tubsLeft, target?.day ?? ''));
  const listed = $derived(tubsListed(offer.tubs, allTubs));

  /** Cook once here: the recipe buttons wait while the recipe is being planned (no second plan). */
  let planning = $state(false);

  /** Plan the recipe in this meal, then open Cook once for it from what the add answered. */
  async function cookHere(recipe: {
    id: number;
    name: string;
    optional_count?: number;
    method_count?: number;
    wait?: StepWait | null;
  }) {
    if (!target || slotId === null || actions.readonly || planning) return;
    const [day, slot] = [target.day, slotId];
    planning = true;
    try {
      const outcome = await model.add({ recipe }, day, slot);
      if (!outcome.ok) return; // the failure has said why (a toast), and this sheet stays open
      // A late answer: the sheet was closed or opened on another day or meal meanwhile, so it acts on
      // nothing (the recipe stays planned; Undo is in the toast).
      if (target?.day !== day || slotId !== slot) return;
      onclose();
      const next = cookTargetOf(outcome.value, day, slot, recipe);
      if (next) actions.openCookOnce(next.meal, next.item);
      else
        toasts.show(
          `Planned ${recipe.name}, but Cook once didn’t open. Open its menu to try again.`,
          {
            tone: 'problem'
          }
        ); // proposed, for cabledrawer
    } finally {
      planning = false;
    }
  }

  function putTub(tub: TubLeft) {
    if (!target || slotId === null || actions.readonly) return;
    void model.placeTub(tub.id, `${tub.recipe_name} tub`, target.day, slotId);
    onclose();
  }

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === dialog) onclose();
  }
</script>

<dialog
  bind:this={dialog}
  aria-label="Add to the plan"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={closeOnBackdrop}
  data-testid="plan-add"
>
  {#if target}
    <div class="body">
      <span class="handle" aria-hidden="true"></span>
      <header>
        <p class="sub">{heading.sub}</p>
        <h2>{heading.title}</h2>
      </header>

      {#if slotId === null || model.slotsOn.length > 1}
        <div class="slots" role="group" aria-label="Meal">
          {#each model.slotsOn as slot (slot.id)}
            <button
              type="button"
              aria-pressed={slotId === slot.id}
              onclick={() => (slotId = slot.id)}>{slot.name}</button
            >
          {/each}
        </div>
      {/if}

      {#if noting}
        <form
          class="note-form"
          onsubmit={(event) => {
            event.preventDefault();
            addNote(noteText);
          }}
        >
          <input
            type="text"
            class="find"
            maxlength="200"
            placeholder="Eating out, takeaway, at Amma’s"
            aria-label="Note"
            bind:value={noteText}
          />
          <div class="quick">
            {#each QUICK_NOTES as quick (quick)}
              <button
                type="button"
                disabled={slotId === null || actions.readonly || planning}
                onclick={() => addNote(quick)}>{quick}</button
              >
            {/each}
          </div>
          <div class="pair">
            <button type="button" class="quiet" onclick={() => (noting = false)}>Back</button>
            <button type="submit" class="go" disabled={!noteReady}>Add note</button>
          </div>
        </form>
      {:else}
        <input
          type="search"
          class="find"
          placeholder="Find a recipe or an ingredient"
          aria-label="Find a recipe or an ingredient"
          bind:value={query}
        />
        <div class="extras">
          {#if !cooking}
            <button type="button" class="add-note" onclick={() => (noting = true)}>+ Note</button>
          {/if}
          <button
            type="button"
            class="add-note"
            disabled={actions.readonly}
            onclick={() => (cooking = !cooking)}>{cooking ? 'Back' : 'Cook once here…'}</button
          >
        </div>
        {#if cooking}
          <p class="note" role="status">Pick the recipe to cook once here.</p>
        {/if}
      {/if}

      {#if actions.readonly}
        <p class="note" role="status">
          {downLine(network.deviceOffline, (b) => `Plan changes ${b.when}.`)}
        </p>
      {/if}
      {#if problem}<p class="note problem" role="alert">{problem}</p>{/if}

      {#if !noting && !cooking && offer.tubs.length && !query.trim()}
        <h3 class="group">Use a tub</h3>
        <ul class="results" aria-label="Tubs left">
          {#each listed.shown as tub (tub.id)}
            <li>
              <button
                type="button"
                disabled={slotId === null || actions.readonly || planning}
                onclick={() => putTub(tub)}
              >
                <span class="name">{tub.recipe_name} · tub {tub.number} of {tub.tub_count}</span>
                <span class="meta"
                  >{tub.place_kind === 'freezer' ? 'Freezer' : 'Fridge'} · {useByWords(
                    tub.use_by,
                    model.today
                  )}</span
                >
              </button>
            </li>
          {/each}
        </ul>
        {#if listed.hidden > 0}
          <button type="button" class="add-note" onclick={() => (allTubs = true)}
            >+{listed.hidden} more tubs</button
          >
        {/if}
        {#if offer.pastUseBy > 0}
          <p class="none">Fridge tubs that are past their use-by by then aren’t offered.</p>
        {/if}
      {/if}

      {#if !noting}
        <ul class="results" aria-label="Results">
          {#each recipes.recipes.slice(0, 12) as recipe (recipe.id)}
            <li>
              <button
                type="button"
                disabled={slotId === null || actions.readonly || planning}
                onclick={() =>
                  cooking
                    ? void cookHere({
                        id: recipe.id,
                        name: recipe.name,
                        optional_count: recipe.optional_count,
                        method_count: recipe.method_count,
                        wait: recipe.wait
                      })
                    : pick({
                        recipe: {
                          id: recipe.id,
                          name: recipe.name,
                          optional_count: recipe.optional_count,
                          method_count: recipe.method_count,
                          wait: recipe.wait
                        }
                      })}
              >
                <span class="name">{recipe.name}</span>
                <span class="meta"
                  >{[
                    timePlusWait(recipe.time_minutes, recipe.wait),
                    recipe.kcal != null ? `${recipe.kcal} kcal` : ''
                  ]
                    .filter(Boolean)
                    .join(' · ')}</span
                >
              </button>
            </li>
          {/each}
          {#each cooking ? [] : foods as food (food.id)}
            <li>
              <button
                type="button"
                disabled={slotId === null || actions.readonly || planning}
                onclick={() => pick({ ingredient: { id: food.id, name: food.name } })}
              >
                <span class="name">{food.name}</span>
                <span class="meta">Ingredient</span>
              </button>
            </li>
          {/each}
        </ul>
        {#if recipes.loaded && !recipes.recipes.length && !foods.length}
          <p class="none">
            {query.trim() ? 'Nothing matches.' : 'You have no recipes yet. Add one under Recipes.'}
          </p>
        {:else if !query.trim() && !cooking}
          <p class="none">Type to find an ingredient, such as Fruit.</p>
        {/if}
      {/if}

      <button type="button" class="close" onclick={onclose}>Close</button>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    overscroll-behavior: contain;
    scrollbar-width: none;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  header {
    text-align: center;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: break-word;
  }

  .slots {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .slots button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .slots button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .find {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-size: 1rem; /* 16 px: a phone does not zoom into it */
  }

  .results {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .results button {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-3) var(--space-6);
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .results button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: break-word;
  }

  .meta,
  .none {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .note {
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

  .close {
    min-height: 54px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-fill-strong);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      max-height: min(720px, calc(100dvh - 80px));
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(480px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }
    .handle {
      display: none;
    }
  }

  .add-note {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-accent);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .extras {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .add-note:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .note-form {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .quick,
  .pair {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .quick button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .pair .quiet,
  .pair .go {
    min-height: 54px;
    border: none;
    border-radius: var(--radius-button);
    font: inherit;
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .pair .quiet {
    padding: 0 var(--space-8);
    background: var(--color-fill-strong);
    color: var(--color-text);
  }

  .pair .go {
    flex: 1;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .quick button:disabled,
  .pair .go:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .group {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    color: var(--color-text-muted);
  }
</style>
