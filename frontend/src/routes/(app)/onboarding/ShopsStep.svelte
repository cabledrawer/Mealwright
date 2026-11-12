<script lang="ts">
  // Onboarding's "Where do you shop?" (0.9 U2): the household's shops, ✕ to remove one (with
  // Undo, as in Settings) and "+ Add a shop". Optional. The same endpoints as Settings → Shops and
  // places; renaming and putting them in order stay in Settings.
  import { onMount } from 'svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { serverUndo } from '#lib/client/changes.js';
  import { getShops } from '#lib/client/foods.js';
  import { removeShop } from '#lib/client/settingsLists.js';
  import type { Shop } from '#lib/client/types.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { focusOnMount } from '#lib/focusOnMount.js';
  import { network } from '#lib/network.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { save } from '#lib/save.js';

  const uid = $props.id();
  let shops = $state<Shop[]>([]);
  let adding = $state(false);
  let newShop = $state('');
  let problem = $state<string | null>(null);

  async function load() {
    try {
      shops = await getShops();
    } catch (error) {
      problem = cantReach(error) ? cantReachWords() : 'Couldn’t load your shops.';
    }
  }
  onMount(() => void load());

  const refreshShared = () => void placesAndShops.load(true).catch(() => {});

  function wordsOf(error: unknown): string {
    return error instanceof ApiError && !cantReach(error)
      ? error.detail
      : nothingChanged(network.deviceOffline);
  }

  function remove(shop: Shop) {
    const before = shops;
    void save({
      apply: () => (shops = before.filter((s) => s.id !== shop.id)),
      rollback: () => (shops = before),
      send: (key) => removeShop(shop.id, key),
      saved: refreshShared,
      undo: {
        label: `Removed the shop ${shop.name}`,
        skip: (done) => done.change === null,
        run: (done) =>
          done.change?.can_undo
            ? serverUndo(done.change.id, () => {
                refreshShared();
                void load();
              })()
            : false
      }
    });
  }

  async function add(event: SubmitEvent) {
    event.preventDefault();
    const name = newShop.trim();
    if (!name) return;
    problem = null;
    try {
      const shop = await placesAndShops.addShop(name);
      if (!shops.some((s) => s.id === shop.id)) shops = [...shops, shop];
      newShop = '';
      adding = false;
    } catch (error) {
      problem = wordsOf(error);
    }
  }
</script>

{#if shops.length}
  <ul class="people" aria-label="Shops">
    {#each shops as shop (shop.id)}
      <li class="row">
        <span class="label">{shop.name}</span>
        <button
          type="button"
          class="remove"
          aria-label="Remove {shop.name}"
          disabled={network.offline}
          onclick={() => remove(shop)}>✕</button
        >
      </li>
    {/each}
  </ul>
{/if}
{#if adding}
  <form class="add-form" onsubmit={add}>
    <label class="sr" for="{uid}-shop">New shop</label>
    <input
      id="{uid}-shop"
      use:focusOnMount
      type="text"
      autocomplete="off"
      maxlength="60"
      placeholder="Shop name"
      bind:value={newShop}
      disabled={network.offline}
    />
    <button type="submit" class="solid" disabled={!newShop.trim() || network.offline}>Add</button>
    <button type="button" class="quiet" onclick={() => ((adding = false), (newShop = ''))}
      >Cancel</button
    >
  </form>
{:else}
  <button type="button" class="add" disabled={network.offline} onclick={() => (adding = true)}
    >+ Add a shop</button
  >
{/if}
{#if problem}<p class="problem" role="alert">{problem}</p>{/if}
<p class="note">
  Just names, in the order you visit. Places at home start as Fridge, Freezer, Cupboard and Spice
  rack.
</p>
