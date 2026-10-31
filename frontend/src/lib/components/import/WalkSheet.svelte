<script lang="ts">
  // "2 lines aren’t linked yet" (mockup Dark-ImportSave07-Phone, spec "Importer consistency",
  // F4): Save found lines with no ingredient behind them. This goes through them one at a time:
  // New ingredient · Pick another · Treat as staple, with Skip this line, Back to Check and Save
  // anyway. A sheet on a phone, a dialog on a computer. Words proposed, for cabledrawer, except where
  // the mockup has them.
  import { onMount } from 'svelte';
  import FoodPicker from '#lib/components/FoodPicker.svelte';
  import type { Ref } from '#lib/client/types.js';
  import type { ImportFlow } from '#lib/import.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { amountWords } from '#lib/import.svelte.js';
  import { unitFor } from '#lib/recipeAmounts.js';

  let { flow, onsave }: { flow: ImportFlow; onsave: () => void } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let picking = $state(false);

  onMount(() => {
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  });

  const walk = $derived(flow.walk);
  const total = $derived(walk?.queue.length ?? 0);
  const at = $derived(walk?.at ?? 0);
  const index = $derived(flow.walkLine ?? 0);
  /** Null on the last card, when every line has had its turn. */
  const line = $derived(flow.walkLine === null ? undefined : flow.review?.lines[index]);
  const guess = $derived(flow.guessFor(index));
  const COUNTED = { weight: 'by weight', volume: 'by volume', count: 'one by one' } as const;

  const amount = $derived.by(() => {
    if (!line || line.amount === null) return '';
    const shown = flow.withPints(line);
    const text = shown.amount_text ?? amountWords(shown.amount ?? 0);
    return [text, shown.unit ? unitFor(shown.unit, shown.amount ?? 0) : ''].join(' ').trim();
  });
  const sub = $derived(
    guess
      ? `Counted ${COUNTED[guess.counted_as]}${guess.place ? ` · ${guess.place.name}` : ''}`
      : ''
  );

  // A new line starts with its buttons, not the picker.
  $effect(() => {
    void index;
    picking = false;
  });

  $effect(() => {
    if (!placesAndShops.places.length) void placesAndShops.load().catch(() => {});
  });

  function newIngredient(staple: boolean) {
    flow.newIngredient(index, staple);
    flow.walkNext();
  }

  function pick(food: Ref) {
    flow.sameAs(index, food);
    flow.walkNext();
  }
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  aria-describedby="{uid}-text"
  oncancel={(e) => {
    e.preventDefault();
    flow.walkClose();
  }}
  onclick={(e) => {
    if (e.target === dialog) flow.walkClose();
  }}
>
  {#if line}
    <div class="body">
      <span class="grip" aria-hidden="true"></span>
      <div class="head">
        <h2 id="{uid}-title">
          {total}
          {total === 1 ? 'line isn’t' : 'lines aren’t'} linked yet
        </h2>
        <p id="{uid}-text">
          Unlinked lines can’t be counted in your pantry or added to the shopping list properly.
          Sort them now, or save anyway and link them later in the recipe.
        </p>
      </div>

      <div class="progress">
        <span class="count">Line {at + 1} of {total}</span>
        <span class="bars" aria-hidden="true">
          {#each Array.from({ length: total }, (_, i) => i) as i (i)}
            <span class="bar" class:done={i <= at}></span>
          {/each}
        </span>
      </div>

      <div class="card" class:confirm={line.label === 'to_confirm'}>
        <span class="written">{line.written}</span>
        <span class="name"
          >{line.readable ? line.words : 'Couldn’t read this line'}
          {#if amount}<span class="amount">· {amount}</span>{/if}</span
        >
        <span class="not"
          >{line.label === 'to_confirm' && line.food
            ? `Close to “${line.food.name}”`
            : 'Not in your ingredients'}</span
        >
      </div>

      {#if picking}
        <FoodPicker
          label="Pick an ingredient for {line.written}"
          onpick={pick}
          oncancel={() => (picking = false)}
        />
      {:else}
        <div class="choices">
          {#if line.label === 'to_confirm' && line.food}
            <button type="button" class="main" onclick={() => pick(line.food!)}
              >Same as “{line.food.name}”</button
            >
          {:else}
            <button type="button" class="main" onclick={() => newIngredient(false)}>
              New ingredient{guess?.name ? ` “${guess.name}”` : ''}
              {#if sub}<span class="sub">{sub}</span>{/if}
            </button>
          {/if}
          <div class="grid">
            <button type="button" class="outline" onclick={() => (picking = true)}
              >Pick another</button
            >
            {#if line.label === 'to_confirm' && line.food}
              <button type="button" class="outline" onclick={() => newIngredient(false)}
                >New ingredient</button
              >
            {/if}
            <button type="button" class="outline" onclick={() => newIngredient(true)}
              >Treat as staple</button
            >
          </div>
          <button type="button" class="skip" onclick={() => flow.walkNext()}>Skip this line</button>
        </div>
      {/if}

      <div class="foot">
        <button type="button" class="back" onclick={() => flow.walkClose()}>Back to Check</button>
        <button type="button" class="anyway" disabled={flow.saving} onclick={onsave}
          >Save anyway</button
        >
      </div>
    </div>
  {:else if walk}
    <!-- The last card: every line has had its turn, and some are still not linked. -->
    {@const left = flow.unlinkedLines().length}
    <div class="body">
      <span class="grip" aria-hidden="true"></span>
      <div class="head">
        <h2 id="{uid}-title">
          {left}
          {left === 1 ? 'line' : 'lines'} left unlinked
        </h2>
        <p id="{uid}-text">
          You can save now and link {left === 1 ? 'it' : 'them'} later in the recipe, or go back to Check
          and sort {left === 1 ? 'it' : 'them'} there.
        </p>
      </div>
      <div class="foot last">
        <button type="button" class="back" onclick={() => flow.walkClose()}>Back to Check</button>
        <button type="button" class="anyway" disabled={flow.saving} onclick={onsave}
          >Save anyway</button
        >
      </div>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    width: min(100vw, 30rem);
    max-width: 100vw;
    max-height: 100dvh;
    margin: auto auto 0;
    padding: 10px 20px 28px;
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
  }

  @media (min-width: 768px) {
    dialog {
      width: min(100vw - 48px, 460px);
      margin: auto;
      padding: var(--space-9);
      border-radius: var(--radius-3xl);
    }

    .grip {
      display: none;
    }
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .grip {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .head {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  h2 {
    font-size: 20px;
    font-weight: var(--weight-extrabold);
  }

  .head p {
    color: var(--color-text-soft);
    font-size: 14px;
    line-height: 1.45;
  }

  .progress {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .count {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }

  .bars {
    display: flex;
    gap: 4px;
  }

  .bar {
    width: 22px;
    height: 6px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .bar.done {
    background: var(--color-accent);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 14px;
    border: 1px solid var(--color-warning-border);
    border-radius: 16px;
  }

  .card.confirm {
    border-color: var(--color-maybe-chip-border);
  }

  .written {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    overflow-wrap: anywhere;
  }

  .name {
    font-size: 17px;
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .amount {
    color: var(--color-text-soft);
    font-size: 14px;
    font-weight: var(--weight-semibold);
  }

  .not {
    color: var(--color-warning-text);
    font-size: 13px;
    font-weight: var(--weight-bold);
  }

  .card.confirm .not {
    color: var(--color-maybe-text);
  }

  .choices {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }

  button {
    cursor: pointer;
    font-family: inherit;
  }

  .main {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1px;
    min-height: 52px;
    border: none;
    border-radius: 14px;
    background: #2a7353; /* the mockup's green: white words on it pass AA */
    color: #fff;
    font-size: 15px;
    font-weight: var(--weight-extrabold);
  }

  .sub {
    color: #d7f2e3;
    font-size: 12px;
    font-weight: var(--weight-semibold);
  }

  .outline {
    min-height: 48px;
    border: 1px solid var(--color-border-strong);
    border-radius: 14px;
    background: transparent;
    color: var(--color-text);
    font-size: 14px;
    font-weight: var(--weight-bold);
  }

  .skip {
    min-height: 44px;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: 14px;
    font-weight: var(--weight-bold);
  }

  .foot {
    display: flex;
    gap: 10px;
    padding-top: 12px;
    border-top: 1px solid var(--color-border);
  }

  .foot.last {
    flex-direction: column-reverse;
    border-top: none;
  }

  .back,
  .anyway {
    flex: 1;
    min-height: 48px;
    border-radius: var(--radius-full);
    font-size: 14px;
  }

  .back {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }

  .anyway {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  button:disabled {
    opacity: 0.6;
    cursor: default;
  }
</style>
