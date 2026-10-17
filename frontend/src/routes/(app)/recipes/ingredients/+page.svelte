<script lang="ts">
  // Ingredients (mockups Ingredients-Phone, Ingredients-Desktop): every food, searchable
  // by any name, with the editor. Desktop shows the editor beside the list; phones open
  // it as a sheet. The recipe counts and "Not in any recipe" wait for recipes (0.4).
  //
  // SKELETON: placeholder foods until the 0.2 API is ready.
  import Icon from '$lib/components/Icon.svelte';
  import IngredientEditor from '$lib/components/IngredientEditor.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import { countedAs, listFoods, type Food, type FoodFilter } from '$lib/foods';
  import { foodById, kitchen } from '$lib/foods.sample.svelte';
  import { ingredientEditor } from '$lib/ingredientEditor.svelte';

  let query = $state('');
  let filter = $state<FoodFilter>('all');
  let selectedId = $state<number | null>(kitchen.foods[0]?.id ?? null);

  const shown = $derived(listFoods(kitchen.foods, query, filter));
  const maybeCount = $derived(kitchen.foods.filter((f) => f.maybeSameAsId !== undefined).length);
  const selected = $derived(foodById(selectedId));

  const FILTERS: { value: FoodFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'staples', label: 'Staples' }
  ];

  const placeName = (food: Food) =>
    kitchen.places.find((p) => p.id === food.placeId)?.name ?? 'Not set';

  /** The quiet line under a food's name. */
  function note(food: Food, phone: boolean): string {
    const other = foodById(food.maybeSameAsId);
    if (other) return `Maybe the same as “${other.name}”`;
    if (phone) return `${countedAs(food)} · ${placeName(food)}`;
    if (food.otherNames.length) return `also: ${food.otherNames.join(', ')}`;
    const standIn = food.standInIds.map((id) => foodById(id)?.name).find(Boolean);
    if (standIn) return `${standIn.toLocaleLowerCase()} can stand in`;
    const usual = food.saleUnits.find((u) => u.usual);
    if (food.base === 'count' && usual) {
      return `${usual.name} = ${usual.amount} ${food.countName ? food.countName + 's' : ''}`.trim();
    }
    return '';
  }

  function open(food: Food) {
    // Desktop edits beside the list; phones get the sheet.
    if (matchMedia('(min-width: 768px)').matches) selectedId = food.id;
    else ingredientEditor.open(food.id);
  }
</script>

<PageHeader
  title="Ingredients"
  parent={{ href: '/recipes', label: 'Recipes' }}
  subtitle="{kitchen.foods.length} foods · shared by recipes, pantry and shopping"
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
          bind:value={query}
        />
      </label>
      <div class="filters" role="group" aria-label="Show">
        {#each FILTERS as f (f.value)}
          <button
            type="button"
            class="filter"
            aria-pressed={filter === f.value}
            onclick={() => (filter = f.value)}>{f.label}</button
          >
        {/each}
        {#if maybeCount}
          <button
            type="button"
            class="filter maybe"
            aria-pressed={filter === 'maybe'}
            onclick={() => (filter = filter === 'maybe' ? 'all' : 'maybe')}
            >Maybe the same · {maybeCount}</button
          >
        {/if}
      </div>
    </div>

    <div class="card">
      <div class="heads" aria-hidden="true">
        <span>Ingredient</span><span>Counted as</span><span>Lives in</span><span></span>
      </div>
      {#if shown.length}
        <ul>
          {#each shown as food (food.id)}
            {@const maybe = food.maybeSameAsId !== undefined}
            <li class:maybe class:open={food.id === selected?.id}>
              <button
                type="button"
                class="row"
                aria-current={food.id === selected?.id ? 'true' : undefined}
                onclick={() => open(food)}
              >
                <span class="name">{food.name}</span>
                <span class="note phone">{note(food, true)}</span>
                {#if note(food, false)}<span class="note desk">{note(food, false)}</span>{/if}
              </button>
              <span class="col">
                {#if food.staple}<span class="staple">Staple</span>{:else}{countedAs(food)}{/if}
              </span>
              <span class="col">{placeName(food)}</span>
              <span class="end">
                {#if maybe}
                  <button type="button" class="merge" onclick={() => open(food)}>Merge</button>
                {/if}
              </span>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="nothing">No ingredient called “{query.trim()}” yet.</p>
      {/if}
    </div>

    <p class="tip">
      You can also tap any ingredient in a recipe, the pantry or the shopping list to open this same
      editor.
    </p>
  </section>

  {#if selected}
    <aside class="panel" aria-label="Edit {selected.name.toLocaleLowerCase()}">
      {#key selected.id}
        <IngredientEditor food={selected} variant="panel" />
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
