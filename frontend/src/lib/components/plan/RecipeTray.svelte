<script lang="ts">
  // The recipe tray (mockup Desktop-Plan): a slim strip under the plan, collapsible. Drag a recipe
  // up onto a day to plan it; or click it (or press Enter) to choose the day and meal from a
  // menu. Filters are the ones All recipes has: Can cook now, Use soon.
  import type { TubLeft } from '#lib/client/plan.js';
  import type { RecipeRow } from '#lib/client/recipes.js';
  import { colourOfBatch, useByWords } from '#lib/planMeals.js';
  import type { Carried } from '#lib/planDrag.svelte.js';
  import { pressable } from '#lib/planDrag.svelte.js';
  import type { RecipeFilter, RecipeList } from '#lib/recipes.svelte.js';

  let {
    list,
    disabled,
    open,
    onopen,
    carry,
    onchoose,
    tubs = [],
    today = '',
    carryTub,
    onchooseTub
  }: {
    list: RecipeList;
    disabled: boolean;
    open: boolean;
    onopen: (open: boolean) => void;
    carry: (recipe: RecipeRow) => Carried;
    onchoose: (recipe: RecipeRow) => void;
    /** Tubs in no meal ("Tubs left"): they can be dragged onto a meal like a recipe. */
    tubs?: TubLeft[];
    today?: string;
    carryTub?: (tub: TubLeft) => Carried;
    onchooseTub?: (tub: TubLeft) => void;
  } = $props();

  const FILTERS: { value: RecipeFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'cook', label: 'Can cook now' },
    { value: 'soon', label: 'Use soon' }
  ];

  function setFilter(filter: RecipeFilter) {
    list.filter = filter;
    void list.load();
  }

  // Typing in "Find a recipe": ask again shortly after the last key.
  let typed = $state('');
  let first = true;
  $effect(() => {
    const words = typed;
    if (first) {
      first = false;
      return;
    }
    const timer = setTimeout(() => {
      list.query = words;
      void list.load();
    }, 200);
    return () => clearTimeout(timer);
  });
</script>

<section class="tray" class:closed={!open} aria-label="Recipe tray">
  <div class="top">
    <h2>Recipes <span class="hint">· drag up onto a day</span></h2>
    {#if open}
      <input
        type="search"
        class="find"
        placeholder="Find a recipe"
        aria-label="Find a recipe to plan"
        bind:value={typed}
      />
      <div class="chips" role="group" aria-label="Show">
        {#each FILTERS as f (f.value)}
          <button
            type="button"
            aria-pressed={list.filter === f.value}
            onclick={() => setFilter(f.value)}>{f.label}</button
          >
        {/each}
      </div>
    {/if}
    <button
      type="button"
      class="toggle"
      aria-expanded={open}
      aria-label={open ? 'Collapse recipe tray' : 'Open recipe tray'}
      title={open ? 'Collapse tray' : 'Open tray'}
      onclick={() => onopen(!open)}>{open ? '⌄' : '⌃'}</button
    >
  </div>
  {#if open}
    {#if list.problem}
      <p class="none" role="alert">{list.problem}</p>
    {:else if list.loaded && !list.recipes.length}
      <p class="none">
        {list.filter === 'all'
          ? 'You have no recipes yet. Add one under Recipes.'
          : 'No recipes match.'}
      </p>
    {:else}
      {#if tubs.length && carryTub && onchooseTub}
        <ul class="strip" aria-label="Tubs left">
          <li class="label">Tubs left</li>
          {#each tubs as tub (tub.id)}
            {@const n = colourOfBatch({ id: tub.batch_id, colour: tub.colour })}
            <li>
              <button
                type="button"
                class="recipe tubleft"
                {disabled}
                style:--soft="var(--batch-{n}-soft)"
                style:--soft-text="var(--batch-{n}-soft-text)"
                use:pressable={{
                  carry: disabled ? null : () => carryTub(tub),
                  open: () => onchooseTub(tub)
                }}
                aria-label="{tub.recipe_name}, tub {tub.number} of {tub.tub_count}. Choose a meal for it"
              >
                <span class="text">
                  <span class="name">{tub.recipe_name} · tub {tub.number}</span>
                  <span class="meta"
                    >{tub.place_kind === 'freezer' ? 'Freezer' : 'Fridge'} · {useByWords(
                      tub.use_by,
                      today
                    )}</span
                  >
                </span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
      <ul class="strip" aria-label="Recipes to plan">
        {#each list.recipes as recipe (recipe.id)}
          <li>
            <button
              type="button"
              class="recipe"
              {disabled}
              use:pressable={{
                carry: disabled ? null : () => carry(recipe),
                open: () => onchoose(recipe)
              }}
              aria-label="{recipe.name}. Choose a day to plan it"
            >
              {#if recipe.photo}
                <img src={recipe.photo.list_url} alt="" width="40" height="40" loading="lazy" />
              {:else}
                <span class="square" aria-hidden="true"></span>
              {/if}
              <span class="text">
                <span class="name">{recipe.name}</span>
                <span class="meta"
                  >{recipe.use_soon
                    ? 'Uses ' + (recipe.use_soon.foods[0]?.name ?? 'something to use soon')
                    : recipe.time_minutes
                      ? `${recipe.time_minutes} min`
                      : ''}</span
                >
              </span>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</section>

<style>
  .tray {
    flex: none;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-5) var(--space-6);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .top {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    flex-wrap: wrap;
  }

  h2 {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .chips {
    display: flex;
    gap: var(--space-3);
  }

  .find {
    width: 180px;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-size: 1rem; /* 16 px: a phone does not zoom into it */
  }

  .chips button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .chips button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }

  .toggle {
    margin-left: auto;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text-soft);
    font: inherit;
    font-size: var(--text-3xl);
    cursor: pointer;
  }

  .strip {
    display: flex;
    gap: var(--space-4);
    margin: 0;
    padding: 0 0 var(--space-2);
    list-style: none;
    overflow-x: auto;
    scrollbar-width: none;
  }

  .strip li {
    flex: 0 0 196px;
  }

  .recipe {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: grab;
    user-select: none;
    -webkit-user-select: none;
    -webkit-touch-callout: none;
  }

  /* The strip scrolls sideways with a finger; a recipe is picked up only after a long press. */
  .recipe:not(:disabled) {
    touch-action: pan-x pan-y;
  }

  .recipe:disabled {
    opacity: 0.5;
    cursor: default;
  }

  img,
  .square {
    flex: none;
    width: 40px;
    height: 40px;
    border-radius: var(--radius-sm);
    object-fit: cover;
  }

  .square {
    background: var(--color-recipe-square);
  }

  .text {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .meta {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .none {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .label {
    align-self: center;
    flex: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .tubleft {
    background: var(--soft);
    color: var(--soft-text);
  }
</style>
