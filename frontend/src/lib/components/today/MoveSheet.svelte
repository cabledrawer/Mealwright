<script lang="ts">
  // "Move it" (mockups MoveIt-Phone, MoveIt-Desktop): quick picks Today and Tomorrow at the same
  // meal, a 7-day strip, then a meal. A meal that already has food gets it alongside. The old
  // meal is marked moved and keeps its place. The words are proposed, for cabledrawer.
  import { downLine } from '#lib/downWords.js';
  import { network } from '#lib/network.svelte.js';
  import type { WaitingMeal } from '#lib/client/today.js';
  import { addDays } from '#lib/dates.js';
  import { dayFull, dayOfMonth, dayShort } from '#lib/planDates.js';
  import type { TodayModel } from '#lib/today.svelte.js';
  import { dayInSentence, spotAt, spotWords, plannedDayWords } from '#lib/todayWords.js';
  import { untrack } from 'svelte';

  let {
    model,
    waiting,
    onclose
  }: { model: TodayModel; waiting: WaitingMeal | null; onclose: () => void } = $props();

  let dialog: HTMLDialogElement;
  let day = $state<string | null>(null);
  let slotId = $state<number | null>(null);

  const data = $derived(model.data);
  const today = $derived(data?.today ?? '');
  const name = $derived(waiting ? model.nameOf(waiting) : '');
  const days = $derived(today ? Array.from({ length: 7 }, (_, i) => addDays(today, i)) : []);

  // A new meal starts at the first quick pick that is somewhere else (today, else tomorrow).
  // Only a different meal resets the pick: a fresh copy of Today (a live update) keeps it.
  const mealId = $derived(waiting?.meal_id ?? null);
  $effect(() => {
    if (mealId === null) return;
    untrack(() => {
      if (!waiting || !today) return;
      day = today;
      slotId = waiting.slot_id;
    });
  });

  $effect(() => {
    if (waiting !== null && !dialog.open) dialog.showModal();
    else if (waiting === null && dialog.open) dialog.close();
  });

  const subtitle = $derived(
    waiting
      ? `was ${plannedDayWords(waiting.date, today).replace('Yesterday', 'yesterday')} ${model.slotName(waiting.slot_id).toLowerCase()}`
      : ''
  );

  const quick = $derived(
    waiting
      ? [
          { label: 'Today', day: today },
          { label: 'Tomorrow', day: addDays(today, 1) }
        ].map((q) => ({
          ...q,
          slot: waiting.slot_id,
          spot: data ? spotAt(data.plan, q.day, waiting.slot_id) : { state: 'free' as const }
        }))
      : []
  );

  const spot = $derived(
    data && day !== null && slotId !== null ? spotAt(data.plan, day, slotId) : null
  );
  const ready = $derived(
    !!waiting && day !== null && slotId !== null && spot?.state !== 'done' && !model.readonly
  );
  const confirmWords = $derived(day ? `Move to ${dayInSentence(day, today)}` : 'Move it');

  function go() {
    if (!waiting || !ready || day === null || slotId === null) return;
    void model.move(waiting, day, slotId);
    onclose();
  }

  function closeOnBackdrop(event: MouseEvent) {
    if (event.target === dialog) onclose();
  }
</script>

<dialog
  bind:this={dialog}
  aria-label={name ? `Move ${name} to` : 'Move it'}
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={closeOnBackdrop}
  data-testid="move-sheet"
>
  {#if waiting && data}
    <div class="body">
      <span class="handle" aria-hidden="true"></span>
      <header>
        <p class="sub">{subtitle}</p>
        <h2>Move {name} to…</h2>
      </header>

      <h3>Quick picks</h3>
      <div class="quick">
        {#each quick as q (q.label)}
          {@const same = q.day === waiting.date && q.slot === waiting.slot_id}
          <button
            type="button"
            aria-pressed={day === q.day && slotId === q.slot}
            disabled={same || q.spot.state === 'done'}
            onclick={() => {
              day = q.day;
              slotId = q.slot;
            }}
          >
            <span>{q.label} · {model.slotName(q.slot)}</span>
            <span class="state" class:alongside={q.spot.state === 'alongside'}
              >{spotWords(q.spot)}</span
            >
          </button>
        {/each}
      </div>

      <h3>Or pick a day</h3>
      <div class="days" role="group" aria-label="Day">
        {#each days as d (d)}
          <button
            type="button"
            aria-pressed={day === d}
            aria-label={dayFull(d)}
            onclick={() => (day = d)}><span>{dayShort(d)}</span><b>{dayOfMonth(d)}</b></button
          >
        {/each}
      </div>

      <div class="slots" role="group" aria-label="Meal">
        {#each data.slots as slot (slot.id)}
          {@const here = day === waiting.date && slot.id === waiting.slot_id}
          {@const s = day ? spotAt(data.plan, day, slot.id) : ({ state: 'free' } as const)}
          <button
            type="button"
            aria-pressed={slotId === slot.id}
            disabled={here || s.state === 'done'}
            onclick={() => (slotId = slot.id)}
          >
            <span>{slot.name}</span>
            <span class="state" class:alongside={s.state === 'alongside'}>
              {#if s.state === 'alongside'}<span class="what">{s.what}</span>{/if}
              {here ? 'was here' : spotWords(s)}
            </span>
          </button>
        {/each}
      </div>

      {#if model.readonly}
        <p class="note" role="status">
          {downLine(network.deviceOffline, (b) => `Today changes ${b.when}.`)}
        </p>
      {:else}
        <p class="note">You can undo a move.</p>
      {/if}

      <div class="buttons">
        <button type="button" class="back" onclick={onclose}>Cancel</button>
        <button type="button" class="go" disabled={!ready} onclick={go}>{confirmWords}</button>
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
    gap: var(--space-5);
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
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  button {
    font: inherit;
    cursor: pointer;
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .quick,
  .slots {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .quick button,
  .slots button {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2) var(--space-4);
    min-height: 54px;
    padding: var(--space-3) var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    text-align: left;
  }

  .state {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  .state.alongside {
    color: var(--color-use-soon-text);
  }

  .what {
    margin-right: var(--space-2);
    overflow-wrap: anywhere;
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

  button[aria-pressed='true'] {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  button[aria-pressed='true'] .state {
    color: inherit;
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
      max-height: min(720px, calc(100dvh - 80px));
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(500px, calc(100vw - 2 * var(--space-7)));
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
