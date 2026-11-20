<script lang="ts">
  // "Make “For the batter” its own recipe?" (mockup Dark-CheckOwnRecipe08-Phone; F190, cabledrawer
  // 8 Nov): the new recipe's name and what it makes, asked and prefilled from the heading and the
  // lines. A sheet on a phone, a dialog on a computer. Loaded when first opened.
  import { onMount, untrack } from 'svelte';
  import type { ImportFlow } from '#lib/import.svelte.js';
  import {
    OWN_NAME_TAKEN,
    OWN_UNITS,
    otherSectionCalled,
    ownDefaults,
    ownLineWords,
    sectionOf
  } from '#lib/importOwn.js';
  import { makeOwn } from '#lib/importOwnEdits.js';
  import { holdUndo } from '#lib/undo.svelte.js';
  import '#lib/styles/fields.css';

  let { flow, heading, onclose }: { flow: ImportFlow; heading: number; onclose: () => void } =
    $props();

  // Read once, when the sheet opens: the sheet is made for one heading and is closed with it.
  const { review, line, kept, start } = untrack(() => {
    const review = flow.review!;
    const line = review.lines[heading]!;
    const kept = line.own ?? null;
    const start = kept
      ? { name: kept.name, amount: String(kept.amount), unit: kept.unit }
      : ownDefaults(review, heading);
    return { review, line, kept, start };
  });
  let name = $state(start.name);
  let amount = $state(start.amount);
  let unit = $state(start.unit);
  let problem = $state<string | null>(null);

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  onMount(() => {
    const letGo = holdUndo(); // Ctrl+Z must not move the lines behind this sheet
    dialog.showModal();
    return () => {
      letGo();
      if (dialog.open) dialog.close();
    };
  });

  const section = $derived(sectionOf(review, heading));
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  /** The whole number or decimal typed in "It makes", or null. */
  const made = $derived.by(() => {
    const value = Number(amount.trim().replace(',', '.'));
    return amount.trim() !== '' && Number.isFinite(value) && value > 0 && value <= 100_000
      ? value
      : null;
  });
  const words = $derived(
    count(section.lines.length, 'line', 'lines') +
      (section.steps.length > 0 ? ` and ${count(section.steps.length, 'step', 'steps')}` : '')
  );

  /** The one line the main recipe gets, as far as it is typed. */
  const preview = $derived(
    made === null
      ? name.trim() || 'the new recipe'
      : ownLineWords({ name: name.trim() || 'the new recipe', amount: made, unit })
  );

  function done() {
    const typed = name.replace(/\s+/g, ' ').trim();
    if (!typed) {
      problem = 'Type a name.';
      return;
    }
    if (made === null) {
      problem = 'Type how much it makes.';
      return;
    }
    if (otherSectionCalled(review, heading, typed) !== null) {
      problem = OWN_NAME_TAKEN;
      return;
    }
    makeOwn(flow, heading, { name: typed, amount: made, unit });
    onclose();
  }
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  aria-describedby="{uid}-text"
  oncancel={(e) => {
    e.preventDefault();
    onclose();
  }}
  onclick={(e) => {
    if (e.target === dialog) onclose();
  }}
>
  <form
    class="body"
    onsubmit={(e) => {
      e.preventDefault();
      done();
    }}
  >
    <span class="grip" aria-hidden="true"></span>
    <h2 id="{uid}-title">Make “{line.words}” its own recipe?</h2>
    <p id="{uid}-text">
      It becomes a new recipe, <b>{name.trim() || 'the new recipe'}</b>, with its {words}, kept as
      <b>Made ahead</b>. {flow.name.trim() || 'This recipe'} then uses it as one line: “{preview}”.
    </p>
    <label class="field" for="{uid}-name">
      <span>Name of the new recipe</span>
      <input
        id="{uid}-name"
        class="mw-input"
        type="text"
        maxlength="100"
        autocomplete="off"
        bind:value={name}
      />
    </label>
    <div class="field" role="group" aria-labelledby="{uid}-makes">
      <span id="{uid}-makes">It makes</span>
      <span class="makes">
        <input
          class="mw-input amount"
          type="text"
          inputmode="decimal"
          maxlength="10"
          autocomplete="off"
          aria-label="How much it makes"
          bind:value={amount}
        />
        <select class="mw-input" aria-label="Unit" bind:value={unit}>
          {#each OWN_UNITS as option (option.unit)}
            <option value={option.unit}>{option.words}</option>
          {/each}
        </select>
      </span>
    </div>
    <p class="foot">Both recipes are checked here and saved together.</p>
    {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
    <div class="buttons">
      <button type="submit" class="go">{kept ? 'Done' : 'Make it its own recipe'}</button>
      <button type="button" class="cancel" onclick={onclose}>Cancel</button>
    </div>
  </form>
</dialog>

<style>
  dialog {
    width: min(100vw, 30rem);
    max-width: 100vw;
    max-height: none;
    margin: auto auto 0;
    padding: var(--space-5) var(--space-8) var(--space-9);
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
    gap: var(--space-5);
  }

  .grip {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  p {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  p b {
    color: var(--color-text);
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .makes {
    display: flex;
    gap: var(--space-4);
  }

  .amount {
    width: 5rem;
    flex: none;
  }

  .makes select {
    flex: 1;
  }

  .foot {
    font-size: var(--text-sm);
    color: var(--color-text-muted);
  }

  .problem {
    color: var(--color-warning-text);
    font-weight: var(--weight-semibold);
  }

  .buttons {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .go,
  .cancel {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 52px;
    border-radius: var(--radius-button);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .go {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .cancel {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-text);
  }

  @media (min-width: 768px) {
    .buttons {
      flex-direction: row-reverse;
      justify-content: flex-start;
      align-items: center;
    }

    .go {
      min-height: var(--touch-target);
      padding: 0 var(--space-7);
      border-radius: var(--radius-full);
    }
  }
</style>
