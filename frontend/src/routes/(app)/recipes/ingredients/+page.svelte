<script lang="ts">
  // Ingredients (mockups Ingredients-Phone, Ingredients-Desktop): every food, searchable
  // by any name, with the editor. Desktop shows the editor beside the list; phones open
  // it as a sheet. Each row says how many recipes use it ("5 recipes"; "Used in 5 recipes" for a
  // screen reader), and "Not in any recipe · 9" is a filter beside Staples (spec "Ingredients
  // screen", cabledrawer 17 Oct; 0.4). On a Maybe-the-same row the Merge button takes the place of
  // the count, as in the mockups.
  import { browser } from '$app/env';
  import { page } from '$app/state';
  import { tick } from 'svelte';
  import { serverUndo } from '#lib/client/changes.js';
  import { mergeFood } from '#lib/client/foods.js';
  import type { FoodFilter, FoodRow, FoodWrite } from '#lib/client/types.js';
  import Icon from '#lib/components/Icon.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import IngredientEditor from '#lib/components/IngredientEditor.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import RecentChanges from '#lib/components/RecentChanges.svelte';
  import UsedCount from '#lib/components/UsedCount.svelte';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
  import { IngredientChanges } from '#lib/ingredientChanges.svelte.js';
  import { IngredientsList } from '#lib/ingredients.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { mergeTarget } from '#lib/maybeSame.js';
  import { network } from '#lib/network.svelte.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import { save } from '#lib/save.js';

  const list = new IngredientsList();
  const recent = new IngredientChanges();
  const uid = $props.id();
  let recentSheet: HTMLDialogElement;
  /** Desktop: the side column shows the Recent changes list instead of the editor. */
  let showRecent = $state(false);
  let recentBar = $state<HTMLButtonElement>();
  let recentClose = $state<HTMLButtonElement>();
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

  // Recent changes: fetch again after any change here or elsewhere, when stock moved (a
  // purchase can bring an ingredient back), and when coming back to the tab.
  $effect(() => {
    void kitchen.version;
    void live.pantry;
    void recent.load();
  });

  // The sheet is for phones; if the window grows into a desktop, it closes (the side panel
  // shows the same list).
  $effect(() => {
    if (desktop && recentSheet?.open) recentSheet.close();
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
      void recent.load();
    }
  });

  // Desktop starts with the first food open, as in the mockup.
  $effect(() => {
    if (selectedId === null && list.foods[0] && isDesktop()) selectedId = list.foods[0].id;
  });

  // Back to the tab after a while: fetch again (live updates come in 0.3).
  function onVisible() {
    if (document.visibilityState !== 'visible') return;
    void list.load();
    void recent.load();
  }

  /** The quiet line under a food's name. */
  function note(food: FoodRow, phone: boolean): string {
    const maybe = mergeTarget(food);
    if (maybe) return `Maybe the same as “${maybe.name}”`;
    if (phone) return [food.counted_as_display, food.place?.name].filter(Boolean).join(' · ');
    if (food.matched_name && food.matched_name !== food.name) return `also: ${food.matched_name}`;
    if (food.other_names.length) return `also: ${food.other_names.join(', ')}`;
    const standIn = food.stand_ins[0];
    if (standIn) return `${standIn.name} can stand in`;
    return '';
  }

  /** " · 9", " · 10+" when there are more than the list holds; nothing while loading, on an
   * error, or when there is nothing to count. */
  const recentCount = $derived(
    !recent.loaded || recent.problem || recent.changes.length === 0
      ? ''
      : ` · ${recent.changes.length}${recent.more ? '+' : ''}`
  );

  async function openRecent() {
    showRecent = true;
    await tick();
    recentClose?.focus();
  }

  async function closeRecent() {
    showRecent = false;
    await tick();
    recentBar?.focus();
  }

  function open(food: FoodRow) {
    // Desktop edits beside the list; phones get the sheet.
    if (isDesktop()) {
      selectedId = food.id;
      showRecent = false; // opening an ingredient shows its editor again
    } else ingredientEditor.open(food.id);
  }

  /** "New ingredient": ask how it's counted, then open it so the rest can be filled in. */
  async function makeNew() {
    const made = await newIngredient.ask();
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

{#snippet changesList()}
  {#if recent.problem && !recent.changes.length}
    <div class="none" role="alert">
      <p>{recent.problem}</p>
      <button type="button" class="again" onclick={() => void recent.load()}>Try again</button>
    </div>
  {:else}
    <RecentChanges
      changes={recent.changes}
      onundo={(change) => void recent.undo(change)}
      verbFirst={false}
      none={recent.loaded
        ? 'Nothing yet. Changes to ingredients show here, with Undo.'
        : 'Loading…'}
    />
  {/if}
{/snippet}

<PageHeader
  title="Ingredients"
  parent={{ href: '/(app)/recipes', label: 'Recipes' }}
  subtitle={list.loaded && !list.problem
    ? `${list.counts.all} ${list.counts.all === 1 ? 'ingredient' : 'ingredients'} · ${desktop ? 'shared by your recipes, pantry and shopping list' : 'shared by recipes, pantry and shopping'}`
    : undefined}
>
  {#snippet actions()}
    {#if !network.offline}
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

{#if network.offline || (network.down && list.problem !== null)}
  <!-- From the first failure, so the words don't change when the bar comes (F67). -->
  <OfflineNote screen="Ingredients" />
{:else}
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
              onclick={() => (list.filter = f.value)}>{f.label}{chipCount(f.value)}</button
            >
          {/each}
          {#if !desktop}
            <button
              type="button"
              class="filter recent-button"
              onclick={() => recentSheet.showModal()}>Recent changes</button
            >
          {/if}
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
      </div>

      <div class="card">
        <div class="heads" aria-hidden="true">
          <span>Ingredient</span><span>Counted as</span><span>Lives in</span><span>Recipes</span>
        </div>
        {#if list.foods.length}
          <ul>
            {#each list.foods as food (food.id)}
              {@const maybe = !!mergeTarget(food)}
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
      </div>

      <p class="tip">
        You can also tap any ingredient in a recipe, the pantry or the shopping list to open this
        same editor.
      </p>
    </section>

    {#if desktop}
      <div class="side">
        {#if showRecent}
          <section class="panel recent" aria-labelledby="{uid}-recent">
            <div class="recent-head">
              <h2 id="{uid}-recent">Recent changes</h2>
              <button
                type="button"
                class="close"
                bind:this={recentClose}
                onclick={() => void closeRecent()}>Close</button
              >
            </div>
            {@render changesList()}
          </section>
        {:else}
          <button
            type="button"
            class="recent-bar"
            bind:this={recentBar}
            onclick={() => void openRecent()}
            >Recent changes{recentCount}<Icon name="chevron-down" size={16} stroke={2.4} /></button
          >
          {#if selectedId !== null}
            <aside class="panel" aria-label={panelName ? `Edit ${panelName}` : 'Edit'}>
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
        {/if}
      </div>
    {/if}
  </div>
{/if}

<dialog
  bind:this={recentSheet}
  aria-labelledby="{uid}-sheet"
  onclick={(event) => {
    if (event.target === recentSheet) recentSheet.close();
  }}
>
  <div class="sheet-body">
    <span class="handle" aria-hidden="true"></span>
    <div class="sheet-head">
      <h2 id="{uid}-sheet">Recent changes</h2>
      <button type="button" class="close" onclick={() => recentSheet.close()}>Close</button>
    </div>
    {@render changesList()}
  </div>
</dialog>

<style>
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

  .none {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .recent-button {
    color: var(--color-accent);
  }

  /* The phone's Recent changes sheet: from the bottom, like the ingredient editor. */
  dialog {
    inset: auto 0 0 0;
    width: 100%;
    max-width: none;
    max-height: min(680px, calc(100dvh - 120px));
    margin: 0;
    padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .sheet-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .sheet-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .recent-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .recent-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: var(--touch-target);
    padding: 0 22px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .sheet-head h2,
  .recent h2 {
    margin: 0;
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .close {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
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

    /* The editor and Recent changes stay in view while the list scrolls. */
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

    .recent {
      display: flex;
      flex-direction: column;
      gap: var(--space-3);
    }
  }
</style>
