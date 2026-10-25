<script lang="ts">
  // The status line under a ticked row (mockups ShopRows-*, option A; cabledrawer 20 Oct). It says
  // where the tick went and stays until the row is unticked or cleared:
  //   "In the Fridge · 2 L"  Change  Undo           (an amount went into the pantry)
  //   "Not in the pantry yet. No amount."  Add amount  (nothing went in)
  //   "Restocked · staples aren’t counted"  Undo     (a staple)
  import { putAwayWords, type PutAway } from '#lib/shopping/putAway.js';

  let {
    state,
    changing = false,
    name,
    onchange,
    onadd,
    onundo
  }: {
    state: PutAway;
    /** The place choices are showing. */
    changing?: boolean;
    /** The ingredient's name, for screen readers ("Undo ticking Milk"). */
    name: string;
    onchange: () => void;
    onadd: (button: HTMLElement) => void;
    onundo: () => void;
  } = $props();
</script>

<span class="line {state.kind}" role="group" aria-label="Where {name} went">
  <span class="words">{putAwayWords(state)}</span>
  {#if state.kind === 'amount'}
    <button
      type="button"
      aria-expanded={changing}
      aria-label="Change where {name} went"
      onclick={onchange}>Change</button
    >
  {:else if state.kind === 'none'}
    <button
      type="button"
      aria-label="Add amount for {name}"
      onclick={(event) => onadd(event.currentTarget)}>Add amount</button
    >
  {/if}
  {#if state.kind !== 'none'}
    <button type="button" aria-label="Undo ticking {name}" onclick={onundo}>Undo</button>
  {/if}
</span>

<style>
  .line {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 var(--space-5);
    min-height: 32px;
    padding: 0 var(--space-5);
    border-radius: var(--radius-md);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .words {
    padding: var(--space-2) 0;
  }

  /* Where it went: green. Nothing went in: amber. A staple: plain. */
  .amount {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .none {
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
  }

  .staple {
    background: var(--color-fill);
    color: var(--color-text);
  }

  button {
    position: relative;
    min-width: var(--touch-target);
    min-height: 32px;
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: inherit;
    font: inherit;
    text-decoration: underline;
    cursor: pointer;
  }

  /* The tap area is 44 px tall, as the rest of the app, though the line is slimmer. */
  button::before {
    content: '';
    position: absolute;
    inset: -6px 0;
  }
</style>
