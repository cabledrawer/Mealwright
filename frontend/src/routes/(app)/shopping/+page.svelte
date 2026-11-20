<script lang="ts">
  import Loading from '#lib/components/Loading.svelte';
  // Shopping (mockups Shop, Desktop-Shop): the list split by shop, then by aisle, with ticked
  // items folded into "In the trolley" at the end of each shop. Ticking puts the item into the
  // pantry (phone: a toast with Change and Undo; desktop: the Put away panel). Every change
  // goes through sendAction (lib/shopping/actions.ts). Docs: docs/dev/sync-protocol.md section 13.
  // The list is built from the plan on the server (docs/dev/api-endpoints.md section 6.3b); the
  // "Check you have these" card shows the staples the plan uses.
  import { untrack } from 'svelte';
  import { browser } from '$app/env';
  import { resolve } from '$app/paths';
  import { ApiError } from '#lib/api.js';
  import { network } from '#lib/network.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';
  import AddBox from '#lib/components/shopping/AddBox.svelte';
  import DoubleTickCard from '#lib/components/shopping/DoubleTickCard.svelte';
  import ItemRow from '#lib/components/shopping/ItemRow.svelte';
  import ListPicker from '#lib/components/shopping/ListPicker.svelte';
  import PrintSheet from '#lib/components/shopping/PrintSheet.svelte';
  import PutAwayPanel from '#lib/components/shopping/PutAwayPanel.svelte';
  import StaplesCard from '#lib/components/shopping/StaplesCard.svelte';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { keepFocus } from '#lib/focusNear.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { printing, watchPrinting } from '#lib/printing.svelte.js';
  import { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import { inTrolleyOrder, joinTrolley, linesOf } from '#lib/shopping/view.js';
  import { DESKTOP_QUERY } from '#lib/layout.js';
  import { whenIdle } from '#lib/whenIdle.js';
  import { couldntAdd } from '#lib/errorWords.js';

  const model = new ShoppingModel();
  // On paper the page is the plain sheet of what is left to buy (PrintSheet).
  $effect(() => watchPrinting());
  const uid = $props.id();

  let desktop = $state(browser && matchMedia(DESKTOP_QUERY).matches);
  $effect(() => {
    const media = matchMedia(DESKTOP_QUERY);
    const onChange = () => (desktop = media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  });
  // Plan shopping: from 1100 px the page is one column by shop and aisle, with a column of
  // panels beside it (docs/mockups/Dark-ShopPlan08-Desktop.dc.html). Below that it is the
  // phone screen, as before.
  const PLAN = '(min-width: 1100px)';
  let plan = $state(browser && matchMedia(PLAN).matches);
  $effect(() => {
    const media = matchMedia(PLAN);
    const onChange = () => (plan = media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
  });
  // Why each line is there (Plan shopping) and whether "Make it a staple?" is offered (phone too)
  // come from the server's list read: ask again when the copy moves.
  $effect(() => {
    if (!model.loaded) return;
    void model.copy.cursor;
    void model.list?.id;
    void network.offline;
    untrack(() => void model.loadListRead());
  });

  // The bottom tabs show below 768 px, the sidebar from there up: "saving on this phone"
  // or "… on this computer" while offline.
  $effect(() => {
    model.device = desktop ? 'computer' : 'phone';
  });

  // Fetch again after a change elsewhere (an ingredient edit, a merge). The live stream (below)
  // covers other phones.
  $effect(() => {
    void kitchen.version;
    // Only kitchen.version is watched: load() reads and replaces the copy, which would
    // otherwise run this again for ever.
    untrack(() => void model.open());
  });

  // Another phone or window changed the list: ask what changed since our own counter. Our
  // own changes come back with their answer, so their counter is already ours.
  $effect(() => {
    const heard = live.shopping;
    untrack(() => {
      if (model.loaded && heard > model.copy.cursor) void model.load();
    });
  });

  function onVisible() {
    if (document.visibilityState === 'visible') void model.open();
  }

  let tab = $state<string>('all');
  let open = $state<Record<string, boolean>>({});
  let highlight = $state<string | null>(null);

  // The toast's Change (or a place button) names an item in a trolley: open that fold. The same
  // for "How much?" asked by a tick with no amount (F62): its row is in the fold.
  $effect(() => {
    const id = model.placing ?? model.askingHowMuch;
    if (!id) return;
    const group = model.groups.find((g) =>
      g.trolley.some((v) => linesOf(v).some((l) => l.item.id === id))
    );
    if (group) {
      const folded = `${uid}-${key(group.shopId)}`;
      untrack(() => (open = { ...open, [folded]: true }));
    }
  });

  const key = (shopId: number | null) => (shopId === null ? 'any' : String(shopId));
  const tabs = $derived(
    model.groups.length > 1
      ? [
          ...model.groups.map((g) => ({ id: key(g.shopId), label: `${g.name} · ${g.toBuy}` })),
          { id: 'all', label: 'All' }
        ]
      : []
  );
  const shown = $derived(
    tab === 'all' || model.groups.length < 2
      ? model.groups
      : model.groups.filter((g) => key(g.shopId) === tab)
  );
  $effect(() => {
    const known = model.groups.some((g) => key(g.shopId) === tab);
    if (tab !== 'all' && !known && !(plan && chips.some((c) => c.id === tab))) tab = 'all';
  });

  // Plan shopping's shop chips: every shop in Settings order (even with nothing to buy), and
  // "Any shop" when something is there.
  const chips = $derived([
    ...[...model.copy.shops]
      .sort((a, b) => a.position - b.position || a.id - b.id)
      .map((s) => ({
        id: String(s.id),
        label: s.name,
        count: model.groups.find((g) => g.shopId === s.id)?.toBuy ?? 0
      })),
    ...(model.groups.some((g) => g.shopId === null)
      ? [
          {
            id: 'any',
            label: 'Any shop',
            count: model.groups.find((g) => g.shopId === null)?.toBuy ?? 0
          }
        ]
      : [])
  ]);
  const total = $derived(model.groups.reduce((n, g) => n + g.toBuy, 0));
  const trolleyRows = $derived(
    joinTrolley(inTrolleyOrder(model.groups.flatMap((g) => g.trolley.flatMap(linesOf))))
  );
  // A dot for each shop, in the order of the shops (shops have no colour of their own).
  const DOTS = ['#2e9e6b', '#d99a1e', '#4a8fd6', '#c45fa0', '#8a6fd1', '#d9694a'];
  const dotOf = (shopId: number | null) => {
    const at = model.copy.shops.findIndex((s) => s.id === shopId);
    return shopId === null || at < 0 ? 'var(--color-text-muted)' : DOTS[at % DOTS.length]!;
  };
  let newShop = $state(false);
  let newShopName = $state('');
  async function addShop() {
    const name = newShopName.trim();
    if (!name) return;
    try {
      await placesAndShops.addShop(name);
      newShop = false;
      newShopName = '';
      await model.load();
    } catch (error) {
      toasts.problem(error instanceof ApiError ? error.detail : couldntAdd('the shop'));
    }
  }

  const notesFor = (itemId: string) => model.notes.filter((n) => n.item_id === itemId);
  // Notes about the list as a whole. A note for an item that has gone sits where it was.
  const looseNotes = $derived(model.notes.filter((n) => !n.item_id));

  function showLine(itemId: string) {
    highlight = itemId;
    setTimeout(() => (highlight = null), 2500);
  }

  const empty = $derived(model.loaded && !!model.list && model.groups.length === 0);

  // "Already have it" works offline (it is queued), so its code is fetched once the page is idle,
  // not on first use: a first-use fetch offline is blocked (Playwright's WebKit; a real phone
  // with no signal). A failed warm-up is forgotten; the sheet then fetches it when asked.
  $effect(() =>
    whenIdle(() => {
      void import('#lib/components/shopping/FoundSheet.svelte').catch(() => {});
    })
  );
</script>

<svelte:document onvisibilitychange={onVisible} />

{#if plan}
  <PageHeader title="Plan shopping" overline={model.subtitle || undefined}>
    {#snippet actions()}
      {#if model.loaded && model.list}
        <div class="addplan"><AddBox {model} desktop onexisting={showLine} /></div>
      {/if}
    {/snippet}
  </PageHeader>
{:else}
  <PageHeader title="Shopping" overline={model.subtitle || undefined} />
{/if}

{#if model.problem && !model.list}
  <p class="problem" role="alert">{model.problem}</p>
{:else if !model.loaded || !model.list}
  <Loading />
{:else if plan}
  <div class="plan">
    <section class="rows" aria-label="The list">
      <ListPicker {model} />

      {#if looseNotes.length}
        <ul class="loose" aria-label="Notes">
          {#each looseNotes as note (note.id)}
            <li>
              <span>{note.text}</span>
              {#if note.undo}
                <button type="button" onclick={() => void model.undo(note.undo!)}>Undo</button>
              {/if}
              <button
                type="button"
                aria-label="Dismiss: {note.text}"
                onclick={() => void model.dismissNote(note.id)}>✕</button
              >
            </li>
          {/each}
        </ul>
      {/if}

      {#if empty}
        <EmptyState title="Nothing to buy"
          >Add an item above. Ticking it puts it in the pantry.</EmptyState
        >
      {/if}

      {#each shown as group (key(group.shopId))}
        {@const id = `${uid}-${key(group.shopId)}`}
        <section class="shopblock" aria-labelledby="{id}-h">
          {#if model.groups.length > 1}
            <h2 class="shop-name" id="{id}-h" tabindex="-1">
              <span class="dot" style:background={dotOf(group.shopId)} aria-hidden="true"
              ></span>{group.name + ' '}<span class="count">· {group.toBuy}</span>
            </h2>
          {:else}
            <h2 class="visually-hidden" id="{id}-h" tabindex="-1">{group.name}</h2>
          {/if}
          {#each group.aisles as aisle (aisle.key)}
            <h3>{aisle.name}</h3>
            <ul class="rowlist">
              {#each aisle.items as view (view.item.id)}
                <ItemRow
                  {model}
                  {view}
                  plan
                  notes={notesFor(view.item.id)}
                  highlight={highlight === view.item.id}
                />
              {/each}
            </ul>
          {/each}
          {#each group.ghosts as ghost (ghost.note.id)}
            <p class="ghost">
              <span>{ghost.text}</span>
              {#if ghost.note.undo}
                <button type="button" onclick={() => void model.undo(ghost.note.undo!)}>Undo</button
                >
              {/if}
              <button
                type="button"
                aria-label="Dismiss: {ghost.note.text}"
                onclick={() => void model.dismissNote(ghost.note.id)}>✕</button
              >
            </p>
          {/each}
        </section>
      {/each}
    </section>

    <aside class="rail" aria-label="Shops, staples and trolley">
      <section class="panel" aria-label="Shops">
        <div class="panel-head">
          <h2>Shops</h2>
          <a href={resolve('/(app)/settings/shops-places')}>Manage</a>
        </div>
        <div class="chips" role="group" aria-label="Show shop">
          <button
            type="button"
            class="chip"
            aria-pressed={tab === 'all'}
            onclick={() => (tab = 'all')}>All · {total}</button
          >
          {#each chips as c (c.id)}
            <button
              type="button"
              class="chip"
              aria-pressed={tab === c.id}
              onclick={() => (tab = c.id)}>{c.label} · {c.count}</button
            >
          {/each}
          <button
            type="button"
            class="chip new"
            aria-expanded={newShop}
            disabled={network.offline}
            onclick={() => (newShop = !newShop)}>+ New shop</button
          >
        </div>
        {#if newShop}
          <form
            class="newshop"
            onsubmit={(event) => {
              event.preventDefault();
              void addShop();
            }}
          >
            <label class="visually-hidden" for="{uid}-newshop">Shop name</label>
            <input
              id="{uid}-newshop"
              type="text"
              maxlength="60"
              bind:value={newShopName}
              placeholder="Shop name"
            />
            <button type="submit" class="chip" disabled={!newShopName.trim()}>Add shop</button>
          </form>
        {/if}
        <p class="hint">⋯ on a row moves it to another shop.</p>
      </section>

      <StaplesCard {model} foldable />

      {#each model.cards as question (question.id)}
        <DoubleTickCard {model} {question} />
      {/each}

      {#if trolleyRows.length}
        <section class="panel" aria-label="In the trolley">
          <div class="panel-head">
            <h2>In the trolley · {trolleyRows.length}</h2>
            <button
              type="button"
              class="chip"
              onclick={(event) => {
                const back = keepFocus(event.currentTarget);
                void model.clearTicked(
                  trolleyRows.flatMap(linesOf).map((v) => v.item),
                  trolleyRows.length
                );
                back();
              }}>Clear ticked</button
            >
          </div>
          <ul class="rowlist trolley">
            {#each trolleyRows as view (view.item.id)}
              <ItemRow
                {model}
                {view}
                trolley
                clear
                notes={linesOf(view).flatMap((l) => notesFor(l.item.id))}
              />
            {/each}
          </ul>
        </section>
      {/if}

      <PutAwayPanel {model} />
    </aside>
  </div>
{:else}
  <div class="layout">
    <div class="main">
      <div class="controls">
        <ListPicker {model} />
        {#if tabs.length}
          <div class="tabs" role="group" aria-label="Shops">
            {#each tabs as t (t.id)}
              <button type="button" aria-pressed={tab === t.id} onclick={() => (tab = t.id)}
                >{t.label}</button
              >
            {/each}
          </div>
        {/if}
        <AddBox {model} {desktop} onexisting={showLine} />
      </div>

      <StaplesCard {model} />

      {#if !desktop}
        {#each model.cards as question (question.id)}
          <DoubleTickCard {model} {question} />
        {/each}
      {/if}

      {#if looseNotes.length}
        <ul class="loose" aria-label="Notes">
          {#each looseNotes as note (note.id)}
            <li>
              <span>{note.text}</span>
              {#if note.undo}
                <button type="button" onclick={() => void model.undo(note.undo!)}>Undo</button>
              {/if}
              <button
                type="button"
                aria-label="Dismiss: {note.text}"
                onclick={() => void model.dismissNote(note.id)}>✕</button
              >
            </li>
          {/each}
        </ul>
      {/if}

      {#if empty}
        <EmptyState title="Nothing to buy"
          >Add an item above. Ticking it puts it in the pantry.</EmptyState
        >
      {/if}

      {#each shown as group (key(group.shopId))}
        {@const id = `${uid}-${key(group.shopId)}`}
        <section class="shop" aria-labelledby="{id}-h">
          {#if tab === 'all' && model.groups.length > 1}
            <h2 class="shop-name" id="{id}-h" tabindex="-1">{group.name}</h2>
          {:else}
            <h2 class="visually-hidden" id="{id}-h" tabindex="-1">{group.name}</h2>
          {/if}
          <div class="aisles">
            {#each group.aisles as aisle (aisle.key)}
              <div class="aisle">
                <h3>{aisle.name}</h3>
                <ul class="card">
                  {#each aisle.items as view (view.item.id)}
                    <ItemRow
                      {model}
                      {view}
                      notes={notesFor(view.item.id)}
                      highlight={highlight === view.item.id}
                    />
                  {/each}
                </ul>
              </div>
            {/each}
          </div>
          {#each group.ghosts as ghost (ghost.note.id)}
            <p class="ghost">
              <span>{ghost.text}</span>
              {#if ghost.note.undo}
                <button type="button" onclick={() => void model.undo(ghost.note.undo!)}>Undo</button
                >
              {/if}
              <button
                type="button"
                aria-label="Dismiss: {ghost.note.text}"
                onclick={() => void model.dismissNote(ghost.note.id)}>✕</button
              >
            </p>
          {/each}
          {#if group.trolley.length}
            {@const fold = open[id] ?? false}
            <div class="fold">
              <div class="fold-head">
                <button
                  type="button"
                  class="fold-toggle"
                  aria-expanded={fold}
                  aria-controls="{id}-trolley"
                  onclick={() => (open = { ...open, [id]: !fold })}
                  >In the trolley · {group.trolley.length}</button
                >
                {#if fold}
                  <button
                    type="button"
                    class="clear"
                    onclick={(event) => {
                      const back = keepFocus(event.currentTarget);
                      void model.clearTicked(
                        group.trolley.flatMap(linesOf).map((v) => v.item),
                        group.trolley.length
                      );
                      back();
                    }}>Clear ticked</button
                  >
                {/if}
              </div>
              {#if fold}
                <ul class="card" id="{id}-trolley">
                  {#each group.trolley as view (view.item.id)}
                    <ItemRow
                      {model}
                      {view}
                      trolley
                      clear
                      notes={linesOf(view).flatMap((l) => notesFor(l.item.id))}
                    />
                  {/each}
                </ul>
              {/if}
            </div>
          {/if}
        </section>
      {/each}
    </div>

    {#if desktop}
      <aside class="side" aria-label="Put away and questions">
        {#each model.cards as question (question.id)}
          <DoubleTickCard {model} {question} />
        {/each}
        <PutAwayPanel {model} />
      </aside>
    {/if}
  </div>
{/if}

{#if printing.on && model.loaded && model.list}
  <PrintSheet groups={model.groups} builtFrom={model.builtFrom} />
{/if}

<style>
  .layout {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--space-9);
  }

  .main {
    display: flex;
    flex: 999 1 400px;
    flex-direction: column;
    gap: var(--space-7);
    min-width: 0;
  }

  .side {
    display: flex;
    flex: 1 1 300px;
    flex-direction: column;
    gap: var(--space-7);
    min-width: 0;
  }

  .controls {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .controls :global(.picker) {
    align-self: flex-start;
  }

  @media (min-width: 768px) {
    .controls {
      max-width: 640px;
    }
  }

  .tabs {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .tabs button {
    min-height: 44px;
    padding: 0 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .tabs button[aria-pressed='true'] {
    border-color: transparent;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }

  .shop {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .shop-name {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .visually-hidden {
    position: absolute;
    left: -9999px;
  }

  .aisles {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
    gap: var(--space-7);
    align-items: start;
  }

  .aisle {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  h3 {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    margin: 0;
    padding: var(--space-1) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    list-style: none;
  }

  .fold {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .fold-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .fold-toggle,
  .clear {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .clear {
    background: transparent;
    color: var(--color-accent);
  }

  .loose {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .loose li {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-2) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .loose span {
    flex: 1;
  }

  .loose button {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .ghost {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    margin: 0;
    padding: var(--space-1) var(--space-6);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    opacity: 0.85;
  }

  .ghost span {
    flex: 1;
  }

  .ghost button {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  /* Plan shopping (1100 px and wider). */
  .addplan {
    width: 380px;
  }

  .plan {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 340px;
    gap: var(--space-9);
    align-items: start;
  }

  .rows {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    max-width: 860px;
    min-width: 0;
  }

  .rows :global(.picker) {
    align-self: flex-start;
  }

  .shopblock {
    display: flex;
    flex-direction: column;
  }

  .shopblock .shop-name {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .dot {
    width: 10px;
    height: 10px;
    border-radius: 5px;
  }

  .count {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .shopblock h3 {
    padding: var(--space-4) 0 var(--space-2);
    font-size: var(--text-sm);
  }

  .rowlist {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .rail {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
  }

  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .panel h2 {
    font-size: 1rem;
    font-weight: var(--weight-extrabold);
  }

  .panel-head a {
    color: var(--color-accent);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    min-height: var(--touch-target);
    padding: 0 12px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .chip.new {
    color: var(--color-accent);
  }

  .chip:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .newshop {
    display: flex;
    gap: var(--space-3);
  }

  .newshop input {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .hint {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .problem {
    color: var(--color-warning-text);
  }
</style>
