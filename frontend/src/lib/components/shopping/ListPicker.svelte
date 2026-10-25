<script lang="ts">
  // The list picker under the title: This week (main list) · extra lists · + New list
  // (mockup Shop). Each list's "⋯" has Rename, and Remove for extra lists (Undo in the toast).
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';

  let { model }: { model: ShoppingModel } = $props();

  const uid = $props.id();
  let open = $state(false);
  let button = $state<HTMLButtonElement>();
  let optionsFor = $state<string | null>(null);
  let renaming = $state<string | null>(null);
  let renameText = $state('');
  let making = $state(false);
  let newName = $state('');

  const list = $derived(model.list);

  function close() {
    open = false;
    optionsFor = null;
    renaming = null;
    making = false;
  }

  function choose(id: string) {
    close();
    button?.focus();
    model.select(id);
  }

  function startRename(id: string, name: string) {
    renaming = id;
    renameText = name;
  }

  function rename(event: SubmitEvent, id: string) {
    event.preventDefault();
    const name = renameText.trim();
    close();
    if (name) void model.renameList(id, name);
  }

  function make(event: SubmitEvent) {
    event.preventDefault();
    const name = newName.trim();
    if (!name) return;
    newName = '';
    close();
    void model.createList(name);
  }

  function remove(id: string) {
    close();
    void model.removeList(id);
  }

  function describe(id: string, main: boolean) {
    const n = model.countsOf(id).toBuy;
    return main ? `Main list · ${n}` : `Extra list · ${n} · ticked items still go to the pantry`;
  }

  function focusOnShow(node: HTMLElement) {
    node.focus();
  }
</script>

<svelte:window
  onkeydown={(event) => {
    if (open && event.key === 'Escape') {
      close();
      button?.focus();
    }
  }}
/>

{#if list}
  <div class="picker">
    <button
      type="button"
      class="current"
      bind:this={button}
      aria-expanded={open}
      aria-controls="{uid}-menu"
      onclick={() => (open ? close() : (open = true))}
    >
      {list.name}<span class="tag">{list.main ? 'main list' : 'extra list'}</span>
      <svg
        aria-hidden="true"
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.6"
        stroke-linecap="round"
        stroke-linejoin="round"><path d="M6 9l6 6 6-6" /></svg
      >
    </button>
    {#if open}
      <div class="menu" id="{uid}-menu" role="group" aria-label="Lists">
        {#each model.lists as row (row.id)}
          <div class="entry">
            {#if renaming === row.id}
              <form class="inline" onsubmit={(e) => rename(e, row.id)}>
                <input aria-label="List name" bind:value={renameText} use:focusOnShow />
                <button type="submit" class="small">Save</button>
              </form>
            {:else}
              <button
                type="button"
                aria-current={row.id === list.id ? 'true' : undefined}
                class="choice"
                class:on={row.id === list.id}
                onclick={() => choose(row.id)}
              >
                <span class="text">
                  <span class="name">{row.name}</span>
                  <span class="sub">{describe(row.id, row.main)}</span>
                </span>
              </button>
              <button
                type="button"
                class="more"
                aria-label="{row.name} options"
                aria-expanded={optionsFor === row.id}
                onclick={() => (optionsFor = optionsFor === row.id ? null : row.id)}>⋯</button
              >
            {/if}
          </div>
          {#if optionsFor === row.id}
            <div class="options">
              <button type="button" class="small" onclick={() => startRename(row.id, row.name)}
                >Rename</button
              >
              {#if !row.main}
                <button type="button" class="small" onclick={() => remove(row.id)}>Remove</button>
              {/if}
            </div>
          {/if}
        {/each}
        {#if making}
          <form class="inline new" onsubmit={make}>
            <input
              aria-label="New list name"
              placeholder="Party on Saturday"
              bind:value={newName}
              use:focusOnShow
            />
            <button type="submit" class="small">Make list</button>
          </form>
        {:else}
          <button type="button" class="add" onclick={() => (making = true)}>+ New list</button>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .picker {
    position: relative;
  }

  .current {
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 44px;
    padding: 0 var(--space-6) 0 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .tag {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .menu {
    position: absolute;
    top: calc(100% + var(--space-3));
    left: 0;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    width: min(320px, calc(100vw - 2 * var(--space-7)));
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: 16px;
    background: var(--color-surface);
    box-shadow: 0 12px 30px rgba(23, 32, 28, 0.14);
  }

  .entry {
    display: flex;
    align-items: center;
  }

  .choice {
    display: flex;
    flex: 1;
    align-items: center;
    min-height: 52px;
    padding: var(--space-5) var(--space-6);
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    font-family: inherit;
    text-align: left;
    cursor: pointer;
  }

  .choice.on {
    background: var(--color-accent-soft);
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .more {
    width: var(--touch-target);
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: 1.25rem;
    cursor: pointer;
  }

  .options {
    display: flex;
    gap: var(--space-4);
    padding: 0 var(--space-6) var(--space-4);
  }

  .small {
    min-height: 40px;
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .add {
    min-height: 46px;
    padding: var(--space-6);
    border: none;
    border-top: 1px solid var(--color-divider);
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .inline {
    display: flex;
    flex: 1;
    gap: var(--space-4);
    padding: var(--space-3);
  }

  .inline input {
    flex: 1;
    min-width: 0;
    min-height: 44px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }
</style>
