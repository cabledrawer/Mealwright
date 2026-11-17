<script lang="ts">
  // "Your kitchen" (Batch cook, Experimental; mockup Dark-BatchKit08-Phone): hob rings, pressure
  // cookers and the oven, asked once on first use (B2 opens it) and changed in Settings, under
  // Kitchen. A phone sheet: a real modal dialog, Esc closes it, the focus goes back where it
  // came from. On a computer it is a box in the middle of the screen.
  import { tick } from 'svelte';
  import { ApiError, cantReach } from '#lib/api.js';
  import {
    MOST_HOB_RINGS,
    MOST_PRESSURE_COOKERS,
    saveKitchen,
    type Kitchen
  } from '#lib/client/household.js';
  import { nothingChanged } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import Icon from './Icon.svelte';

  let {
    open,
    kitchen,
    onsaved,
    onclose,
    save: send = saveKitchen
  }: {
    open: boolean;
    /** What the household has now (or the usual values before it has answered). */
    kitchen: Kitchen;
    /** Saved: the kitchen as the server stored it. */
    onsaved: (kitchen: Kitchen) => void;
    onclose: () => void;
    /** How it is saved (the gallery shows the sheet without saving anything). */
    save?: typeof saveKitchen;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let rings = $state(4);
  let cookers = $state(1);
  let oven = $state(true);
  let saving = $state(false);
  let problem = $state<string | null>(null);

  $effect(() => {
    if (open && !dialog.open) {
      rings = kitchen.hob_rings;
      cookers = kitchen.pressure_cookers;
      oven = kitchen.oven;
      problem = null;
      saving = false;
      dialog.showModal();
      void tick().then(() => dialog.querySelector<HTMLElement>('[data-first]')?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  });

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (saving) return;
    saving = true;
    problem = null;
    try {
      onsaved(await send({ hob_rings: rings, pressure_cookers: cookers, oven }));
    } catch (error) {
      problem =
        error instanceof ApiError && !cantReach(error)
          ? error.detail
          : nothingChanged(network.deviceOffline);
    } finally {
      saving = false;
    }
  }
</script>

<dialog
  bind:this={dialog}
  class="kitchen-sheet"
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={(event) => {
    if (event.target === dialog) onclose();
  }}
>
  {#if open}
    <form class="body" onsubmit={submit}>
      <span class="grab" aria-hidden="true"></span>
      <div class="head">
        <h2 class="title" id="{uid}-title">Your kitchen</h2>
        <button type="button" class="close" aria-label="Close" onclick={onclose}>
          <Icon name="close" size={18} stroke={2.4} />
        </button>
      </div>
      <p class="about">
        Batch cook never plans more at once than your kitchen has. Asked once; change it any time in
        Settings › Your kitchen.
      </p>
      <div class="card">
        <div class="row">
          <span class="what">
            <span class="name">Hob rings</span>
            <span class="detail">Burners on the cooker</span>
          </span>
          <button
            type="button"
            class="step"
            data-first
            aria-label="Fewer hob rings"
            disabled={rings <= 1}
            onclick={() => (rings -= 1)}>−</button
          >
          <span class="count" aria-live="polite">{rings}</span>
          <button
            type="button"
            class="step"
            aria-label="More hob rings"
            disabled={rings >= MOST_HOB_RINGS}
            onclick={() => (rings += 1)}>+</button
          >
        </div>
        <div class="row">
          <span class="what">
            <span class="name">Pressure cookers</span>
            <span class="detail">Including an Instant Pot</span>
          </span>
          <button
            type="button"
            class="step"
            aria-label="Fewer pressure cookers"
            disabled={cookers <= 0}
            onclick={() => (cookers -= 1)}>−</button
          >
          <span class="count" aria-live="polite">{cookers}</span>
          <button
            type="button"
            class="step"
            aria-label="More pressure cookers"
            disabled={cookers >= MOST_PRESSURE_COOKERS}
            onclick={() => (cookers += 1)}>+</button
          >
        </div>
        <div class="row">
          <span class="what"><span class="name" id="{uid}-oven">Oven</span></span>
          <div class="seg" role="radiogroup" aria-labelledby="{uid}-oven" use:radioKeys>
            <button type="button" role="radio" aria-checked={oven} onclick={() => (oven = true)}
              >Yes</button
            >
            <button type="button" role="radio" aria-checked={!oven} onclick={() => (oven = false)}
              >No</button
            >
          </div>
        </div>
      </div>
      {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
      <button type="submit" class="main" disabled={saving}>Save</button>
    </form>
  {/if}
</dialog>

<style>
  dialog {
    inset: auto 0 0 0;
    width: 100%;
    max-width: none;
    max-height: none;
    margin: 0;
    padding: var(--space-4) var(--space-8) max(32px, env(safe-area-inset-bottom));
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-toast);
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .grab {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .title {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
  }

  .close {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    cursor: pointer;
  }

  .about {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .card {
    padding: var(--space-2) var(--space-7);
    border-radius: 18px;
    background: var(--color-fill);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 56px;
    border-bottom: 1px solid var(--color-border);
  }

  .row:last-child {
    border-bottom: none;
  }

  .what {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .step {
    flex: none;
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-extrabold) 1.25rem var(--font-ui);
    cursor: pointer;
  }

  .step:disabled {
    cursor: default;
    opacity: 0.4;
  }

  .count {
    width: 24px;
    text-align: center;
    font-size: 1.25rem;
    font-weight: var(--weight-extrabold);
  }

  .seg {
    display: grid;
    grid-template-columns: 64px 64px;
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-fill-strong);
  }

  .seg button {
    min-height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .seg button[aria-checked='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-extrabold);
  }

  .problem {
    margin: 0;
    color: var(--color-warning-text);
    font-size: var(--text-base);
  }

  .main {
    min-height: 52px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-extrabold) 1rem var(--font-ui);
    cursor: pointer;
  }

  .main:disabled {
    cursor: default;
    opacity: 0.6;
  }

  /* A computer: a box in the middle of the screen, not a sheet the width of it. */
  @media (min-width: 768px) {
    dialog {
      inset: 0;
      width: min(440px, 100%);
      margin: auto;
      border-radius: var(--radius-xl);
    }

    .grab {
      display: none;
    }
  }
</style>
