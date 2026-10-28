<script lang="ts">
  // Shopping (mockups Shop, Desktop-Shop): the list split by shop, then by aisle, with ticked
  // items folded into "In the trolley" at the end of each shop. Ticking puts the item into the
  // pantry (phone: a toast with Change and Undo; desktop: the Put away panel). Every change
  // goes through sendAction (lib/shopping/actions.ts). Docs: docs/dev/sync-protocol.md section 13.
  // The list is built from the plan on the server (docs/dev/api-0.2.md section 6.3b); the
  // "Check you have these" card shows the staples the plan uses.
  import { untrack } from 'svelte';
  import { browser } from '$app/env';
  import AddBox from '#lib/components/shopping/AddBox.svelte';
  import DoubleTickCard from '#lib/components/shopping/DoubleTickCard.svelte';
  import ItemRow from '#lib/components/shopping/ItemRow.svelte';
  import ListPicker from '#lib/components/shopping/ListPicker.svelte';
  import PutAwayPanel from '#lib/components/shopping/PutAwayPanel.svelte';
  import StaplesCard from '#lib/components/shopping/StaplesCard.svelte';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { keepFocus } from '#lib/focusNear.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { live } from '#lib/live.svelte.js';
  import { ShoppingModel } from '#lib/shopping/store.svelte.js';

  const model = new ShoppingModel();
  const uid = $props.id();

  const WIDE = '(min-width: 768px)';
  let desktop = $state(browser && matchMedia(WIDE).matches);
  $effect(() => {
    const media = matchMedia(WIDE);
    const onChange = () => (desktop = media.matches);
    media.addEventListener('change', onChange);
    return () => media.removeEventListener('change', onChange);
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
    const group = model.groups.find((g) => g.trolley.some((v) => v.item.id === id));
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
    if (tab !== 'all' && !model.groups.some((g) => key(g.shopId) === tab)) tab = 'all';
  });

  const notesFor = (itemId: string) => model.notes.filter((n) => n.item_id === itemId);
  // Notes about the list as a whole. A note for an item that has gone sits where it was.
  const looseNotes = $derived(model.notes.filter((n) => !n.item_id));

  function showLine(itemId: string) {
    highlight = itemId;
    setTimeout(() => (highlight = null), 2500);
  }

  const empty = $derived(model.loaded && !!model.list && model.groups.length === 0);
</script>

<svelte:document onvisibilitychange={onVisible} />

<PageHeader title="Shopping" overline={model.subtitle || undefined} />

{#if model.problem && !model.list}
  <p class="problem" role="alert">{model.problem}</p>
{:else if !model.loaded || !model.list}
  <p class="loading">Loading…</p>
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
                      void model.clearTicked(group.trolley.map((v) => v.item));
                      back();
                    }}>Clear ticked</button
                  >
                {/if}
              </div>
              {#if fold}
                <ul class="card" id="{id}-trolley">
                  {#each group.trolley as view (view.item.id)}
                    <ItemRow {model} {view} trolley notes={notesFor(view.item.id)} />
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

  .problem {
    color: var(--color-warning-text);
  }

  .loading {
    color: var(--color-text-muted);
  }
</style>
