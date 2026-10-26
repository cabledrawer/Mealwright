<script lang="ts">
  // The menu for something on the Plan (spec "Meal planner interactions": phone long-press
  // sheet; and the keyboard way to do everything a drag does):
  //   a meal or one thing in it: Move to… · Copy to… · Leftovers on… · Remove, then a day
  //   and a meal to pick; a recipe from the tray: the day and meal to plan it on;
  //   a day (Month): its meals.
  // "Whose tub?" and "To freezer" come with Cook once (0.6 PR 4), which makes the tubs.
  import type { DropMode } from '#lib/client/plan.js';
  import type { PlanActions, PlanTarget as Target } from '#lib/planActions.js';
  import {
    addDays,
    dayFull,
    dayOfMonth,
    dayShort,
    weekDays,
    weekStart,
    weekWords
  } from '#lib/planDates.js';
  import { itemName, mealName } from '#lib/planMeals.js';
  import PlanDays from './PlanDays.svelte';

  let {
    actions,
    target,
    onclose
  }: { actions: PlanActions; target: Target | null; onclose: () => void } = $props();

  const model = $derived(actions.model);
  let dialog: HTMLDialogElement;

  // Which step, and what has been picked so far.
  let mode = $state<DropMode | 'plan' | null>(null);
  let weekOf = $state('');
  let day = $state<string | null>(null);
  let slotId = $state<number | null>(null);

  // A new target starts again at the first step. A recipe has only the one: where.
  $effect(() => {
    if (target === null) return;
    mode = target.kind === 'recipe' ? 'plan' : null;
    day = null;
    slotId = null;
    const from =
      target.kind === 'meal' || target.kind === 'item'
        ? target.meal.date
        : target.kind === 'day'
          ? target.day
          : model.anchor || model.today;
    weekOf = weekStart(from, model.startsOn);
  });

  $effect(() => {
    if (target !== null && !dialog.open) dialog.showModal();
    else if (target === null && dialog.open) dialog.close();
  });

  const heading = $derived.by(() => {
    if (!target) return '';
    if (target.kind === 'day') return dayFull(target.day);
    if (target.kind === 'recipe') return target.recipe.name;
    if (target.kind === 'item') return itemName(target.item, model.plan);
    return mealName(target.meal, model.plan);
  });

  const subheading = $derived.by(() => {
    if (!target || target.kind === 'recipe' || target.kind === 'day') return '';
    return `${dayFull(target.meal.date)} · ${model.slotName(target.meal.slot_id)}`;
  });

  const question = $derived(
    mode === 'move'
      ? 'Move to…'
      : mode === 'copy'
        ? 'Copy to…'
        : mode === 'leftovers'
          ? 'Leftovers on…'
          : 'Plan it on…'
  );
  const confirmWords = $derived(
    mode === 'move'
      ? 'Move here'
      : mode === 'copy'
        ? 'Copy here'
        : mode === 'leftovers'
          ? 'Plan leftovers here'
          : 'Plan it here'
  );

  /** Moving or copying onto the very place it is in does nothing. */
  const samePlace = $derived(
    !!target &&
      (target.kind === 'meal' || target.kind === 'item') &&
      day === target.meal.date &&
      slotId === target.meal.slot_id
  );
  const ready = $derived(day !== null && slotId !== null && !samePlace && !actions.readonly);

  function choose() {
    if (!target || !ready || day === null || slotId === null) return;
    if (target.kind === 'recipe') {
      void model.add({ recipe: target.recipe }, day, slotId);
    } else if (target.kind === 'meal') {
      void model.drop({ meal: target.meal.id }, day, slotId, mode as DropMode);
    } else if (target.kind === 'item') {
      void model.drop({ item: target.item.id }, day, slotId, mode as DropMode);
    }
    onclose();
  }

  function remove() {
    if (!target) return;
    if (target.kind === 'meal') void model.removeMeal(target.meal.id);
    if (target.kind === 'item') void model.removeItem(target.item.id);
    onclose();
  }

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === dialog) onclose();
  }
</script>

<dialog
  bind:this={dialog}
  aria-label={heading || 'Plan'}
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={closeOnBackdrop}
  data-testid="plan-sheet"
>
  {#if target}
    <div class="body">
      <span class="handle" aria-hidden="true"></span>
      <header>
        {#if subheading}<p class="sub">{subheading}</p>{/if}
        <h2>{heading}</h2>
      </header>

      {#if actions.readonly}
        <p class="note" role="status">You’re offline. Plan changes when you’re back online.</p>
      {/if}

      {#if target.kind === 'day'}
        <PlanDays {actions} days={[target.day]} />
      {:else if mode === null}
        <div class="list">
          <button type="button" disabled={actions.readonly} onclick={() => (mode = 'move')}
            >Move to…</button
          >
          <button type="button" disabled={actions.readonly} onclick={() => (mode = 'copy')}
            >Copy to…</button
          >
          <button type="button" disabled={actions.readonly} onclick={() => (mode = 'leftovers')}
            >Leftovers on…</button
          >
          <button type="button" class="remove" disabled={actions.readonly} onclick={remove}
            >Remove</button
          >
        </div>
      {:else}
        <h3>{question}</h3>
        <div class="weekbar">
          <button
            type="button"
            aria-label="Earlier week"
            onclick={() => (weekOf = addDays(weekOf, -7))}>‹</button
          >
          <span>{weekWords(weekOf, model.today.slice(0, 4))}</span>
          <button
            type="button"
            aria-label="Later week"
            onclick={() => (weekOf = addDays(weekOf, 7))}>›</button
          >
        </div>
        <div class="days" role="group" aria-label="Day">
          {#each weekDays(weekOf) as d (d)}
            <button
              type="button"
              aria-pressed={day === d}
              aria-label={dayFull(d)}
              onclick={() => (day = d)}><span>{dayShort(d)}</span><b>{dayOfMonth(d)}</b></button
            >
          {/each}
        </div>
        <div class="slots" role="group" aria-label="Meal">
          {#each model.slotsOn as slot (slot.id)}
            <button
              type="button"
              aria-pressed={slotId === slot.id}
              onclick={() => (slotId = slot.id)}>{slot.name}</button
            >
          {/each}
        </div>
        {#if samePlace}<p class="note" role="status">
            It’s already there. Pick another day or meal.
          </p>{/if}
        <div class="buttons">
          <button
            type="button"
            class="back"
            onclick={() => (target?.kind === 'recipe' ? onclose() : (mode = null))}>Back</button
          >
          <button type="button" class="go" disabled={!ready} onclick={choose}>{confirmWords}</button
          >
        </div>
      {/if}
    </div>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    overscroll-behavior: contain;
    scrollbar-width: none;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    text-align: center;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  h3 {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  .note {
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-base);
  }

  .list {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  button {
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .list button {
    min-height: 54px;
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    text-align: left;
  }

  .list .remove {
    color: var(--color-warning-text);
    background: var(--color-warning);
  }

  .weekbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-weight: var(--weight-bold);
  }

  .weekbar button {
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-3xl);
  }

  .days {
    display: grid;
    grid-template-columns: repeat(7, minmax(0, 1fr));
    gap: var(--space-2);
  }

  .days button {
    display: flex;
    flex-direction: column;
    align-items: center;
    min-height: 54px;
    padding: var(--space-3) 0;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-sm);
  }

  .days b {
    font-size: var(--text-lg);
  }

  .slots {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .slots button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .days button[aria-pressed='true'],
  .slots button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .buttons {
    display: flex;
    gap: var(--space-4);
  }

  .back,
  .go {
    min-height: 54px;
    border: none;
    border-radius: var(--radius-button);
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  .back {
    padding: 0 var(--space-8);
    background: var(--color-fill-strong);
    color: var(--color-text);
  }

  .go {
    flex: 1;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      max-height: min(680px, calc(100dvh - 120px));
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(460px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }
    .handle {
      display: none;
    }
  }
</style>
