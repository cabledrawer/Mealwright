<script lang="ts">
  // Ingredients (mockups Ingredients-Phone, Ingredients-Desktop): every food, searchable
  // by any name, with the editor. Desktop shows the editor beside the list; phones open
  // it as a sheet. Recipe counts and "Not in any recipe" wait for recipes (0.4).
  import { browser } from '$app/environment';
  import { serverUndo } from '$lib/client/changes';
  import { mergeFood } from '$lib/client/foods';
  import type { FoodFilter, FoodRow, FoodWrite } from '$lib/client/types';
  import Icon from '$lib/components/Icon.svelte';
  import IngredientEditor from '$lib/components/IngredientEditor.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { kitchen } from '$lib/freshness.svelte';
  import { ingredientEditor } from '$lib/ingredientEditor.svelte';
  import { IngredientsList } from '$lib/ingredients.svelte';
  import { save } from '$lib/save';

  const list = new IngredientsList();
  let selectedId = $state<number | null>(null);
  let panelName = $state('');

  const FILTERS: { value: FoodFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'staples', label: 'Staples' }
  ];

  const isDesktop = () => browser && matchMedia('(min-width: 768px)').matches;

  // Search as you type (after a short pause), and fetch again whenever something changed.
  $effect(() => {
    void list.query;
    void list.filter;
    void kitchen.version;
    const timer = setTimeout(() => void list.load(), list.loaded ? 200 : 0);
    return () => clearTimeout(timer);
  });

  // Desktop starts with the first food open, as in the mockup.
  $effect(() => {
    if (selectedId === null && list.foods[0] && isDesktop()) selectedId = list.foods[0].id;
  });

  // Back to the tab after a while: fetch again (live updates come in 0.3).
  function onVisible() {
    if (document.visibilityState === 'visible') void list.load();
  }

  /** The quiet line under a food's name. */
  function note(food: FoodRow, phone: boolean): string {
    const maybe = food.maybe_same[0];
    if (maybe) return `Maybe the same as “${maybe.name}”`;
    if (phone) return [food.counted_as_display, food.place?.name].filter(Boolean).join(' · ');
    if (food.matched_name && food.matched_name !== food.name) return `also: ${food.matched_name}`;
    if (food.other_names.length) return `also: ${food.other_names.join(', ')}`;
    const standIn = food.stand_ins[0];
    if (standIn) return `${standIn.name.toLocaleLowerCase()} can stand in`;
    return '';
  }

  function open(food: FoodRow) {
    // Desktop edits beside the list; phones get the sheet.
    if (isDesktop()) selectedId = food.id;
    else ingredientEditor.open(food.id);
  }

  /** "Merge" on a Maybe-the-same row: into the food it may be. Undo, not "Are you sure?". */
  function merge(food: FoodRow) {
    const into = food.maybe_same[0];
    if (!into) return;
    let undoer: (() => Promise<string | void>) | null = null;
    const before = list.foods;
    void save<FoodWrite>({
      apply: () => (list.foods = list.foods.filter((f) => f.id !== food.id)),
      rollback: () => (list.foods = before),
      send: (key, answers) => mergeFood(food.id, into.id, key, answers),
      saved: (result) => {
        if (selectedId === food.id) selectedId = result.food.id;
        kitchen.changed();
      },
      undo: {
        label: `Merged ${food.name} into ${into.name}`,
        labelFrom: (result) => result.change.summary,
        run: (result) => (undoer ??= serverUndo(result.change.id))()
      }
    });
  }
</script>

<svelte:document onvisibilitychange={onVisible} />

<PageHeader
  title="Ingredients"
  parent={{ href: '/recipes', label: 'Recipes' }}
  subtitle={list.loaded
    ? `${list.counts.all} ${list.counts.all === 1 ? 'food' : 'foods'} · shared by recipes, pantry and shopping`
    : undefined}
/>

<div class="layout">
  <section class="list-side" aria-label="All ingredients">
    <div class="tools">
      <label class="search">
        <Icon name="search" size={18} stroke={2.2} />
        <input
          type="search"
          placeholder="Search by any name, e.g. arhar dal"
          aria-label="Search ingredients"
          bind:value={list.query}
        />
      </label>
      <div class="filters" role="group" aria-label="Show">
        {#each FILTERS as f (f.value)}
          <button
            type="button"
            class="filter"
            aria-pressed={list.filter === f.value}
            onclick={() => (list.filter = f.value)}>{f.label}</button
          >
        {/each}
        {#if list.counts.maybe_same || list.filter === 'maybe_same'}
          <button
            type="button"
            class="filter maybe"
            aria-pressed={list.filter === 'maybe_same'}
            onclick={() => (list.filter = list.filter === 'maybe_same' ? 'all' : 'maybe_same')}
            >Maybe the same · {list.counts.maybe_same}</button
          >
        {/if}
      </div>
    </div>

    <div class="card">
      <div class="heads" aria-hidden="true">
        <span>Ingredient</span><span>Counted as</span><span>Lives in</span><span></span>
      </div>
      {#if list.foods.length}
        <ul>
          {#each list.foods as food (food.id)}
            {@const maybe = food.maybe_same.length > 0}
            {@const desk = note(food, false)}
            <li class:maybe class:open={food.id === selectedId}>
              <button
                type="button"
                class="row"
                aria-current={food.id === selectedId ? 'true' : undefined}
                onclick={() => open(food)}
              >
                <span class="name">{food.name}</span>
                <span class="note phone">{note(food, true)}</span>
                {#if desk}<span class="note desk">{desk}</span>{/if}
              </button>
              <span class="col">
                {#if food.staple}<span class="staple">Staple</span
                  >{:else}{food.counted_as_display}{/if}
              </span>
              <span class="col">{food.place?.name ?? ''}</span>
              <span class="end">
                {#if maybe}
                  <button type="button" class="merge" onclick={() => merge(food)}>Merge</button>
                {/if}
              </span>
            </li>
          {/each}
        </ul>
        {#if list.next}
          <button type="button" class="more" onclick={() => void list.more()}>Show more</button>
        {/if}
      {:else if list.problem}
        <p class="nothing" role="alert">{list.problem}</p>
      {:else if !list.loaded}
        <p class="nothing">Loading…</p>
      {:else if list.query.trim()}
        <p class="nothing">No ingredient called “{list.query.trim()}” yet.</p>
      {:else if list.filter !== 'all'}
        <p class="nothing">Nothing here right now.</p>
      {:else}
        <p class="nothing">
          No ingredients yet. They're added when you put something in the pantry or import a recipe.
        </p>
      {/if}
    </div>

    <p class="tip">
      You can also tap any ingredient in a recipe, the pantry or the shopping list to open this same
      editor.
    </p>
  </section>

  {#if selectedId !== null}
    <aside class="panel" aria-label={panelName ? `Edit ${panelName.toLocaleLowerCase()}` : 'Edit'}>
      {#key selectedId}
        <IngredientEditor
          foodId={selectedId}
          variant="panel"
          onname={(n) => (panelName = n)}
          onclose={() => (selectedId = null)}
          onopen={(id) => (selectedId = id)}
        />
      {/key}
    </aside>
  {/if}
</div>

<style>
  .layout {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--space-9);
  }

  .list-side {
    display: flex;
    flex: 999 1 480px;
    flex-direction: column;
    gap: var(--space-7);
    min-width: 0;
  }

  .tools {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-5);
  }

  .search {
    display: flex;
    flex: 1 1 260px;
    align-items: center;
    gap: var(--space-4);
    min-height: 48px;
    padding: 0 14px;
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text-muted);
  }

  .search:focus-within {
    outline: 2px solid var(--color-focus);
    outline-offset: 1px;
  }

  .search input {
    flex: 1;
    min-width: 0;
    min-height: 44px;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .search input:focus {
    outline: none;
  }

  .filters {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .filter {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .filter[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }

  .filter.maybe {
    border-color: var(--color-maybe-chip-border);
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
    font-weight: var(--weight-bold);
  }

  .filter.maybe[aria-pressed='true'] {
    outline: 2px solid var(--color-maybe-chip-text);
    outline-offset: -2px;
  }

  .card {
    padding: var(--space-1) 14px;
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 60px;
    margin: 0 -14px;
    padding: 0 14px;
    border-bottom: 1px solid var(--color-divider);
  }

  li:last-child {
    border-bottom: none;
  }

  .row {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
    min-width: 0;
    padding: var(--space-4) 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
  }

  /* The whole row opens the editor. */
  .row::after {
    content: '';
    position: absolute;
    inset: 0;
  }

  .row:focus-visible {
    outline: none;
  }

  .row:focus-visible::after {
    outline: 2px solid var(--color-focus);
    outline-offset: -2px;
    border-radius: var(--radius-md);
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .maybe {
    background: var(--color-maybe-row);
  }

  .maybe .note {
    color: var(--color-maybe-text);
    font-weight: var(--weight-bold);
  }

  .merge {
    position: relative; /* above the row's click area */
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-maybe-button);
    color: var(--color-maybe-chip-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .heads,
  .col,
  .desk {
    display: none;
  }

  .staple {
    padding: 3px var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .nothing {
    padding: var(--space-8) 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: center;
  }

  .more {
    width: 100%;
    min-height: var(--touch-target);
    border: none;
    border-top: 1px solid var(--color-divider);
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .tip {
    padding: 0 var(--space-6);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    text-align: center;
  }

  .panel {
    display: none;
  }

  /* Desktop: a table-like list, and the editor beside it. */
  @media (min-width: 768px) {
    .card {
      padding: var(--space-2) 18px;
    }

    .heads,
    li {
      display: grid;
      grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 0.9fr) 80px;
      column-gap: 14px;
    }

    .heads {
      padding: var(--space-6) 0 var(--space-4);
      color: var(--color-text-muted);
      font-size: var(--text-xs);
      font-weight: var(--weight-extrabold);
      letter-spacing: var(--tracking-overline);
      text-transform: uppercase;
    }

    li {
      min-height: 56px;
      margin: 0 -18px;
      padding: 0 18px;
      border-top: 1px solid var(--color-divider);
      border-bottom: none;
      font-size: var(--text-base);
    }

    li.open {
      background: var(--color-accent-soft);
    }

    li.open .name {
      color: var(--color-accent-on-soft);
    }

    li.open .note {
      color: var(--color-text-soft);
    }

    .name {
      font-size: var(--text-base);
    }

    .col {
      display: flex;
      align-items: center;
    }

    .end {
      display: flex;
      justify-content: flex-end;
    }

    .phone {
      display: none;
    }

    .desk {
      display: block;
    }

    .tip {
      padding: 0;
      text-align: left;
    }

    .panel {
      display: block;
      flex: 1 1 340px;
      min-width: 0;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      background: var(--color-surface);
    }
  }
</style>
