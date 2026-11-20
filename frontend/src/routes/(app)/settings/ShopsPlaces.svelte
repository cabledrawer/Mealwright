<script lang="ts">
  // Settings › Shops & places (F74, F101; mockup Dark-Settings08-Desktop; spec "Shops & places
  // in Settings"). Anyone in the household can manage them. Shops in the order you visit them;
  // places in order, each with its kind (Fridge, Freezer, Cupboard). Removing a shop moves its
  // ingredients to "Any shop"; a place with things in it says how many and asks where to move
  // them; the last Fridge and the last Freezer stay. Each removal has Undo.
  import { onMount } from 'svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { serverUndo } from '#lib/client/changes.js';
  import { getPlaces, getShops } from '#lib/client/foods.js';
  import {
    orderPlaces,
    orderShops,
    removePlace,
    removeShop,
    renamePlace,
    renameShop
  } from '#lib/client/settingsLists.js';
  import type { Place, PlaceKind, Shop } from '#lib/client/types.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { focusOnMount } from '#lib/focusOnMount.js';
  import { network } from '#lib/network.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { save } from '#lib/save.js';
  import { toasts } from '#lib/toast.svelte.js';
  import OrderedRows from './OrderedRows.svelte';

  const KINDS: { value: PlaceKind; label: string }[] = [
    { value: 'fridge', label: 'Fridge' },
    { value: 'freezer', label: 'Freezer' },
    { value: 'cupboard', label: 'Cupboard' }
  ];
  const kindLabel = (kind: PlaceKind) => KINDS.find((k) => k.value === kind)?.label ?? kind;

  let shops = $state<Shop[]>([]);
  let places = $state<Place[]>([]);
  /** The server answered (so a problem is worth a Try again). */
  let reached = $state(true);
  let problem = $state<string | null>(null);
  /** The last answer to a rename, order or add that the server refused (its own words). */
  let shopNote = $state<string | null>(null);
  let placeNote = $state<string | null>(null);

  async function load() {
    try {
      [shops, places] = await Promise.all([getShops(), getPlaces()]);
      problem = null;
    } catch (error) {
      problem = cantReach(error) ? cantReachWords() : 'Couldn’t load your shops and places.';
      reached = !cantReach(error);
    }
  }
  onMount(() => void load());
  // Opened while the server couldn't be reached: fetch again once the connection is back.
  let seen = network.backAgain;
  $effect(() => {
    if (network.backAgain === seen) return;
    seen = network.backAgain;
    void load();
  });
  // An Undo from anywhere on the page (the toast, or Recent changes below) puts a shop or a place
  // back on the server: read the rows again and tell the other pickers (F175).
  let undoneSeen = kitchen.elsewhere;
  $effect(() => {
    if (kitchen.elsewhere === undoneSeen) return;
    undoneSeen = kitchen.elsewhere;
    void load();
    void placesAndShops.load(true).catch(() => {});
  });

  /** The rest of the app's pickers fetch the lists again. */
  const refreshShared = () => {
    void placesAndShops.load(true).catch(() => {});
    // Recent changes, further down this page, fetch again (F176).
    kitchen.wroteSettings();
  };

  function wordsOf(error: unknown): string {
    return error instanceof ApiError && !cantReach(error)
      ? error.detail
      : nothingChanged(network.deviceOffline);
  }

  // --- Shops -----------------------------------------------------------------------------------

  /**
   * The server wants every shop (or place) once. When another tab or person has added or removed
   * one meanwhile, ours was out of date: read the lists again and say so (RF5, H5).
   */
  function listChanged(error: ApiError): boolean {
    if (error.code !== 'not_all_shops' && error.code !== 'not_all_places') return false;
    void load();
    toasts.show('The list changed. Try again.', { tone: 'problem' }); // proposed, for cabledrawer
    return true;
  }

  function orderShopsTo(ids: number[]) {
    const before = shops;
    void save({
      apply: () => (shops = ids.map((id) => before.find((s) => s.id === id)!)),
      rollback: () => (shops = before),
      send: () => orderShops(ids),
      saved: refreshShared,
      refused: listChanged
    });
  }

  async function renameShopTo(shop: Shop, name: string): Promise<boolean> {
    shopNote = null;
    try {
      const done = await renameShop(shop.id, name);
      shops = shops.map((s) => (s.id === shop.id ? done : s));
      refreshShared();
      return true;
    } catch (error) {
      shopNote = wordsOf(error);
      return false;
    }
  }

  function removeShopRow(shop: Shop) {
    const before = shops;
    void save({
      apply: () => (shops = before.filter((s) => s.id !== shop.id)),
      rollback: () => (shops = before),
      send: (key) => removeShop(shop.id, key),
      saved: refreshShared,
      undo: {
        label: `Removed the shop ${shop.name}`,
        skip: (done) => done.change === null,
        run: (done) => (done.change?.can_undo ? serverUndo(done.change.id, refreshShared)() : false)
      }
    });
  }

  let newShop = $state('');
  let addingShop = $state(false);
  async function addShop(event: Event) {
    event.preventDefault();
    const name = newShop.trim();
    if (!name) return;
    shopNote = null;
    try {
      const shop = await placesAndShops.addShop(name);
      if (!shops.some((s) => s.id === shop.id)) shops = [...shops, shop];
      kitchen.wroteSettings();
      newShop = '';
      addingShop = false;
    } catch (error) {
      shopNote = wordsOf(error);
    }
  }

  // --- Places ----------------------------------------------------------------------------------

  function orderPlacesTo(ids: number[]) {
    const before = places;
    void save({
      apply: () => (places = ids.map((id) => before.find((p) => p.id === id)!)),
      rollback: () => (places = before),
      send: () => orderPlaces(ids),
      saved: refreshShared,
      refused: listChanged
    });
  }

  async function renamePlaceTo(place: Place, name: string): Promise<boolean> {
    placeNote = null;
    try {
      const done = await renamePlace(place.id, name);
      places = places.map((p) => (p.id === place.id ? done : p));
      refreshShared();
      return true;
    } catch (error) {
      placeNote = wordsOf(error);
      return false;
    }
  }

  /** The last of its kind can't go: Mealwright needs a Fridge and a Freezer. */
  function lastOfKind(place: Place): string | null {
    if (place.kind === 'cupboard') return null;
    const others = places.filter((p) => p.id !== place.id && p.kind === place.kind);
    return others.length
      ? null
      : `Mealwright needs a ${kindLabel(place.kind).toLowerCase()}, so ${place.name} stays.`;
  }

  /** A place with things in it: asking where to move them. */
  let moving = $state<{ place: Place; things: number } | null>(null);
  let moveTo = $state<number | null>(null);

  function removePlaceRow(place: Place, to?: number) {
    const before = places;
    void save({
      apply: () => {
        places = before.filter((p) => p.id !== place.id);
        placeNote = null;
      },
      rollback: () => (places = before),
      send: (key) => removePlace(place.id, key, to),
      saved: () => {
        moving = null;
        refreshShared();
      },
      refused: (error) => {
        if (error.code !== 'place_not_empty') return false;
        const things = (error.body as { things?: number } | null)?.things ?? 0;
        moving = { place, things };
        moveTo = before.find((p) => p.id !== place.id && p.kind === place.kind)?.id ?? null;
        moveTo ??= before.find((p) => p.id !== place.id)?.id ?? null;
        return true;
      },
      undo: {
        label: `Removed the place ${place.name}`,
        skip: (done) => done.change === null,
        run: (done) => (done.change?.can_undo ? serverUndo(done.change.id, refreshShared)() : false)
      }
    });
  }

  let newPlace = $state('');
  let newKind = $state<PlaceKind>('cupboard');
  let addingPlace = $state(false);
  async function addPlace(event: Event) {
    event.preventDefault();
    const name = newPlace.trim();
    if (!name) return;
    placeNote = null;
    try {
      const place = await placesAndShops.addPlace(name, newKind);
      if (!places.some((p) => p.id === place.id)) places = [...places, place];
      kitchen.wroteSettings();
      newPlace = '';
      addingPlace = false;
    } catch (error) {
      placeNote = wordsOf(error);
    }
  }

  const askedMove = (node: HTMLElement) => node.focus();
  const hasFixed = $derived(places.some((p) => lastOfKind(p) !== null));
</script>

{#if problem}
  <p class="note" role="status">
    {problem}
    {#if reached}<button type="button" class="link" onclick={() => void load()}>Try again</button
      >{/if}
  </p>
{/if}

<section class="card" aria-labelledby="shops-title">
  <h3 id="shops-title">Shops</h3>
  <p class="detail">In the order you visit them. Shopping groups the list by shop in this order.</p>
  <OrderedRows
    items={shops}
    noun="shop"
    disabled={network.offline}
    onorder={orderShopsTo}
    onrename={renameShopTo}
    onremove={removeShopRow}
  />
  {#if addingShop}
    <form class="add" onsubmit={addShop}>
      <label class="sr" for="new-shop">New shop</label>
      <input
        id="new-shop"
        use:focusOnMount
        type="text"
        maxlength="60"
        placeholder="Shop name"
        bind:value={newShop}
      />
      <button type="submit" class="solid" disabled={!newShop.trim() || network.offline}>Add</button>
      <button type="button" class="quiet" onclick={() => ((addingShop = false), (newShop = ''))}
        >Cancel</button
      >
    </form>
  {:else}
    <button
      type="button"
      class="addb"
      disabled={network.offline}
      onclick={() => (addingShop = true)}>+ New shop</button
    >
  {/if}
  {#if shopNote}<p class="warning-line" role="alert">{shopNote}</p>{/if}
  <p class="detail">Removing a shop moves its ingredients to “Any shop”, with Undo.</p>
</section>

<section class="card" aria-labelledby="places-title">
  <h3 id="places-title">Places at home</h3>
  <p class="detail">
    Where things are kept. Each kind tells Mealwright how long things last there.
  </p>
  <OrderedRows
    items={places}
    noun="place"
    disabled={network.offline}
    onorder={orderPlacesTo}
    onrename={renamePlaceTo}
    onremove={(place) => removePlaceRow(place)}
    removeBlocked={lastOfKind}
  >
    {#snippet after(place)}
      <span class="kind">{kindLabel(place.kind)}</span>
    {/snippet}
  </OrderedRows>
  {#if moving}
    <form
      class="move"
      aria-label="Move things out of {moving.place.name}"
      onsubmit={(event) => {
        event.preventDefault();
        if (moveTo !== null && moving) removePlaceRow(moving.place, moveTo);
      }}
    >
      <p class="note-line" tabindex="-1" use:askedMove>
        {moving.place.name} has {moving.things}
        {moving.things === 1 ? 'thing' : 'things'} in it. Move them to…
      </p>
      <label class="sr" for="move-to">Move them to</label>
      <select id="move-to" bind:value={moveTo}>
        {#each places.filter((p) => p.id !== moving?.place.id) as place (place.id)}
          <option value={place.id}>{place.name}</option>
        {/each}
      </select>
      <button type="submit" class="solid" disabled={moveTo === null || network.offline}
        >Move and remove</button
      >
      <button type="button" class="quiet" onclick={() => (moving = null)}>Cancel</button>
    </form>
  {/if}
  {#if addingPlace}
    <form class="add" onsubmit={addPlace}>
      <label class="sr" for="new-place">New place</label>
      <input
        id="new-place"
        use:focusOnMount
        type="text"
        maxlength="40"
        placeholder="Place name"
        bind:value={newPlace}
      />
      <label class="sr" for="new-place-kind">Kind</label>
      <select id="new-place-kind" bind:value={newKind}>
        {#each KINDS as kind (kind.value)}
          <option value={kind.value}>{kind.label}</option>
        {/each}
      </select>
      <button type="submit" class="solid" disabled={!newPlace.trim() || network.offline}>Add</button
      >
      <button type="button" class="quiet" onclick={() => ((addingPlace = false), (newPlace = ''))}
        >Cancel</button
      >
    </form>
  {:else}
    <button
      type="button"
      class="addb"
      disabled={network.offline}
      onclick={() => (addingPlace = true)}>+ New place</button
    >
  {/if}
  {#if placeNote}<p class="warning-line" role="alert">{placeNote}</p>{/if}
  <p class="detail">
    A place with things in it can’t be removed until they’re moved: Mealwright says how many and
    offers “Move them to…”.{hasFixed
      ? ' Mealwright needs at least one Fridge and one Freezer.'
      : ''}
  </p>
</section>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  h3 {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .detail {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .kind {
    flex: none;
    padding: 2px var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .addb {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .addb:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .add,
  .move {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-3);
  }

  .move {
    padding: var(--space-4);
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .note-line {
    flex: 1 1 100%;
    margin: 0;
    font-weight: var(--weight-semibold);
  }

  input,
  select {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-weight: var(--weight-semibold);
  }

  .solid {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-field);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
    cursor: pointer;
  }

  .solid:disabled {
    opacity: 0.4;
    cursor: default;
  }

  .quiet,
  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: inherit;
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  .note,
  .warning-line {
    margin: 0;
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .sr {
    position: absolute;
    left: -9999px;
  }
</style>
