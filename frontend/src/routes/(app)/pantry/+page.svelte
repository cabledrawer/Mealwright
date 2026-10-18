<script lang="ts">
  // Pantry (mockups Phone-Pantry, Desktop-Pantry and their dark versions, plus the
  // lead's rulings of 17 Oct):
  //   phone: search; tabs All · every place (More if they don't fit) · Use soon; staples;
  //          Recent changes at the bottom (last 3, with Undo);
  //   desktop: search, filters, the places as 4 columns or 2 × 2, and a side panel with
  //            Use soon, Staples and Recent changes.
  // Tapping a staple, and "+ List" on a running-low row, add to the main shopping list
  // (0.3, PantryList). Waiting for later milestones (spec "Decided for 0.2"): tubs (0.6),
  // "Recipes for these" (0.4).
  import { browser } from '$app/environment';
  import { resolve } from '$app/paths';
  import { untrack } from 'svelte';
  import { addToPantry } from '$lib/addToPantry.svelte';
  import type { PantryFilter, PantryPlace, Ref, UseSoonLot } from '$lib/client/types';
  import AddToPantry from '$lib/components/AddToPantry.svelte';
  import FoodPicker from '$lib/components/FoodPicker.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import OfflineNote from '$lib/components/OfflineNote.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import PantryGroup from '$lib/components/PantryGroup.svelte';
  import PlaceTabs from '$lib/components/PlaceTabs.svelte';
  import RecentChanges from '$lib/components/RecentChanges.svelte';
  import { compactDateWords, dateWords } from '$lib/dates';
  import { kitchen } from '$lib/freshness.svelte';
  import { live } from '$lib/live.svelte';
  import { network } from '$lib/network.svelte';
  import { ingredientEditor } from '$lib/ingredientEditor.svelte';
  import { PantryModel } from '$lib/pantry.svelte';
  import { PantryList, listLabel } from '$lib/pantryList.svelte';
  import { searchResults } from '$lib/pantrySearch';
  import { toasts } from '$lib/toast.svelte';

  const model = new PantryModel();
  const shopping = new PantryList();
  const uid = $props.id();

  const PHONE = '(max-width: 767px)';
  let phone = $state(browser && matchMedia(PHONE).matches);
  $effect(() => {
    const media = matchMedia(PHONE);
    const onChange = () => (phone = media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  });

  let tab = $state('all');
  let addingStaple = $state(false);
  /** Phone: Recent changes beyond the last 3. */
  let moreChanges = $state(false);
  /** Place columns showing every food, not just the first few (desktop). */
  let expanded = $state<Record<number, boolean>>({});
  const FIRST = 8;

  // Fetch again after any change, a new filter, or coming back to the tab (stock
  // changes elsewhere arrive below).
  $effect(() => {
    void kitchen.version;
    void model.filter;
    void model.load();
  });

  // What is on the shopping list, for the staples' ticks and "+ List": fetch again after any
  // change here, and when another phone changed the list (as Shopping does).
  $effect(() => {
    void kitchen.version;
    untrack(() => void shopping.refresh());
  });
  $effect(() => {
    const heard = live.shopping;
    untrack(() => {
      if (shopping.loaded && heard > shopping.cursor) void shopping.refresh();
    });
  });

  // Stock changed on another phone or window: fetch again. Only the lists on screen are
  // replaced; an open editor or form keeps what was typed (it doesn't watch this).
  let firstLive = true;
  $effect(() => {
    void live.pantry;
    if (firstLive) {
      firstLive = false;
      return;
    }
    void model.load();
  });

  // Pantry needs the server (spec section 6, "Opening the app offline"): offline it shows a
  // note pointing to Shopping, and fetches again once the connection is back.
  let wasOffline = false;
  $effect(() => {
    if (network.offline) wasOffline = true;
    else if (wasOffline) {
      wasOffline = false;
      void model.load();
      void shopping.refresh();
    }
  });

  // Typing in "Find in pantry": ask again shortly after the last key. The server matches
  // every name an ingredient has, the same way Ingredients does.
  let firstSearch = true;
  $effect(() => {
    void model.query;
    if (firstSearch) {
      firstSearch = false;
      return;
    }
    const timer = setTimeout(() => void model.load(), 200);
    return () => clearTimeout(timer);
  });

  function onVisible() {
    if (document.visibilityState !== 'visible') return;
    void model.load();
    void shopping.refresh();
  }

  const pantry = $derived(model.pantry);
  const places = $derived(pantry?.places ?? []);
  /** While there's a search: one list of what it found, whatever tab or column is showing. */
  const searching = $derived(model.searched !== '');
  const found = $derived(searching ? searchResults(places, model.matches) : []);
  const summary = $derived(
    pantry
      ? [
          `${pantry.counts.items} ${pantry.counts.items === 1 ? 'item' : 'items'}`,
          pantry.counts.use_soon ? `${pantry.counts.use_soon} use soon` : ''
        ]
          .filter(Boolean)
          .join(' · ')
      : undefined
  );

  // Phone tabs, in order. Pinned tabs always show; the others, from the end, go under
  // "More" when they don't fit. cabledrawer (17 Oct): All · Fridge · Freezer · Cupboard ·
  // More, with Use soon under More (the All tab already shows the Use soon card).
  const tabs = $derived([
    { id: 'all', label: 'All', pinned: true },
    ...places.map((p) => ({ id: `place-${p.id}`, label: p.name })),
    { id: 'use-soon', label: 'Use soon', pinned: false }
  ]);

  const phonePlaces = $derived(
    tab === 'all' ? places : places.filter((p) => `place-${p.id}` === tab)
  );

  const FILTERS: { value: PantryFilter; label: () => string }[] = [
    { value: 'all', label: () => 'All' },
    {
      value: 'use_soon',
      label: () => (pantry?.counts.use_soon ? `Use soon · ${pantry.counts.use_soon}` : 'Use soon')
    },
    { value: 'running_low', label: () => 'Running low' },
    { value: 'staples', label: () => 'Staples' }
  ];

  function lotWords(lot: UseSoonLot) {
    const date = dateWords(lot.use_by, lot.days_left);
    const what =
      lot.of > 1
        ? `${lot.position}\u00a0of\u00a0${lot.of}`
        : (lot.stock.short ?? lot.stock.display);
    return { what, date, compactDate: compactDateWords(lot.use_by, lot.days_left) };
  }

  /** "+ Add to pantry": the sheet online; offline, a toast says why it can't open (cabledrawer 18 Oct). */
  function addClicked() {
    if (network.offline) {
      toasts.show(
        "Adding to the pantry needs your Mealwright server. Try again when you're back online."
      );
      return;
    }
    addToPantry.show();
  }

  function newStaple(name: string) {
    addingStaple = false;
    void model.newStaple(name);
  }

  function pickStaple(food: Ref) {
    addingStaple = false;
    void model.makeStaple(food);
  }
</script>

<svelte:document onvisibilitychange={onVisible} />

<PageHeader title="Pantry" overline={summary}>
  {#snippet actions()}
    <!-- Adding needs the server: offline the button stays, and a tap says why (cabledrawer 18 Oct). -->
    {#if phone}
      <button type="button" class="add-round" aria-label="Add to pantry" onclick={addClicked}
        >+</button
      >
    {:else}
      <button type="button" class="add-pill" onclick={addClicked}>+ Add to pantry</button>
    {/if}
  {/snippet}
</PageHeader>

{#snippet useSoonRows(lots: UseSoonLot[], compact: boolean)}
  <ul class="soon-list">
    {#each lots as lot (lot.id)}
      {@const words = lotWords(lot)}
      <li>
        <button type="button" class="soon-name" onclick={() => ingredientEditor.open(lot.food.id)}
          >{lot.food.name} · {compact ? words.compactDate : words.what}</button
        >
        <span class="soon-actions">
          <button type="button" class="pill" onclick={() => void model.used(lot.id, lot.food.name)}
            >Used</button
          >
          <button
            type="button"
            class="pill"
            onclick={() => void model.binned(lot.id, lot.food.name)}>Binned</button
          >
          {#if lot.place.kind !== 'freezer'}
            <button
              type="button"
              class="pill"
              onclick={() => void model.toFreezer(lot.id, lot.food.name)}>To freezer</button
            >
          {/if}
        </span>
      </li>
    {/each}
  </ul>
{/snippet}

{#snippet placeCard(place: PantryPlace, heading: boolean, limit: number | null)}
  {@const groups = place.groups}
  {@const visible = limit && !expanded[place.id] ? groups.slice(0, limit) : groups}
  <section class="place" aria-labelledby="{uid}-place-{place.id}">
    <div class="place-head" class:visually-hidden={!heading}>
      <h2 id="{uid}-place-{place.id}">{place.name}</h2>
      <span class="count">{place.items} {place.items === 1 ? 'item' : 'items'}</span>
    </div>
    {#if groups.length}
      <ul class="groups">
        {#each visible as group (group.food.id)}
          <PantryGroup {group} {place} {places} {model} {shopping} />
        {/each}
      </ul>
      {#if visible.length < groups.length}
        <button
          type="button"
          class="show-all"
          onclick={() => (expanded = { ...expanded, [place.id]: true })}
          >Show all {groups.length}</button
        >
      {/if}
    {:else}
      <p class="empty">
        Nothing in the {place.name}.
      </p>
    {/if}
  </section>
{/snippet}

{#snippet searchBox(label: string)}
  <label class="search">
    <Icon name="search" size={18} stroke={2.2} />
    <input type="search" placeholder="{label}…" aria-label={label} bind:value={model.query} />
  </label>
{/snippet}

{#snippet results()}
  <div class="card results">
    {#if found.length}
      <ul class="groups" aria-label="Found in the pantry">
        {#each found as item (`${item.group.food.id}-${item.place.id}`)}
          <PantryGroup
            group={item.group}
            place={item.place}
            {places}
            {model}
            {shopping}
            showPlace
            also={item.also}
          />
        {/each}
      </ul>
    {:else}
      <p class="empty">Nothing called “{model.searched}”.</p>
    {/if}
  </div>
{/snippet}

{#snippet staples(desktop: boolean)}
  <section class="staples" class:panel={desktop} aria-labelledby="{uid}-staples">
    <h2 id="{uid}-staples">Staples</h2>
    <p class="hint">Always assumed in stock.</p>
    <ul class="staple-chips">
      {#each pantry?.staples ?? [] as staple (staple.id)}
        {@const listed = shopping.onList(staple.id)}
        <li>
          <button
            type="button"
            class="chip"
            class:listed
            aria-label={listLabel(staple.name, listed)}
            onclick={() => void shopping.tap({ ...staple, staple: true })}
          >
            {staple.name}
            {#if listed}<Icon name="check" size={14} stroke={3} />{/if}
          </button>
        </li>
      {/each}
      <li class:wide={addingStaple}>
        {#if addingStaple}
          <FoodPicker
            label="Make an ingredient a staple"
            exclude={(pantry?.staples ?? []).map((s) => s.id)}
            onpick={pickStaple}
            oncreate={newStaple}
            oncancel={() => (addingStaple = false)}
          />
        {:else}
          <button type="button" class="add-staple" onclick={() => (addingStaple = true)}
            >+ Staple</button
          >
        {/if}
      </li>
    </ul>
    <a class="edit-staples" href="{resolve('/recipes/ingredients')}?filter=staples">Edit staples</a>
  </section>
{/snippet}

{#if network.offline}
  <OfflineNote screen="Pantry" />
{:else if model.problem && !pantry}
  <p class="problem" role="alert">
    {model.problem}
    <button type="button" class="link" onclick={() => void model.load()}>Try again</button>
  </p>
{:else if !pantry}
  <p class="loading">Loading…</p>
{:else if phone}
  <div class="phone-search">{@render searchBox('Search pantry')}</div>
  {#if !searching}
    <PlaceTabs {tabs} bind:selected={tab} panelId="{uid}-panel" />
  {/if}

  <div class="phone-panel" id="{uid}-panel" role={searching ? undefined : 'tabpanel'}>
    {#if searching}
      {@render results()}
    {:else if tab === 'use-soon'}
      {#if model.useSoon.length}
        <section class="soon-card" aria-label="Use soon">
          {@render useSoonRows(model.useSoon, true)}
        </section>
      {:else}
        <p class="empty card">Nothing needs using up soon.</p>
      {/if}
    {:else}
      {#if tab === 'all' && model.useSoon.length}
        <section class="soon-card" aria-labelledby="{uid}-soon">
          <h2 id="{uid}-soon" class="soon-title">Use soon</h2>
          {@render useSoonRows(model.useSoon.slice(0, 1), true)}
          {#if model.useSoon.length > 1}
            <button type="button" class="soon-more" onclick={() => (tab = 'use-soon')}
              >{model.useSoon.length - 1} more →</button
            >
          {/if}
        </section>
      {/if}
      {#if pantry.counts.items === 0 && tab === 'all'}
        <div class="card first">
          <h2>Nothing in the pantry yet</h2>
          <p class="hint">Add what's in your fridge and cupboards, and Mealwright keeps count.</p>
          <button type="button" class="add-pill" onclick={() => addToPantry.show()}
            >+ Add to pantry</button
          >
        </div>
      {:else}
        <div class="card">
          {#each phonePlaces as place (place.id)}
            {@render placeCard(place, tab === 'all', null)}
          {/each}
        </div>
      {/if}
      {@render staples(false)}
    {/if}

    <!-- The last 3, always; "Show more" for the rest. -->
    <section class="recent" aria-labelledby="{uid}-precent">
      <h2 id="{uid}-precent">Recent changes</h2>
      <RecentChanges
        changes={moreChanges ? model.changes : model.changes.slice(0, 3)}
        onundo={(change) => void model.undo(change)}
      />
      {#if model.changes.length > 3}
        <button
          type="button"
          class="link"
          aria-expanded={moreChanges}
          onclick={() => (moreChanges = !moreChanges)}
          >{moreChanges ? 'Show fewer' : 'Show more'}</button
        >
      {/if}
    </section>
  </div>
{:else}
  <div class="desk">
    <section class="main-side" aria-label="What's in the pantry">
      <div class="tools">
        {@render searchBox('Find in pantry')}
        <div class="filters" role="group" aria-label="Show">
          {#each FILTERS as f (f.value)}
            <button
              type="button"
              class="filter"
              aria-pressed={model.filter === f.value}
              onclick={() => (model.filter = f.value)}>{f.label()}</button
            >
          {/each}
        </div>
      </div>
      {#if searching}
        {@render results()}
      {:else if pantry.counts.items === 0 && model.filter === 'all'}
        <div class="card first">
          <h2>Nothing in the pantry yet</h2>
          <p class="hint">Add what's in your fridge and cupboards, and Mealwright keeps count.</p>
          <button type="button" class="add-pill" onclick={() => addToPantry.show()}
            >+ Add to pantry</button
          >
        </div>
      {:else}
        <div class="columns">
          {#each places as place (place.id)}
            <div class="card column">{@render placeCard(place, true, FIRST)}</div>
          {/each}
        </div>
      {/if}
    </section>

    <aside class="side" aria-label="Use soon, staples and recent changes">
      <section class="card side-card" aria-labelledby="{uid}-dsoon">
        <h2 id="{uid}-dsoon">Use soon</h2>
        {#if model.useSoon.length}
          {@render useSoonRows(model.useSoon, false)}
        {:else}
          <p class="hint">Nothing needs using up soon.</p>
        {/if}
      </section>
      {@render staples(true)}
      <section class="card side-card" aria-labelledby="{uid}-recent">
        <h2 id="{uid}-recent">Recent changes</h2>
        <RecentChanges changes={model.changes} onundo={(change) => void model.undo(change)} />
      </section>
    </aside>
  </div>
{/if}

<AddToPantry {model} {places} today={pantry?.today ?? new Date().toISOString().slice(0, 10)} />

<style>
  .add-round {
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-bold) 1.375rem var(--font-ui);
    cursor: pointer;
  }

  .add-pill {
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

  .card {
    padding: var(--space-1) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .card.first {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    padding: var(--space-8);
  }

  .first h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  /* The phone's search sits above the tabs and runs the width of the screen. */
  .phone-search {
    margin-bottom: var(--space-4);
  }

  .phone-search .search {
    max-width: none;
  }

  .phone-panel {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .place + .place {
    border-top: 1px solid var(--color-divider);
  }

  .place-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: var(--space-5) 0 var(--space-3);
  }

  .place-head h2 {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .count,
  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .groups {
    margin: 0;
    padding: 0;
  }

  .empty {
    padding: var(--space-6) 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .empty.card {
    padding: var(--space-7);
  }

  .show-all,
  .link,
  .soon-more {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-align: left;
    cursor: pointer;
  }

  /* Use soon: a salmon card on phones, a white card on desktop. */
  .soon-card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-6) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-use-soon-chip);
  }

  .soon-title {
    color: var(--color-use-soon-heading);
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .soon-more {
    color: var(--color-use-soon-heading);
  }

  .soon-list {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .soon-list li {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
  }

  .soon-name {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
    text-align: left;
    cursor: pointer;
  }

  .soon-actions {
    display: flex;
    gap: var(--space-3);
  }

  .pill {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .staples {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .staples h2 {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .staples .hint {
    display: none;
  }

  .staple-chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .staple-chips .wide {
    flex-basis: 100%;
  }

  .staple-chips button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-staple-chip);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  /* A staple chip is a button: a tap adds it to the shopping list. A small tick shows while
     it's on the list. */
  .staple-chips .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  .staple-chips .chip.listed {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .edit-staples {
    display: inline-flex;
    align-items: center;
    align-self: flex-start;
    min-height: var(--touch-target);
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .staple-chips .add-staple {
    border: 1px dashed var(--color-add-border);
    background: transparent;
    color: var(--color-text-muted);
  }

  .recent {
    padding: var(--space-2) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .recent h2 {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .problem,
  .loading {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  /* Desktop */
  .desk {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--space-9);
  }

  .main-side {
    display: flex;
    flex: 999 1 640px;
    flex-direction: column;
    gap: var(--space-7);
    min-width: 0;
    container-type: inline-size;
  }

  .tools {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-4);
  }

  .search {
    display: flex;
    flex: 1 1 240px;
    align-items: center;
    gap: var(--space-4);
    max-width: 360px;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
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
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-medium) var(--text-base) var(--font-ui);
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
    padding: 0 14px;
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

  /* Four places side by side when there's room, otherwise two by two. */
  .columns {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    align-items: start;
  }

  @container (min-width: 760px) {
    .columns {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }
  }

  .column {
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-2xl);
  }

  .column .place-head {
    padding-top: 0;
  }

  .side {
    display: flex;
    flex: 1 1 300px;
    flex-direction: column;
    gap: 14px;
    min-width: 0;
  }

  .side-card {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-7) 18px;
    border-radius: var(--radius-2xl);
  }

  .side-card h2,
  .staples.panel h2 {
    color: var(--color-text);
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    letter-spacing: normal;
    text-transform: none;
  }

  .side-card .soon-list li {
    border-top: 1px solid var(--color-divider);
  }

  .side-card .soon-name {
    font-size: var(--text-base);
  }

  .side-card .pill {
    border: 1px solid var(--color-border-strong);
    font-size: var(--text-sm);
  }

  .staples.panel {
    padding: var(--space-7) 18px;
    border-radius: var(--radius-2xl);
    background: var(--color-staples-panel);
  }

  .staples.panel .hint {
    display: block;
  }
</style>
