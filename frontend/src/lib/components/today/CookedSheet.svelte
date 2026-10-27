<script lang="ts">
  // "Cooked it" (mockups CookedMeal-Phone, CookedMeal-Desktop): a short check sheet, filled in
  // but editable. In 0.6 it shows the portions and an optional "Any left over?" (tubs, in the
  // fridge or freezer, with a use-by); the table of ingredients taken from the pantry is 0.7's
  // review, so this answer does not touch the pantry. The words are proposed, for cabledrawer.
  import type { Leftovers, WaitingMeal } from '#lib/client/today.js';
  import { pickedDateWords } from '#lib/dates.js';
  import { useByWords } from '#lib/planMeals.js';
  import type { TodayModel } from '#lib/today.svelte.js';
  import { tubsWords, whenWords } from '#lib/todayWords.js';

  let {
    model,
    waiting,
    onclose
  }: { model: TodayModel; waiting: WaitingMeal | null; onclose: () => void } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  let count = $state(0);
  let place = $state<'fridge' | 'freezer'>('fridge');
  let chosen = $state<string | null>(null);
  let changing = $state(false);

  $effect(() => {
    if (waiting) {
      count = 0;
      place = 'fridge';
      chosen = null;
      changing = false;
    }
  });

  $effect(() => {
    if (waiting !== null && !dialog.open) dialog.showModal();
    else if (waiting === null && dialog.open) dialog.close();
  });

  const meal = $derived(waiting ? model.mealOf(waiting) : null);
  const name = $derived(waiting ? model.nameOf(waiting) : '');
  const today = $derived(model.data?.today ?? '');
  const useBy = $derived(
    chosen ?? (place === 'fridge' ? waiting?.use_by_fridge : waiting?.use_by_freezer) ?? today
  );
  const canKeep = $derived(waiting?.leftover_item_id != null);
  /** The portions the recipe was planned for: shown, not changed (nothing in 0.6 uses them). */
  const portions = $derived(
    meal?.items.find((i) => i.kind === 'recipe' && i.servings != null)?.servings ?? null
  );
  const subtitle = $derived(
    waiting && model.data
      ? `${whenWords(waiting.date, today)} · ${model.slotName(waiting.slot_id).toLowerCase()}`
      : ''
  );

  function confirm() {
    if (!waiting) return;
    const leftovers: Leftovers | null =
      count > 0 && canKeep
        ? {
            count,
            place_kind: place,
            item_id: waiting.leftover_item_id ?? undefined,
            ...(chosen ? { use_by: chosen } : {})
          }
        : null;
    void model.cooked(waiting, leftovers);
    onclose();
  }

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === dialog) onclose();
  }
</script>

<dialog
  bind:this={dialog}
  aria-label={name ? `Cooked ${name}` : 'Cooked it'}
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={closeOnBackdrop}
  data-testid="cooked-sheet"
>
  {#if waiting}
    <div class="body">
      <span class="handle" aria-hidden="true"></span>
      <header>
        <p class="sub">{subtitle}</p>
        <h2>Cooked {name}</h2>
      </header>

      {#if portions !== null}
        <p class="made">Made {portions} {portions === 1 ? 'portion' : 'portions'} · as planned</p>
      {/if}
      <p class="note">Your pantry isn’t changed by this yet.</p>

      {#if canKeep}
        <section class="left" aria-labelledby="{uid}-left">
          <div class="row">
            <span class="words"
              ><span class="label" id="{uid}-left">Any left over?</span><span class="hint"
                >Optional · makes tubs for later</span
              ></span
            >
            <span class="stepper" role="group" aria-label="Leftover tubs">
              <button
                type="button"
                aria-label="Fewer tubs"
                disabled={count <= 0}
                onclick={() => (count = Math.max(0, count - 1))}>−</button
              >
              <b aria-live="polite">{tubsWords(count)}</b>
              <button
                type="button"
                aria-label="More tubs"
                disabled={count >= 12}
                onclick={() => (count = Math.min(12, count + 1))}>+</button
              >
            </span>
          </div>

          {#if count > 0}
            <div class="places" role="group" aria-label="Where the tub goes">
              <button
                type="button"
                aria-pressed={place === 'fridge'}
                onclick={() => (place = 'fridge')}>Fridge</button
              >
              <button
                type="button"
                aria-pressed={place === 'freezer'}
                onclick={() => (place = 'freezer')}>Freezer</button
              >
            </div>
            <div class="useby">
              <span>Use by <b>{pickedDateWords(useBy)}</b> · {useByWords(useBy, today)}</span>
              <button type="button" class="link" onclick={() => (changing = !changing)}
                >Change</button
              >
            </div>
            {#if changing}
              <label class="date">
                <span class="visually-hidden">Use-by date</span>
                <input
                  type="date"
                  value={useBy}
                  onchange={(event) => (chosen = event.currentTarget.value || null)}
                />
              </label>
            {/if}
          {/if}
        </section>
      {/if}

      <div class="buttons">
        <button type="button" class="back" onclick={onclose}>Cancel</button>
        <button type="button" class="go" disabled={model.readonly} onclick={confirm}
          >Cooked it</button
        >
      </div>
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

  .made,
  .note {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: center;
  }

  .left {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-6);
    border-radius: var(--radius-xl);
    background: var(--color-ground);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .label {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .stepper {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }

  .stepper b {
    min-width: 4.5rem;
    text-align: center;
    font-size: var(--text-xl);
  }

  button {
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .stepper button {
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill-strong);
    color: var(--color-text);
    font-size: var(--text-3xl);
    line-height: 1;
  }

  .places {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .places button {
    min-height: var(--touch-target);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .places button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .useby {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    font-size: var(--text-base);
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: none;
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
    text-decoration: underline;
  }

  .date input {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
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
