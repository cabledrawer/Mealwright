<script lang="ts">
  // "Add to Dinner · Mon 19": pick a recipe (searched by name, tag or ingredient) or, once
  // something is typed, a plain ingredient ("Fruit") to put in a meal. A meal that already has
  // things gets it alongside. In Month, with no meal chosen, it asks which meal first.
  import { untrack } from 'svelte';
  import { listFoods } from '#lib/client/foods.js';
  import type { FoodRow } from '#lib/client/types.js';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayFull } from '#lib/planDates.js';
  import { RecipeList } from '#lib/recipes.svelte.js';

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

  const where = $derived(
    target ? `${slotId === null ? 'a meal' : model.slotName(slotId)} · ${dayFull(target.day)}` : ''
  );

  function pick(what: Parameters<typeof model.add>[0]) {
    if (!target || slotId === null || actions.readonly) return;
    void model.add(what, target.day, slotId);
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
        <p class="sub">Add to</p>
        <h2>{where}</h2>
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

      <input
        type="search"
        class="find"
        placeholder="Find a recipe or an ingredient"
        aria-label="Find a recipe or an ingredient"
        bind:value={query}
      />

      {#if actions.readonly}
        <p class="note" role="status">You’re offline. Plan changes when you’re back online.</p>
      {/if}
      {#if problem}<p class="note problem" role="alert">{problem}</p>{/if}

      <ul class="results" aria-label="Results">
        {#each recipes.recipes.slice(0, 12) as recipe (recipe.id)}
          <li>
            <button
              type="button"
              disabled={slotId === null || actions.readonly}
              onclick={() => pick({ recipe: { id: recipe.id, name: recipe.name } })}
            >
              <span class="name">{recipe.name}</span>
              <span class="meta"
                >{[
                  recipe.time_minutes ? `${recipe.time_minutes} min` : '',
                  recipe.kcal != null ? `${recipe.kcal} kcal` : ''
                ]
                  .filter(Boolean)
                  .join(' · ')}</span
              >
            </button>
          </li>
        {/each}
        {#each foods as food (food.id)}
          <li>
            <button
              type="button"
              disabled={slotId === null || actions.readonly}
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
      {:else if !query.trim()}
        <p class="none">Type to find an ingredient, such as Fruit.</p>
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
    overflow-wrap: anywhere;
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
    overflow-wrap: anywhere;
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
</style>
