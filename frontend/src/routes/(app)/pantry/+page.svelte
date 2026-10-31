<script lang="ts">
  // Pantry (mockups Phone-Pantry, Desktop-Pantry and their dark versions, plus the
  // lead's rulings of 17 Oct):
  //   phone: search; jump chips; Use soon; a card per place (no place tabs, cabledrawer 24 Oct);
  //          staples; Recent changes at the bottom (last 3, with Undo);
  //   desktop: search, filters, the places as 4 columns or 2 × 2, and a side panel with
  //            Use soon, Staples and Recent changes.
  // Tapping a staple, and "+ List" on a running-low row, add to the main shopping list
  // (0.3, PantryList). "Recipes for these" (desktop) and "Recipes that use them →" (phone) open
  // All recipes on its "Use soon" filter (0.4). Waiting for later milestones (spec "Decided for
  // 0.2"): tubs (0.6).
  import { browser } from '$app/env';
  import { resolve } from '$app/paths';
  import { untrack } from 'svelte';
  import { addToPantry } from '#lib/addToPantry.svelte.js';
  import type { PantryFilter, PantryPlace, Ref, UseSoonLot } from '#lib/client/types.js';
  import AddToPantry from '#lib/components/AddToPantry.svelte';
  import FoodPicker from '#lib/components/FoodPicker.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import PantryGroup from '#lib/components/PantryGroup.svelte';
  import SwipeRow from '#lib/components/SwipeRow.svelte';
  import UsedSheet from '#lib/components/UsedSheet.svelte';
  import RecentChanges from '#lib/components/RecentChanges.svelte';
  import { compactDateWords, dateWords } from '#lib/dates.js';
  import type { Name as IconName } from '#lib/components/Icon.svelte';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
  import { cantReachWords } from '#lib/api.js';
  import { blockedWhileDown } from '#lib/serverNeeded.js';
  import { PantryModel } from '#lib/pantry.svelte.js';
  import { PantryList, listLabel } from '#lib/pantryList.svelte.js';
  import { searchResults } from '#lib/pantrySearch.js';
  import { toasts } from '#lib/toast.svelte.js';

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

  /** The Use soon item whose "How much?" is open, and which ones are swiped open. */
  let usedFor = $state<UseSoonLot | null>(null);
  let usedOpen = $state(false);
  const soonSwiped = $state<Record<number, 'left' | 'right' | null>>({});

  /** Phone: the Use soon card shows every item, not just the first. */
  let soonAll = $state(false);
  let addingStaple = $state(false);
  /** Phone: Recent changes beyond the last 3. */
  let moreChanges = $state(false);
  /** Place columns showing every food, not just the first few (desktop). */
  let expanded = $state<Record<number, boolean>>({});
  const FIRST = 8;
  /** Phone, All: a place's card shows this many rows, then "+ 3 more in the Cupboard". */
  const PHONE_FIRST = 6;

  /** A place's icon (mockup PantryPlaces-Phone): the fridge, the freezer, the spice rack, else a cupboard. */
  function placeIcon(place: { kind: string; name: string }): IconName {
    if (place.kind === 'fridge') return 'place-fridge';
    if (place.kind === 'freezer') return 'place-freezer';
    return /spice/i.test(place.name) ? 'place-spice' : 'place-cupboard';
  }

  /** The jump chips and the places' cards use these anchors. */
  const placeAnchor = (id: number) => `${uid}-place-card-${id}`;

  function jumpTo(id: number) {
    const card = document.getElementById(placeAnchor(id));
    card?.scrollIntoView({ block: 'start' });
    card?.querySelector<HTMLElement>('h2')?.setAttribute('tabindex', '-1');
    card?.querySelector<HTMLElement>('h2')?.focus({ preventScroll: true });
  }

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
    // `down`, not `offline`: the note shows from the first failure, so the page fetches again
    // when anything answers, even before the bar came (F67 review).
    if (network.down) wasOffline = true;
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
  /** While there's a search: one list of what it found, whatever column or card is showing. */
  const searching = $derived(model.searched !== '');
  const found = $derived(searching ? searchResults(places, model.matches) : []);
  const summary = $derived(
    pantry
      ? [
          `${pantry.counts.items} ${pantry.counts.items === 1 ? 'ingredient' : 'ingredients'}`,
          pantry.counts.use_soon ? `${pantry.counts.use_soon} use soon` : ''
        ]
          .filter(Boolean)
          .join(' · ')
      : undefined
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
      // The words follow the cause: no network on the device, or no answer from the server.
      toasts.show(
        network.deviceOffline
          ? 'Adding to the pantry needs your Mealwright server. Try again when you’re back online.'
          : cantReachWords()
      );
      return;
    }
    addToPantry.show();
  }

  /** What the Use soon item is counted in, from the group it sits in (else by weight). */
  const usedGroup = $derived(
    usedFor
      ? places
          .find((p) => p.id === usedFor?.place.id)
          ?.groups.find((g) => g.food.id === usedFor?.food.id)
      : undefined
  );
  const usedCounted = $derived(usedGroup?.food.counted_as ?? 'weight');
  const usedUnit = $derived(
    usedCounted === 'weight' ? 'g' : usedCounted === 'volume' ? 'ml' : 'count'
  );

  function openUsed(lot: UseSoonLot) {
    usedFor = lot;
    usedOpen = true;
  }

  function usedDone() {
    usedOpen = false;
  }

  function newStaple(name: string) {
    if (blockedWhileDown()) return;
    addingStaple = false;
    void model.newStaple(name);
  }

  function pickStaple(food: Ref) {
    if (blockedWhileDown()) return;
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
        ><Icon name="plus" size={20} stroke={2.6} /></button
      >
    {:else}
      <button type="button" class="add-pill" aria-label="+ Add to pantry" onclick={addClicked}
        ><Icon name="plus" size={16} stroke={2.6} />Add to pantry</button
      >
    {/if}
  {/snippet}
</PageHeader>

{#snippet useSoonRow(lot: UseSoonLot, compact: boolean)}
  {@const words = lotWords(lot)}
  <button
    type="button"
    class="soon-name"
    disabled={network.offline}
    onclick={() => ingredientEditor.open(lot.food.id)}
    >{lot.food.name} · {compact ? words.compactDate : words.what}</button
  >
  <span class="soon-actions">
    <button
      type="button"
      class="pill"
      disabled={network.offline}
      onclick={() => void model.used(lot.id, lot.food.name)}>Used</button
    >
    <button
      type="button"
      class="pill"
      disabled={network.offline}
      onclick={() => void model.binned(lot.id, lot.food.name)}>Binned</button
    >
    {#if lot.place.kind !== 'freezer'}
      <button
        type="button"
        class="pill"
        disabled={network.offline}
        onclick={() => void model.toFreezer(lot.id, lot.food.name)}>To freezer</button
      >
    {/if}
  </span>
{/snippet}

{#snippet useSoonRows(lots: UseSoonLot[], compact: boolean)}
  <ul class="soon-list">
    {#each lots as lot (lot.id)}
      <li class:swipe-li={compact && phone}>
        {#if compact && phone}
          <SwipeRow
            bleed={0}
            bind:open={() => soonSwiped[lot.id] ?? null, (side) => (soonSwiped[lot.id] = side)}
            right={{
              label: 'Used…',
              describe: lot.food.name,
              icon: 'check',
              tone: 'used',
              run: () => {
                if (!blockedWhileDown()) openUsed(lot);
              }
            }}
            left={{
              label: 'Binned',
              describe: lot.food.name,
              icon: 'trash',
              tone: 'danger',
              run: () => {
                if (!blockedWhileDown()) void model.binned(lot.id, lot.food.name);
              }
            }}
          >
            <div class="soon-line">{@render useSoonRow(lot, compact)}</div>
          </SwipeRow>
        {:else}
          {@render useSoonRow(lot, compact)}
        {/if}
      </li>
    {/each}
  </ul>
{/snippet}

<!-- Opens All recipes on its "Use soon" filter: the recipes that use what is about to go off. -->
{#snippet recipesFor(words: string)}
  <a class="recipes-for" href="{resolve('/(app)/recipes')}?filter=use-soon">{words}</a>
{/snippet}

{#snippet placeCard(place: PantryPlace, heading: boolean, limit: number | null, icon = false)}
  {@const groups = place.groups}
  {@const visible = limit && !expanded[place.id] ? groups.slice(0, limit) : groups}
  <section class="place" aria-labelledby="{uid}-place-{place.id}">
    <div class="place-head" class:visually-hidden={!heading} class:with-icon={icon}>
      {#if icon}<span class="place-icon" aria-hidden="true"
          ><Icon name={placeIcon(place)} size={20} stroke={2} /></span
        >{/if}
      <h2 id="{uid}-place-{place.id}">{place.name}</h2>
      <span class="count">{place.items} {place.items === 1 ? 'ingredient' : 'ingredients'}</span>
    </div>
    {#if groups.length}
      <ul class="groups">
        {#each visible as group (group.food.id)}
          <PantryGroup
            {group}
            {place}
            {places}
            {model}
            {shopping}
            swipes={phone}
            today={pantry?.today}
          />
        {/each}
      </ul>
      {#if visible.length < groups.length}
        <button
          type="button"
          class="show-all"
          onclick={() => (expanded = { ...expanded, [place.id]: true })}
          >{icon
            ? `+ ${groups.length - visible.length} more in the ${place.name}`
            : `Show all ${groups.length}`}</button
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
            swipes={phone}
            today={pantry?.today}
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
          <button
            type="button"
            class="add-staple"
            disabled={network.offline}
            onclick={() => (addingStaple = true)}>+ Staple</button
          >
        {/if}
      </li>
    </ul>
    <a class="edit-staples" href="{resolve('/(app)/recipes/ingredients')}?filter=staples"
      >Edit staples</a
    >
  </section>
{/snippet}

{#if !pantry && network.down}
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
  <div class="phone-panel">
    {#if searching}
      {@render results()}
    {:else}
      {#if places.filter((p) => p.groups.length).length > 1}
        <!-- Jump chips (mockup PantryPlaces-Phone): straight to a place's card. -->
        <nav class="jump" aria-label="Jump to a place">
          {#each places.filter((p) => p.groups.length) as place (place.id)}
            <button type="button" onclick={() => jumpTo(place.id)}
              >{place.name} · {place.items}</button
            >
          {/each}
        </nav>
      {/if}
      {#if model.useSoon.length}
        <section class="soon-card" aria-labelledby="{uid}-soon">
          <h2 id="{uid}-soon" class="soon-title">Use soon</h2>
          {@render useSoonRows(soonAll ? model.useSoon : model.useSoon.slice(0, 1), true)}
          {#if model.useSoon.length > 1}
            <button
              type="button"
              class="soon-more"
              aria-expanded={soonAll}
              onclick={() => (soonAll = !soonAll)}
              >{soonAll ? 'Show fewer' : `${model.useSoon.length - 1} more →`}</button
            >
          {/if}
          {@render recipesFor('Recipes that use them →')}
        </section>
      {/if}
      {#if pantry.counts.items === 0}
        <div class="card first">
          <h2>Nothing in the pantry yet</h2>
          <p class="hint">Add what’s in your fridge and cupboards, and Mealwright keeps count.</p>
          <button type="button" class="add-pill" aria-label="+ Add to pantry" onclick={addClicked}
            ><Icon name="plus" size={16} stroke={2.6} />Add to pantry</button
          >
        </div>
      {:else}
        {#each places as place (place.id)}
          {#if place.groups.length === 0}
            <!-- An empty place folds to one line. -->
            <p class="folded">
              <span class="place-icon quiet" aria-hidden="true"
                ><Icon name={placeIcon(place)} size={20} stroke={2} /></span
              >
              <span class="folded-name">{place.name}</span>
              <span class="count">empty</span>
            </p>
          {:else}
            <div class="card place-card" id={placeAnchor(place.id)}>
              {@render placeCard(place, true, PHONE_FIRST, true)}
            </div>
          {/if}
        {/each}
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
    <section class="main-side" aria-label="What’s in the pantry">
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
          <p class="hint">Add what’s in your fridge and cupboards, and Mealwright keeps count.</p>
          <button type="button" class="add-pill" aria-label="+ Add to pantry" onclick={addClicked}
            ><Icon name="plus" size={16} stroke={2.6} />Add to pantry</button
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
        <div class="side-head">
          <h2 id="{uid}-dsoon">Use soon</h2>
          {#if model.useSoon.length}{@render recipesFor('Recipes for these')}{/if}
        </div>
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

{#if usedFor}
  {@const lot = usedFor}
  <UsedSheet
    open={usedOpen}
    name={lot.food.name}
    detail={[lot.place.name, lot.stock.display, dateWords(lot.use_by, lot.days_left)]
      .filter(Boolean)
      .join(' · ')}
    countedAs={usedCounted}
    total={lot.stock.amount}
    allWords={lot.stock.short ?? lot.stock.display}
    onall={() => {
      usedDone();
      void model.used(lot.id, lot.food.name);
    }}
    onpart={(amount) => {
      usedDone();
      void model.usedSome(lot.food.id, lot.food.name, { amount, unit: usedUnit }, lot.place.id);
    }}
    onleft={(amount) => {
      usedDone();
      void model.leftOf(lot.food.id, lot.food.name, { amount, unit: 'count' }, lot.place.id);
    }}
    onclose={usedDone}
  />
{/if}

<AddToPantry {model} {places} today={pantry?.today ?? new Date().toISOString().slice(0, 10)} />

<style>
  .add-round {
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

  .add-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
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

  /* A card per place on the phone (mockup PantryPlaces-Phone): an icon, the name, the count. */
  .place-head.with-icon {
    flex-wrap: nowrap;
    align-items: center;
    gap: var(--space-4);
    min-height: 52px;
    padding: var(--space-3) 0;
    border-bottom: 2px solid var(--color-divider);
  }

  .place-head.with-icon h2 {
    flex: 1;
    font-size: var(--text-3xl);
  }

  .place-icon {
    display: grid;
    flex: none;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 10px;
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .place-icon.quiet {
    background: var(--color-fill);
    color: var(--color-text-muted);
  }

  .place-card :global(.group:first-child) {
    border-top: none;
  }

  .folded {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 52px;
    padding: 0 var(--space-8);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text-muted);
  }

  .folded-name {
    flex: 1;
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  /* Nothing scrolls sideways (UX principle 14): the chips wrap to a second line instead. */
  .jump {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .jump button {
    flex: none;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .place + .place {
    border-top: 1px solid var(--color-divider);
  }

  .place-head {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: baseline;
    gap: 0 var(--space-3);
    padding: var(--space-5) 0 var(--space-3);
  }

  .place-head h2 {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  /* "7 ingredients" stays on one line, apart from the place's name: when there's no room
     beside the name (a narrow column, or text at 200%), it goes under it. */
  .place-head .count {
    white-space: nowrap;
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

  .recipes-for {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .recipes-for:hover {
    text-decoration: underline;
  }

  .soon-card .recipes-for {
    color: var(--color-use-soon-heading);
  }

  .side-head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 0 var(--space-5);
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

  /* A swipeable Use soon item is a small white card of its own (mockup PantrySwipe-Phone). */
  .soon-list li.swipe-li {
    display: block;
    margin-bottom: var(--space-3);
    border-radius: 14px;
    overflow: hidden;
  }

  .soon-line {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-3);
    min-height: 54px;
    padding: 0 12px;
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
     it’s on the list. */
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
    color: var(
      --color-accent-on-soft
    ); /* the card behind is grey: --color-accent is a hair short */
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

  /* Room above and below each row, so one row's 44 px buttons don't nearly touch the next
     row's (cabledrawer 24 Oct: "they almost clash into the ones above and below them"; 0.5.1). */
  .side-card .soon-list li {
    padding: var(--space-3) 0;
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
