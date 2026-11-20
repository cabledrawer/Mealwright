<script lang="ts">
  import EmptyState from '#lib/components/EmptyState.svelte';
  import FilterChips from '#lib/components/FilterChips.svelte';
  import Loading from '#lib/components/Loading.svelte';
  // Pantry (mockups Phone-Pantry, Desktop-Pantry and their dark versions, plus the
  // lead's rulings of 17 Oct):
  //   phone: search; jump chips; Use soon; a card per place (no place tabs, cabledrawer 24 Oct);
  //          staples;
  //   desktop: search, filters, the places as 4 columns or 2 × 2, and a side panel with
  //            Use soon and Staples. (Recent changes moved to Settings, F172.)
  // Tapping a staple, and "+ List" on a running-low row, add to the main shopping list
  // (0.3, PantryList). "Recipes for these" (desktop) and "Recipes that use them →" (phone) open
  // All recipes on its "Use soon" filter (0.4). Waiting for later milestones (spec "Decided for
  // 0.2"): tubs (0.6).
  import { browser } from '$app/env';
  import { resolve } from '$app/paths';
  import { untrack } from 'svelte';
  import { addToPantry } from '#lib/addToPantry.svelte.js';
  import type {
    Group,
    PantryFilter,
    PantryPlace,
    Ref,
    TubRow,
    UseSoonLot,
    UseSoonTub
  } from '#lib/client/types.js';
  import Lazy from '#lib/components/Lazy.svelte';
  import FoodPicker from '#lib/components/FoodPicker.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PantrySwitch from '#lib/components/PantrySwitch.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import PantryGroup from '#lib/components/PantryGroup.svelte';
  import PantryTub from '#lib/components/PantryTub.svelte';
  import UseSoon from '#lib/components/UseSoon.svelte';
  import { whenWords } from '#lib/dates.js';
  import { chipWords } from '#lib/restockWords.js';
  import type { Name as IconName } from '#lib/components/Icon.svelte';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { needsServer } from '#lib/downWords.js';
  import { blockedWhileDown } from '#lib/serverNeeded.js';
  import { PantryModel } from '#lib/pantry.svelte.js';
  import { PantryList, listLabel } from '#lib/pantryList.svelte.js';
  import { searchResults } from '#lib/pantrySearch.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { plural, nothingMatches } from '#lib/words.js';
  import { PHONE_QUERY } from '#lib/layout.js';

  const model = new PantryModel();
  const shopping = new PantryList();
  const uid = $props.id();

  let phone = $state(browser && matchMedia(PHONE_QUERY).matches);
  $effect(() => {
    const media = matchMedia(PHONE_QUERY);
    const onChange = () => (phone = media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  });

  /** The Use soon item whose "How much?" is open. */
  let usedFor = $state<UseSoonLot | null>(null);
  let usedOpen = $state(false);
  /** The Use soon tub card whose "Eat it on…" is open. */
  let eatingTub = $state<UseSoonTub | null>(null);
  /** "Eat it on…" was asked at least once: its code is fetched then, and kept (size limit). */
  let eatEver = $state(false);

  let addingStaple = $state(false);
  /** Place columns showing every food, not just the first few (desktop). */
  let expanded = $state<Record<number, boolean>>({});
  const FIRST = 6;
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
  const itemsText = $derived(
    pantry
      ? `${pantry.counts.items} ${plural(pantry.counts.items, 'ingredient', 'ingredients')}`
      : ''
  );
  const soonText = $derived(pantry?.counts.use_soon ? `${pantry.counts.use_soon} use soon` : '');
  const summary = $derived(
    pantry
      ? [
          `${pantry.counts.items} ${plural(pantry.counts.items, 'ingredient', 'ingredients')}`,
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

  /** A place has something to show: packets or tubs. */
  const hasRows = (place: PantryPlace) => place.groups.length > 0 || place.tubs.length > 0;

  /** "+ Add to pantry": the sheet online; offline, a toast says why it can't open (cabledrawer 18 Oct). */
  function addClicked() {
    if (network.offline) {
      // The words follow the cause: no network on the device, or no answer from the server.
      toasts.show(
        needsServer(
          network.deviceOffline,
          'Adding to the pantry needs your Mealwright server. Try again when you’re back online.'
        )
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

  // F240: the page that says "needs your Mealwright server" has nothing to add to or count, so its
  // header has no + and no Stocktake. (Once the pantry has loaded, offline keeps the + and a tap
  // says why: cabledrawer 18 Oct.)
  const offlinePage = $derived(!pantry && network.down);
</script>

<svelte:document onvisibilitychange={onVisible} />

<!-- The phone's count line (F194, mockup Dark-PantryHead08-Phone): the count on its own line under
     the title, Stocktake at its right, dropping under it when the line is too narrow. -->
{#snippet countLine()}
  <div class="count-line">
    {#if pantry}
      <span class="summary"
        >{itemsText}{soonText ? ' · ' : ''}{#if soonText}<span class="soon">{soonText}</span
          >{/if}</span
      >
    {/if}
    {#if !offlinePage}
      <a class="stocktake-pill" href={resolve('/(app)/pantry/stocktake')}>Stocktake</a>
    {/if}
  </div>
{/snippet}

<PageHeader
  title="Pantry"
  overline={phone ? undefined : summary}
  count={phone && !offlinePage ? countLine : undefined}
>
  {#snippet actions()}
    <!-- The Stocktake (F118): place by place, in its own screen. -->
    {#if !phone && !offlinePage}
      <a class="stocktake-pill" href={resolve('/(app)/pantry/stocktake')}>Stocktake</a>
    {/if}
    <!-- Adding needs the server: offline the button stays, and a tap says why (cabledrawer 18 Oct). -->
    {#if offlinePage}
      <!-- F240: nothing to add to while the page only says the server is needed. -->
    {:else if phone}
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

<PantrySwitch current="pantry" />

{#snippet placeCard(place: PantryPlace, heading: boolean, limit: number | null, icon = false)}
  <!-- Packets first, then the tubs left, each ingredient on one line (name · amount · date). -->
  {@const rows = [
    ...place.groups.map((group) => ({ group, tub: null as TubRow | null })),
    ...place.tubs.map((tub) => ({ group: null as Group | null, tub }))
  ]}
  {@const visible = limit && !expanded[place.id] ? rows.slice(0, limit) : rows}
  {@const moreRows = rows.length - visible.length}
  <section class="place" aria-labelledby="{uid}-place-{place.id}">
    <div class="place-head" class:visually-hidden={!heading} class:with-icon={icon}>
      {#if icon}<span class="place-icon" aria-hidden="true"
          ><Icon name={placeIcon(place)} size={20} stroke={2} /></span
        >{/if}
      <h2 id="{uid}-place-{place.id}">{place.name}</h2>
      <span class="count">{place.items} {plural(place.items, 'ingredient', 'ingredients')}</span>
    </div>
    {#if rows.length}
      <ul class="groups">
        {#each visible as row (row.group ? `g${row.group.food.id}` : `t${row.tub?.batch_id}`)}
          {#if row.group}
            <PantryGroup
              group={row.group}
              {place}
              {places}
              {model}
              {shopping}
              swipes={phone}
              today={pantry?.today}
            />
          {:else if row.tub}
            <PantryTub tub={row.tub} capital={phone} />
          {/if}
        {/each}
      </ul>
      {#if moreRows > 0}
        <button
          type="button"
          class="show-all"
          onclick={() => (expanded = { ...expanded, [place.id]: true })}
          >{icon ? `+ ${moreRows} more in the ${place.name}` : `${moreRows} more`}</button
        >
      {/if}
    {:else}
      <p class="mw-quiet">Nothing in the {place.name}.</p>
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
      <p class="mw-quiet">{nothingMatches('ingredient', model.searched)}</p>
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
        {@const restocked =
          staple.restocked_on && staple.restocked_days_ago != null
            ? chipWords(staple.restocked_on, staple.restocked_days_ago)
            : ''}
        <li>
          <button
            type="button"
            class="chip"
            class:listed
            aria-label={restocked
              ? `${listLabel(staple.name, listed)}. ${restocked}`
              : listLabel(staple.name, listed)}
            onclick={() => void shopping.tap({ ...staple, staple: true })}
          >
            <span class="chip-name">
              {staple.name}
              {#if listed}<Icon name="check" size={14} stroke={3} />{/if}
            </span>
            {#if restocked}<span class="restocked">{restocked}</span>{/if}
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

{#if offlinePage}
  <OfflineNote screen="Pantry" />
{:else if model.problem && !pantry}
  <p class="problem" role="alert">
    {model.problem}
    <button type="button" class="link" onclick={() => void model.load()}>Try again</button>
  </p>
{:else if !pantry}
  <Loading />
{:else if phone}
  <div class="phone-search">{@render searchBox('Search pantry')}</div>
  <div class="phone-panel">
    {#if searching}
      {@render results()}
    {:else}
      {#if places.filter(hasRows).length > 1}
        <!-- Jump chips (mockup PantryPlaces-Phone): straight to a place's card. -->
        <nav class="jump" aria-label="Jump to a place">
          {#each places.filter(hasRows) as place (place.id)}
            <button type="button" onclick={() => jumpTo(place.id)}
              >{place.name} · {place.items}</button
            >
          {/each}
        </nav>
      {/if}
      {#if model.useSoon.length || model.useSoonTubs.length}
        <UseSoon
          lots={model.useSoon}
          tubs={model.useSoonTubs}
          {model}
          phone
          onhowmuch={openUsed}
          oneaton={(tub) => {
            eatEver = true;
            eatingTub = tub;
          }}
        />
      {/if}
      {#if pantry.counts.items === 0 && pantry.counts.tubs === 0}
        <EmptyState title="Nothing in the pantry yet">
          Add what’s in your fridge and cupboards, and Mealwright keeps count.
          {#snippet action()}
            <button type="button" class="add-pill" aria-label="+ Add to pantry" onclick={addClicked}
              ><Icon name="plus" size={16} stroke={2.6} />Add to pantry</button
            >
          {/snippet}
        </EmptyState>
      {:else}
        {#each places as place (place.id)}
          {#if !hasRows(place)}
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
  </div>
{:else}
  <div class="desk">
    <div class="tools">
      {@render searchBox('Find in pantry')}
      <FilterChips
        label="Show"
        options={FILTERS.map((f) => ({ value: f.value, label: f.label() }))}
        selected={model.filter}
        onselect={(value) => (model.filter = value)}
      />
    </div>
    {#if searching}
      {@render results()}
    {:else}
      <!-- Use soon: a strip of four cards across the top (F66, cabledrawer 6 Nov). -->
      <UseSoon
        lots={model.useSoon}
        tubs={model.useSoonTubs}
        {model}
        phone={false}
        onhowmuch={openUsed}
        oneaton={(tub) => {
          eatEver = true;
          eatingTub = tub;
        }}
      />
      {#if pantry.counts.items === 0 && pantry.counts.tubs === 0 && model.filter === 'all'}
        <EmptyState title="Nothing in the pantry yet">
          Add what’s in your fridge and cupboards, and Mealwright keeps count.
          {#snippet action()}
            <button type="button" class="add-pill" aria-label="+ Add to pantry" onclick={addClicked}
              ><Icon name="plus" size={16} stroke={2.6} />Add to pantry</button
            >
          {/snippet}
        </EmptyState>
      {:else}
        <section class="columns" aria-label="What’s in the pantry">
          {#each places as place (place.id)}
            <div class="card column">{@render placeCard(place, true, FIRST)}</div>
          {/each}
        </section>
      {/if}
      {@render staples(true)}
    {/if}
  </div>
{/if}

{#if eatEver}
  <Lazy
    load={() => import('#lib/components/EatItOn.svelte')}
    onfail={() => {
      eatEver = false;
      eatingTub = null;
    }}
    tub={eatingTub}
    today={pantry?.today ?? ''}
    onclose={() => (eatingTub = null)}
    onpick={(day, slotId, slotName) => {
      const tub = eatingTub;
      eatingTub = null;
      if (tub && !blockedWhileDown()) void model.eatTubOn(tub, day, slotId, slotName);
    }}
  />
{/if}

{#if usedFor}
  {@const lot = usedFor}
  <Lazy
    load={() => import('#lib/components/UsedSheet.svelte')}
    onfail={() => {
      usedDone();
      usedFor = null;
    }}
    open={usedOpen}
    name={lot.food.name}
    detail={[
      lot.place.name,
      lot.stock.display,
      whenWords(lot.date_kind, lot.use_by, lot.days_left, { capital: true }).text
    ]
      .filter(Boolean)
      .join(' · ')}
    unitWord={lot.lots_count === 1 ? (lot.stock.as_sold?.size?.name ?? null) : null}
    countedAs={usedCounted}
    total={lot.stock.amount}
    allWords={lot.stock.short ?? lot.stock.display}
    onall={() => {
      usedDone();
      // One packet: used up. Several that are soon: take their total, soonest first.
      if (lot.lots_count === 1) void model.used(lot.id, lot.food.name);
      else
        void model.usedSome(
          lot.food.id,
          lot.food.name,
          { amount: lot.stock.amount, unit: usedUnit },
          lot.place.id
        );
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

{#if addToPantry.wanted}
  <Lazy
    load={() => import('#lib/components/AddToPantry.svelte')}
    onfail={() => addToPantry.fail()}
    {model}
    {places}
    today={pantry?.today ?? new Date().toISOString().slice(0, 10)}
  />
{/if}

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

  .count-line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .summary {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  .soon {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-bold);
  }

  .stocktake-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: var(--touch-target);
    padding: 0 18px;
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
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

  .show-all,
  .link {
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
    flex-direction: column;
    align-items: flex-start;
    justify-content: center;
    padding-block: var(--space-2);
  }

  .chip-name {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  /* "Restocked 12 Oct": a quiet second line (0.7 K5). */
  .restocked {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  .staple-chips .chip.listed .restocked {
    color: var(--color-accent-on-soft);
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

  .problem,
  /* Desktop: tools, Use soon as a strip, the places across the width, then Staples. */
  .desk {
    display: flex;
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
    outline: var(--focus-width) solid var(--color-focus);
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

  /* The places fill the width: two across, three when there's room (F66). */
  .columns {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 14px;
    align-items: start;
  }

  @container (min-width: 900px) {
    .columns {
      grid-template-columns: repeat(3, minmax(0, 1fr));
    }
  }

  .column {
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-2xl);
  }

  .column .place-head {
    padding-top: 0;
  }

  .staples.panel h2 {
    color: var(--color-text);
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    letter-spacing: normal;
    text-transform: none;
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
