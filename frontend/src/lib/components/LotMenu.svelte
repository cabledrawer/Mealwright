<script lang="ts">
  // What you can do with one packet (mockups Phone-Pantry, Desktop-Pantry): Used ·
  // Binned · To freezer · Move to… · Change use-by date…, and for an open packet the
  // ¼ · ½ · ¾ · Full picks. A small menu next to the packet on desktop, a sheet from the
  // bottom on phones. A real modal dialog: focus stays inside, Esc closes it, and focus
  // goes back to the packet's row.
  import { tick } from 'svelte';
  import type { Lot, Place } from '$lib/client/types';
  import { useByWords } from '$lib/dates';
  import type { PantryModel } from '$lib/pantry.svelte';
  import { pickFor } from '$lib/picks';
  import PackPicks from './PackPicks.svelte';

  let {
    lot,
    name,
    place,
    places,
    countedAs,
    anchor,
    model,
    startAt = 'actions',
    onclose
  }: {
    /** The packet, or null when the menu is closed. */
    lot: Lot | null;
    name: string;
    place: Place;
    places: Place[];
    countedAs: 'weight' | 'volume' | 'count';
    /** The row it was opened from: the desktop menu sits by it, and focus returns to it. */
    anchor: HTMLElement | null;
    model: PantryModel;
    /** "grams": open straight at "What's left" (from the opened row's "type it instead"). */
    startAt?: 'actions' | 'grams';
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let step = $state<'actions' | 'move' | 'date' | 'grams'>('actions');
  let date = $state('');

  const baseUnit = $derived(countedAs === 'weight' ? 'g' : countedAs === 'volume' ? 'ml' : 'count');
  const others = $derived(places.filter((p) => p.id !== place.id));

  $effect(() => {
    if (lot && !dialog.open) {
      step = startAt;
      date = lot.use_by ?? '';
      dialog.showModal();
      placeBy(anchor);
      void tick().then(() => dialog.querySelector<HTMLElement>('[data-first]')?.focus());
    } else if (!lot && dialog.open) {
      dialog.close();
    }
  });

  /** Desktop: just under the row (above it if there's no room), inside the window. */
  function placeBy(row: HTMLElement | null) {
    if (!row || matchMedia('(max-width: 767px)').matches) {
      dialog.style.removeProperty('top');
      dialog.style.removeProperty('left');
      return;
    }
    const box = row.getBoundingClientRect();
    const menu = dialog.getBoundingClientRect();
    const below = box.bottom + 4;
    const top =
      below + menu.height > innerHeight - 8 ? Math.max(8, box.top - menu.height - 4) : below;
    const left = Math.min(Math.max(8, box.left), innerWidth - menu.width - 8);
    dialog.style.top = `${top}px`;
    dialog.style.left = `${left}px`;
  }

  function close() {
    onclose();
    // Focus goes back to the packet's row.
    queueMicrotask(() => anchor?.focus());
  }

  function act(run: () => unknown) {
    run();
    close();
  }

  function typeLeft(event: SubmitEvent) {
    event.preventDefault();
    if (!lot) return;
    const text = String(new FormData(event.currentTarget as HTMLFormElement).get('left') ?? '')
      .trim()
      .replace(',', '.');
    const amount = Number(text);
    if (!text || !(amount >= 0)) return;
    const id = lot.id;
    act(() => model.setLeft(id, name, { amount: { amount, unit: baseUnit } }));
  }

  function saveDate(event: SubmitEvent) {
    event.preventDefault();
    if (!lot) return;
    const id = lot.id;
    const value = date || null;
    act(() => value !== lot?.use_by && model.setUseBy(id, name, value));
  }

  const about = $derived(lot ? (lot.stock.display.split(' · ').at(-1) ?? '') : '');
</script>

<dialog
  bind:this={dialog}
  class="lot-menu"
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    close();
  }}
  onclick={(event) => {
    if (event.target === dialog) close();
  }}
>
  {#if lot}
    {@const id = lot.id}
    <div class="body">
      <p class="title" id="{uid}-title">
        <b>{name}</b> · {lot.stock.display}{lot.open ? ' · open' : ''}
      </p>
      <p class="hint">{useByWords(lot.use_by, lot.days_left)}</p>

      {#if step === 'actions'}
        {#if lot.open || pickFor(lot) !== undefined}
          <div class="picks">
            <span class="hint" id="{uid}-q">How much is left? Best guess is fine.</span>
            <PackPicks
              {lot}
              {name}
              {model}
              labelledby="{uid}-q"
              onneedsamount={() => (step = 'grams')}
            />
            <span class="hint"
              >{about.charAt(0).toLocaleUpperCase() + about.slice(1)} ·
              <button type="button" class="link" onclick={() => (step = 'grams')}
                >type {baseUnit === 'g' ? 'grams' : baseUnit === 'ml' ? 'millilitres' : 'a number'} instead</button
              ></span
            >
          </div>
        {/if}
        <ul class="actions">
          <li>
            <button type="button" data-first onclick={() => act(() => model.used(id, name))}
              >Used</button
            >
          </li>
          <li>
            <button type="button" onclick={() => act(() => model.binned(id, name))}>Binned</button>
          </li>
          {#if place.kind !== 'freezer'}
            <li>
              <button type="button" onclick={() => act(() => model.toFreezer(id, name))}
                >To freezer</button
              >
            </li>
          {/if}
          {#if others.length}
            <li><button type="button" onclick={() => (step = 'move')}>Move to…</button></li>
          {/if}
          <li>
            <button type="button" onclick={() => (step = 'date')}>Change use-by date…</button>
          </li>
        </ul>
      {:else if step === 'move'}
        <p class="step" id="{uid}-move">Move to</p>
        <ul class="actions" aria-labelledby="{uid}-move">
          {#each others as other, i (other.id)}
            <li>
              <button
                type="button"
                data-first={i === 0 ? '' : undefined}
                onclick={() => act(() => model.move(id, name, other))}>{other.name}</button
              >
            </li>
          {/each}
        </ul>
      {:else if step === 'date'}
        <form class="form" onsubmit={saveDate}>
          <label>
            Use by
            <input type="date" bind:value={date} />
          </label>
          <span class="buttons">
            <button type="submit" class="main">Save</button>
            <button
              type="button"
              onclick={() => act(() => lot?.use_by !== null && model.setUseBy(id, name, null))}
              >No date</button
            >
          </span>
        </form>
      {:else}
        <form class="form" onsubmit={typeLeft}>
          <label>
            What's left{baseUnit === 'count' ? '' : ` (${baseUnit})`}
            <input name="left" inputmode="decimal" data-first />
          </label>
          <span class="buttons"><button type="submit" class="main">Save</button></span>
        </form>
      {/if}

      <button type="button" class="cancel" onclick={close}>
        {step === 'actions' ? 'Close' : 'Cancel'}
      </button>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    margin: 0;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-toast);
  }

  dialog::backdrop {
    background: transparent;
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .title {
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .hint,
  .step {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .step {
    font-weight: var(--weight-bold);
  }

  .actions {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .actions button,
  .cancel,
  .buttons button {
    width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-align: left;
    cursor: pointer;
  }

  .actions button:hover,
  .cancel:hover {
    background: var(--color-fill);
  }

  .cancel {
    color: var(--color-text-muted);
  }

  .picks {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5);
    border-radius: var(--radius-md);
    background: var(--color-ground);
  }

  .link {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  label {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  input {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .buttons {
    display: flex;
    gap: var(--space-3);
  }

  .buttons button {
    width: auto;
    text-align: center;
    background: var(--color-fill);
  }

  .buttons .main {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  /* Phone: a sheet from the bottom. */
  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      padding: var(--space-8) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    }
    dialog::backdrop {
      background: var(--color-overlay);
    }
  }

  /* Desktop: a small menu by the packet. */
  @media (min-width: 768px) {
    dialog {
      position: fixed;
      width: 280px;
      padding: var(--space-5);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
    }
  }
</style>
