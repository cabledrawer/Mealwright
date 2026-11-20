<script lang="ts" module>
  import type { Ref } from '#lib/client/types.js';

  /** What was picked for a line: an ingredient, or a recipe that makes it. */
  export type LinePick =
    { kind: 'ingredient'; food: Ref } | { kind: 'recipe'; recipe: Ref; madeAhead: boolean };
</script>

<script lang="ts">
  // "What is “Dosa batter”?" (F187-F189, mockup Dark-CheckPick08-Phone): the pick-list for a line
  // on Check. It searches the household's ingredients and recipes by what was typed; when a recipe
  // and an ingredient share a name the recipe comes first, each labelled Recipe or Ingredient.
  // "New ingredient" and "Made in another recipe…" (the same list, recipes only) are under it.
  // Used by a line's Pick an ingredient and Made in another recipe, and by the Save walk-through.
  // Loaded the first time it is used, so the import page stays small. Words are the mockup's,
  // except where marked proposed, for cabledrawer.
  import Button from '#lib/components/Button.svelte';
  import type { FoodRow } from '#lib/client/types.js';
  import type { RecipeBrief } from '#lib/client/recipes.js';
  import { arrange, lineSearch, recipeSearch } from '#lib/recipes/search.js';

  let {
    written,
    words,
    recipesOnly = false,
    onpick,
    onnew,
    oncancel
  }: {
    /** The line as written ("Dosa batter, as above · 4 cups"); empty for a line added by hand. */
    written: string;
    /** The line's words: the search starts with them. */
    words: string;
    /** Start with recipes only (a line's "Made in another recipe"). */
    recipesOnly?: boolean;
    onpick: (pick: LinePick) => void;
    /** "New ingredient"; left out where the list has no such button. */
    onnew?: () => void;
    oncancel: () => void;
  } = $props();

  const uid = $props.id();
  // The two ways of looking are the person's to switch, so they start from the prop only.
  // svelte-ignore state_referenced_locally
  let onlyRecipes = $state(recipesOnly);
  // svelte-ignore state_referenced_locally
  let query = $state(words);
  let foods = $state<FoodRow[]>([]);
  let recipes = $state<RecipeBrief[]>([]);
  /** The text the answer on show is for. */
  let answered = $state<string | null>(null);
  let failed = $state(false);
  let asked = 0;

  const findBoth = lineSearch();
  const findRecipes = recipeSearch();
  const typed = $derived(query.trim());
  const rows = $derived(arrange(onlyRecipes ? [] : foods, recipes));
  const anyPaired = $derived(rows.some((row) => row.paired));
  const current = $derived(answered === typed);

  $effect(() => {
    const q = typed;
    const recipesOnlyNow = onlyRecipes;
    const mine = ++asked;
    if (!q) {
      foods = [];
      recipes = [];
      answered = '';
      failed = false;
      return;
    }
    const timer = setTimeout(() => {
      (recipesOnlyNow
        ? findRecipes(q).then((found) => ({ foods: [] as FoodRow[], recipes: found }))
        : findBoth(q)
      )
        .then((found) => {
          if (mine !== asked) return;
          foods = found.foods.slice(0, 6);
          recipes = found.recipes;
          answered = q;
          failed = false;
        })
        .catch(() => {
          if (mine === asked) failed = true;
        });
    }, 150);
    return () => clearTimeout(timer);
  });

  function focusOnShow(node: HTMLElement) {
    node.focus();
  }

  const makes = (r: RecipeBrief) =>
    [
      r.made_ahead ? 'Made ahead' : 'Recipe',
      r.makes ? `makes ${r.makes.amount_text}\u00a0${r.makes.unit}` : ''
    ]
      .filter(Boolean)
      .join(' · ');

  function foodSub(food: FoodRow): string {
    const other =
      food.matched_name && food.matched_name !== food.name
        ? food.matched_name
        : food.other_names[0];
    return [other ? `also called ${other}` : '', food.place?.name ?? '']
      .filter(Boolean)
      .join(' · ');
  }

  /** Enter: the first row, only once the list answers what is typed now (a slow answer for
   *  fewer letters could link the wrong thing). */
  function pickFirst() {
    if (!current) return;
    const first = rows[0];
    if (!first) return;
    if (first.kind === 'ingredient') {
      onpick({ kind: 'ingredient', food: { id: first.food.id, name: first.food.name } });
    } else {
      onpick({
        kind: 'recipe',
        recipe: { id: first.recipe.id, name: first.recipe.name },
        madeAhead: !!first.recipe.made_ahead
      });
    }
  }
</script>

<div class="pick" role="group" aria-labelledby="{uid}-title">
  <div class="head">
    <h3 id="{uid}-title">{words ? `What is “${words}”?` : 'What is it?'}</h3>
    {#if written}<p class="muted">As written: {written}</p>{/if}
  </div>
  <input
    type="search"
    aria-label={onlyRecipes ? 'Search recipes' : 'Search'}
    aria-controls="{uid}-list"
    autocomplete="off"
    bind:value={query}
    use:focusOnShow
    onkeydown={(event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        oncancel();
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        pickFirst();
      }
    }}
  />
  {#if failed}<p class="error" role="alert">Couldn’t search. Try again.</p>{/if}
  <ul
    id="{uid}-list"
    aria-label={onlyRecipes ? 'Matching recipes' : 'Matching ingredients and recipes'}
  >
    {#each rows as row (row.kind === 'ingredient' ? `f${row.food.id}` : `r${row.recipe.id}`)}
      <li>
        {#if row.kind === 'ingredient'}
          <button
            type="button"
            onclick={() =>
              onpick({ kind: 'ingredient', food: { id: row.food.id, name: row.food.name } })}
          >
            <span class="text">
              <b>{row.food.name}</b>
              {#if foodSub(row.food)}<span class="sub">{foodSub(row.food)}</span>{/if}
            </span>
            {#if row.paired}<span class="kind">Ingredient</span>{/if}
          </button>
        {:else}
          <button
            type="button"
            onclick={() =>
              onpick({
                kind: 'recipe',
                recipe: { id: row.recipe.id, name: row.recipe.name },
                madeAhead: !!row.recipe.made_ahead
              })}
          >
            <span class="text">
              <b>{row.recipe.name}</b>
              <span class="sub">{makes(row.recipe)}</span>
            </span>
            {#if row.paired}<span class="kind recipe">Recipe</span>{/if}
          </button>
        {/if}
      </li>
    {/each}
  </ul>
  <p class="visually-hidden" role="status">
    {#if current && typed}{rows.length === 0
        ? 'No matches'
        : rows.length === 1
          ? '1 match'
          : `${rows.length} matches`}{/if}
  </p>
  {#if anyPaired}
    <p class="muted">When a recipe and an ingredient share a name, the recipe comes first.</p>
  {/if}
  {#if !onlyRecipes && onnew}
    <div class="two">
      <Button quiet small onclick={onnew}>+ New ingredient</Button>
      <Button quiet small onclick={() => (onlyRecipes = true)}>Made in another recipe…</Button>
    </div>
  {:else if onlyRecipes && current && typed && rows.length === 0}
    <p class="muted">No recipe has that name. Import or write it first, then come back.</p>
  {/if}
  <Button quiet small onclick={oncancel}>Cancel</Button>
</div>

<style>
  .pick {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    width: 100%;
    padding: var(--space-5);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-ground);
  }

  h3 {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  input {
    min-height: 48px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  ul {
    margin: 0;
    padding: 0 var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    list-style: none;
  }

  ul:empty {
    display: none;
  }

  li + li {
    border-top: 1px solid var(--color-divider);
  }

  li button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
    width: 100%;
    min-height: 56px;
    padding: var(--space-3) 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .text b {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .kind {
    flex: none;
    padding: 2px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    white-space: nowrap;
  }

  .kind.recipe {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .two {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--space-3);
  }
</style>
