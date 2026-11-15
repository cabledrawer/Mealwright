<script lang="ts">
  // Ingredients (mockups Ingredients-Phone, Ingredients-Desktop): every food, searchable
  // by any name, with the editor. Desktop shows the editor beside the list; phones open
  // it as a sheet. Each row says how many recipes use it ("5 recipes"; "Used in 5 recipes" for a
  // screen reader), and "Not in any recipe · 9" is a filter beside Staples (spec "Ingredients
  // screen", cabledrawer 17 Oct; 0.4). On a Maybe-the-same row the Merge button takes the place of
  // the count, as in the mockups.
  import { browser } from '$app/env';
  import { page } from '$app/state';
  import { cantReachWords } from '#lib/api.js';
  import { serverUndo } from '#lib/client/changes.js';
  import { mergeFood } from '#lib/client/foods.js';
  import type { FoodFilter, FoodRow, FoodWrite } from '#lib/client/types.js';
  import Icon from '#lib/components/Icon.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PackCell from '#lib/components/PackCell.svelte';
  import PantrySwitch from '#lib/components/PantrySwitch.svelte';
  import IngredientEditor from '#lib/components/IngredientEditor.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import UsedCount from '#lib/components/UsedCount.svelte';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
  import { IngredientsList } from '#lib/ingredients.svelte.js';
  import { mergeTarget } from '#lib/maybeSame.js';
  import { network } from '#lib/network.svelte.js';
  import { isPantryIngredients } from '#lib/pantrySide.svelte.js';
  import { columnWords, fullDateWords } from '#lib/restockWords.js';
  import { newNameFor } from '#lib/ingredientSearch.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import { save } from '#lib/save.js';
  import { starterPacks } from '#lib/starterPacks.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';

  const list = new IngredientsList();
  let selectedId = $state<number | null>(null);
  let panelName = $state('');

  // "Edit staples" on Pantry opens this page with ?filter=staples.
  if (page.url.searchParams.get('filter') === 'staples') list.filter = 'staples';

  const FILTERS: { value: FoodFilter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'staples', label: 'Staples' },
    { value: 'unused', label: 'Not in any recipe' }
  ];

  /** The count on a filter chip that has one ("Not in any recipe · 9"); nothing until it is known. */
  const chipCount = (value: FoodFilter): string =>
    value === 'unused' && list.loaded && !list.problem ? ` · ${list.counts.unused}` : '';

  const isDesktop = () => browser && matchMedia('(min-width: 768px)').matches;
  let desktop = $state(isDesktop());

  // The editor sits beside the list only where the two fit side by side: the list's 480 px, the
  // gap and the editor's 340 px (the .layout rules below). Narrower, flex-wrap would drop it
  // under the whole list, out of sight (F191), so it opens as a panel over the page, as on
  // the narrow layouts elsewhere, with the list still in view.
  const SIDE_BY_SIDE_MIN = 480 + 24 + 340;
  let layoutWidth = $state(0);
  const sideBySide = $derived(desktop && layoutWidth >= SIDE_BY_SIDE_MIN);
  $effect(() => {
    const media = matchMedia('(min-width: 768px)');
    const onChange = () => (desktop = media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  });

  // Search as you type (after a short pause), and fetch again whenever something changed.
  $effect(() => {
    void list.query;
    void list.filter;
    void kitchen.version;
    const timer = setTimeout(() => void list.load(), list.loaded ? 200 : 0);
    return () => clearTimeout(timer);
  });

  // Ingredients needs the server (spec section 6, "Opening the app offline"): offline it
  // shows a note pointing to Shopping, and fetches again once the connection is back. After a
  // short drop (no offline note yet) it fetches again too, whether its load has failed already
  // or is still on its way and about to (0.5.1): the new load takes the old one's place.
  let wasOffline = false;
  let back = network.backAgain;
  $effect(() => {
    if (network.offline) {
      wasOffline = true;
      return;
    }
    const again = network.backAgain !== back;
    back = network.backAgain;
    if (wasOffline || again) {
      wasOffline = false;
      void list.load();
    }
  });

  /** True while the open ingredient is only the one the page opened by itself. */
  let startedOpen = false;

  // Desktop starts with the first food open, as in the mockup.
  $effect(() => {
    if (selectedId === null && list.foods[0] && sideBySide) {
      selectedId = list.foods[0].id;
      startedOpen = true;
    }
  });

  // Resizing with an editor open moves it between the side panel and the sheet, so it stays
  // in view (F191).
  $effect(() => {
    if (layoutWidth === 0) return;
    if (!sideBySide && selectedId !== null) {
      // The first one opened by itself is not an editor someone asked for: it just goes.
      if (!startedOpen) ingredientEditor.open(selectedId);
      selectedId = null;
    } else if (sideBySide && ingredientEditor.foodId !== null) {
      selectedId = ingredientEditor.foodId;
      ingredientEditor.close();
    }
  });

  // Back to the tab after a while: fetch again (live updates come in 0.3).
  function onVisible() {
    if (document.visibilityState !== 'visible') return;
    void list.load();
  }

  /** Reached from the Pantry tab's switch (phone): it shows the switch and no way up to Recipes. */
  const fromPantry = $derived(isPantryIngredients(page.url.pathname, page.url.search));

  /** The staple whose whole restock date is showing (a tap on "Restocked 3 weeks ago"). */
  let dateShownFor = $state<number | null>(null);

  const KEPT_WORD = { weight: 'Weight', volume: 'Volume', count: 'Count' } as const;

  /** The quiet line under a food's name. */
  function note(food: FoodRow, phone: boolean): string {
    const maybe = mergeTarget(food);
    if (maybe) return `Maybe the same as “${maybe.name}”`;
    if (phone) {
      const restocked =
        food.staple && food.restocked_days_ago != null ? columnWords(food.restocked_days_ago) : '';
      // The pack has its own line under the name, so the first words only say how it's kept.
      const kept = food.pack ? KEPT_WORD[food.counted_as] : food.counted_as_display;
      return [kept, restocked, food.place?.name].filter(Boolean).join(' · ');
    }
    if (food.matched_name && food.matched_name !== food.name) return `also: ${food.matched_name}`;
    if (food.other_names.length) return `also: ${food.other_names.join(', ')}`;
    const standIn = food.stand_ins[0];
    if (standIn) return `${standIn.name} can stand in`;
    return '';
  }

  /** "121 ingredients · shared by recipes, pantry and shopping", once the list has loaded. */
  const countText = $derived(
    list.loaded && !list.problem
      ? `${list.counts.all} ${list.counts.all === 1 ? 'ingredient' : 'ingredients'} · ${desktop ? 'shared by your recipes, pantry and shopping list' : 'shared by recipes, pantry and shopping'}`
      : ''
  );

  function open(food: FoodRow) {
    // Editing needs the server: while it is down, say so instead of opening an editor.
    if (network.offline) {
      toasts.show(cantReachWords());
      return;
    }
    // Beside the list where there is room; otherwise the panel or sheet over the page.
    startedOpen = false;
    if (sideBySide) {
      selectedId = food.id;
    } else ingredientEditor.open(food.id);
  }

  /** "+ New ingredient: 'chilli flakes'" at the end of the results (F97): offered when what is
   *  typed isn't exactly the name, or another name, of an ingredient in them. Only once the rows
   *  on show answer what is typed with the "All" filter (another filter hides ingredients that
   *  may be an exact match), and never while the server can't be reached, like the button by
   *  the title. */
  const offered = $derived(
    !network.offline &&
      list.loaded &&
      !list.problem &&
      list.filter === 'all' &&
      list.answeredFor?.query === list.query &&
      list.answeredFor.filter === 'all'
      ? newNameFor(list.query, list.foods)
      : null
  );

  /** "New ingredient": ask how it's counted, then open it so the rest can be filled in. With a
   *  name (from the search box) the question has it filled in already. */
  async function makeNew(name = '') {
    const made = await newIngredient.ask(name);
    if (!made) return;
    list.query = '';
    list.filter = 'all';
    void list.load();
    open({ id: made.id, name: made.name } as FoodRow);
  }

  /** "Merge" on a Maybe-the-same row: into the food it may be. Undo, not "Are you sure?". */
  function merge(food: FoodRow) {
    const into = mergeTarget(food);
    if (!into) return;
    let undoer: (() => Promise<string | void>) | null = null;
    const before = list.foods;
    void save<FoodWrite>({
      apply: () => (list.foods = list.foods.filter((f) => f.id !== food.id)),
      rollback: () => (list.foods = before),
      send: (key, answers) => mergeFood(food.id, into.id, key, answers),
      saved: (result) => {
        if (selectedId === food.id) selectedId = result.food.id;
        kitchen.changed({ elsewhere: true });
      },
      undo: {
        label: `Merged ${food.name} into ${into.name}`,
        labelFrom: (result) => result.change?.summary,
        skip: (result) => result.change === null,
        run: (result) => (result.change ? (undoer ??= serverUndo(result.change.id))() : false)
      }
    });
  }
</script>

<svelte:document onvisibilitychange={onVisible} />

<!-- The count line (F194): beside the title on a computer, on its own full-width line on the phone,
     so the buttons don't squeeze it. -->
{#snippet countLine()}
  <p class="count-line">{countText}</p>
{/snippet}

<PageHeader
  title="Ingredients"
  parent={fromPantry ? undefined : { href: '/(app)/recipes', label: 'Recipes' }}
  subtitle={desktop ? countText : undefined}
  count={!desktop && countText ? countLine : undefined}
>
  {#snippet actions()}
    <!-- F240: not above the note that says the server is needed (down: offline, or no answer yet). -->
    {#if !network.offline && !(network.down && list.couldntLoad)}
      <!-- A phone shows the round + as Pantry does: the words beside the title squeezed it
           until "Ingredients" broke inside the word at 390 px. -->
      {#if desktop}
        <button type="button" class="new" onclick={() => void makeNew()}>+ New ingredient</button>
      {:else}
        <button
          type="button"
          class="new-round"
          aria-label="New ingredient"
          title="New ingredient"
          onclick={() => void makeNew()}><Icon name="plus" size={20} stroke={2.6} /></button
        >
      {/if}
    {/if}
  {/snippet}
</PageHeader>

{#if fromPantry}<PantrySwitch current="ingredients" />{/if}

{#if network.down && list.couldntLoad}
  <!-- From the first failure, so the words don't change when the bar comes (F67). -->
  <OfflineNote screen="Ingredients" />
{:else}
  <div class="layout" bind:clientWidth={layoutWidth}>
    <section class="list-side" aria-label="All ingredients">
      <div class="tools">
        <label class="search">
          <Icon name="search" size={18} stroke={2.2} />
          <input
            type="search"
            placeholder="Search by any name, e.g. arhar dal"
            aria-label="Search ingredients"
            bind:value={list.query}
            onkeydown={(event) => {
              // Enter with nothing found makes it, as Enter does in Shopping's box.
              if (event.key === 'Enter' && offered && !list.foods.length) void makeNew(offered);
            }}
          />
        </label>
        <div class="filters" role="group" aria-label="Show">
          {#each FILTERS as f (f.value)}
            <button
              type="button"
              class="filter"
              aria-pressed={list.filter === f.value}
              onclick={() => (list.filter = f.value)}>{f.label}{chipCount(f.value)}</button
            >
          {/each}
          {#if list.counts.maybe_same_pairs || list.filter === 'maybe_same'}
            <button
              type="button"
              class="filter maybe"
              aria-pressed={list.filter === 'maybe_same'}
              onclick={() => (list.filter = list.filter === 'maybe_same' ? 'all' : 'maybe_same')}
              >Maybe the same · {list.counts.maybe_same_pairs}</button
            >
          {/if}
        </div>
        {#if !network.offline}
          <button type="button" class="starter" onclick={() => starterPacks.show()}
            >Add a starter pack</button
          >
        {/if}
      </div>

      <div class="card">
        <div class="heads" aria-hidden="true">
          <span>Ingredient</span><span>Pack</span><span>Kept by</span><span>Lives in</span><span
            >Recipes</span
          >
        </div>
        {#if list.foods.length}
          <ul>
            {#each list.foods as food (food.id)}
              {@const maybe = !!mergeTarget(food)}
              {@const desk = note(food, false)}
              <li class:maybe class:open={food.id === selectedId}>
                <div class="main">
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
                  {#if !desktop && !maybe}
                    <span class="packline"
                      ><PackCell {food} onother={() => ingredientEditor.open(food.id)} /></span
                    >
                  {/if}
                </div>
                {#if desktop}
                  <span class="col"
                    >{#if !maybe}<PackCell {food} onother={() => open(food)} />{/if}</span
                  >
                {/if}
                <span class="col">
                  {#if food.staple}
                    <span class="stack">
                      <span class="staple">Staple</span>
                      {#if food.restocked_on && food.restocked_days_ago != null}
                        <!-- The whole date on hover, and on tap (a title alone doesn't show on a touch screen). -->
                        <button
                          type="button"
                          class="when"
                          title={fullDateWords(food.restocked_on)}
                          aria-expanded={dateShownFor === food.id}
                          onclick={() => (dateShownFor = dateShownFor === food.id ? null : food.id)}
                          >{dateShownFor === food.id
                            ? `Restocked ${fullDateWords(food.restocked_on)}`
                            : columnWords(food.restocked_days_ago)}</button
                        >
                      {/if}
                    </span>
                  {:else}{food.counted_as_display}{/if}
                </span>
                <span class="col">{food.place?.name ?? ''}</span>
                <span class="end">
                  {#if maybe}
                    <button
                      type="button"
                      class="merge"
                      disabled={network.offline}
                      onclick={() => merge(food)}>Merge</button
                    >
                  {:else}
                    <UsedCount count={food.used_in_recipes ?? 0} />
                  {/if}
                </span>
              </li>
            {/each}
          </ul>
          {#if list.next}
            <button type="button" class="more" onclick={() => void list.more()}>Show more</button>
          {/if}
        {:else if list.problem}
          <div class="nothing" role="alert">
            <p>{list.problem}</p>
            <button type="button" class="again" onclick={() => void list.load()}>Try again</button>
          </div>
        {:else if !list.loaded}
          <p class="nothing">Loading…</p>
        {:else if list.query.trim()}
          <p class="nothing">No ingredient called “{list.query.trim()}” yet.</p>
        {:else if list.filter === 'unused'}
          <p class="nothing">Every ingredient is in a recipe.</p>
        {:else if list.filter !== 'all'}
          <p class="nothing">Nothing here right now.</p>
        {:else}
          <p class="nothing">
            No ingredients yet. They’re added when you put something in the pantry or import a
            recipe.
          </p>
        {/if}
        {#if offered}
          <button type="button" class="new-from-search" onclick={() => void makeNew(offered ?? '')}>
            + New ingredient: “{offered}”
          </button>
        {/if}
      </div>

      <p class="tip">
        You can also tap any ingredient in a recipe, the pantry or the shopping list to open this
        same editor.
      </p>
    </section>

    {#if sideBySide}
      <div class="side">
        {#if selectedId !== null}
          <aside class="panel" aria-label={panelName ? `Edit ${panelName}` : 'Edit'}>
            {#key selectedId}
              <IngredientEditor
                foodId={selectedId}
                variant="panel"
                onname={(n) => (panelName = n)}
                onclose={() => (selectedId = null)}
                onopen={(id) => {
                  startedOpen = false;
                  selectedId = id;
                }}
              />
            {/key}
          </aside>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .count-line {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  .new-round {
    display: grid;
    place-items: center;
    padding: 0;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    cursor: pointer;
  }

  .new {
    min-height: var(--touch-target);
    padding: 0 18px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .starter {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

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
    min-width: var(--touch-target);
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

  /* The name's button, and under it (a phone) the pack. */
  .main {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: flex-start;
    min-width: 0;
  }

  .packline {
    padding-bottom: var(--space-4);
  }

  .packline:empty {
    display: none;
  }

  .row {
    display: flex;
    flex: none;
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

  .end {
    flex: none;
  }

  .merge {
    position: relative; /* above the row’s click area */
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

  .stack {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-1);
  }

  /* "Restocked 3 weeks ago": a button, so a tap shows the date (a hover title would not). */
  .when {
    position: relative; /* above the row’s click area */
    min-height: var(--touch-target);
    margin-block: calc(-1 * var(--space-3));
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-medium) var(--text-sm) var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .staple {
    padding: 3px var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  /* The end of the results, like the "+ New ingredient" chip in Shopping's Add an item box. */
  .new-from-search {
    display: block;
    margin: var(--space-4) auto var(--space-6);
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft); /* accent on the grey chip is 4.47:1, under 4.5 */
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .nothing {
    padding: var(--space-8) 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: center;
  }

  /* "Try again" after a load that failed: a real button, not more grey words (0.5.1). */
  .again {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
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

  .side {
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
      grid-template-columns:
        minmax(0, 1.4fr) minmax(0, 1.2fr) minmax(0, 0.9fr) minmax(0, 0.8fr)
        70px;
      column-gap: 14px;
    }

    .heads span:last-child {
      text-align: right;
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

    /* "Add a pack" in the open row: accent on the green row is 4.3:1, under 4.5. */
    li.open :global(.add) {
      color: var(--color-accent-on-soft);
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

    .main {
      display: contents;
    }

    .tip {
      padding: 0;
      text-align: left;
    }

    /* The editor stays in view while the list scrolls. */
    .side {
      position: sticky;
      top: var(--space-7);
      align-self: flex-start;
      display: flex;
      flex: 1 1 340px;
      flex-direction: column;
      gap: var(--space-6);
      min-width: 0;
      max-height: calc(100dvh - 2 * var(--space-7));
      overflow-x: hidden;
      overflow-y: auto;
      scrollbar-width: thin;
    }

    .panel {
      flex: none;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      background: var(--color-surface);
    }
  }
</style>
