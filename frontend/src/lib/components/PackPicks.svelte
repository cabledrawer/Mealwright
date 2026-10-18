<script lang="ts">
  // The ¼ · ½ · ¾ · Full marks for one packet: a radio group, shared by the packet's
  // menu (LotMenu) and the opened Pantry row (PantryGroup, single-packet foods).
  // Tapping one saves at once (model.setLeft, with Undo in the toast).
  import { ApiError } from '$lib/api';
  import type { Lot } from '$lib/client/types';
  import type { PantryModel } from '$lib/pantry.svelte';
  import { PICKS, pickFor } from '$lib/picks';
  import { radioKeys } from '$lib/radioKeys';

  let {
    lot,
    name,
    model,
    labelledby,
    onneedsamount
  }: {
    lot: Lot;
    name: string;
    model: PantryModel;
    /** The id of the text that asks "How much is left?". */
    labelledby: string;
    /** Called when the packet has no size, so a fraction can't be worked out. */
    onneedsamount?: () => void;
  } = $props();

  /** What was just tapped, shown at once. Cleared when the saved amount changes (unless
   *  another tap is still saving, so a quick second tap doesn't flick back), or when the
   *  last tap's save fails. */
  let picked = $state<number | null>(null);
  let taps = 0;
  let saving = 0;
  $effect(() => {
    void lot.stock.amount;
    if (saving === 0) picked = null;
  });

  const current = $derived(picked ?? pickFor(lot));

  function pick(fraction: number) {
    picked = fraction;
    const tap = ++taps;
    saving += 1;
    void model.setLeft(lot.id, name, { fraction }).then((outcome) => {
      saving -= 1;
      if (!outcome.ok && tap === taps) picked = null;
      if (
        !outcome.ok &&
        outcome.error instanceof ApiError &&
        outcome.error.code === 'needs_amount'
      ) {
        onneedsamount?.();
      }
    });
  }
</script>

<div class="fit">
  <div
    class="pick-row"
    role="radiogroup"
    aria-labelledby={labelledby}
    use:radioKeys={{ select: false }}
  >
    {#each PICKS as p (p.value)}
      <button
        type="button"
        role="radio"
        aria-checked={current === p.value}
        aria-label={p.label === 'Full' ? 'Full' : `${p.label} left`}
        onclick={() => pick(p.value)}>{p.label}</button
      >
    {/each}
  </div>
</div>

<style>
  .fit {
    container-type: inline-size;
  }

  .pick-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-3);
  }

  /* Too narrow for four 44 px marks in a row (a desktop Pantry column): two rows of two. */
  @container (max-width: 211px) {
    .pick-row {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  button {
    min-height: var(--touch-target);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    white-space: nowrap;
    cursor: pointer;
  }

  button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }
</style>
