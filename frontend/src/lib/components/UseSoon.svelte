<script lang="ts">
  // Use soon on the Pantry page (0.8 mockups Dark-Pantry08-Desktop and Dark-UseSoon08-Phone):
  // a strip of four cards across the top on a computer, compact rows on the phone (3 shown, then
  // "Show all N"). One row per ingredient and place, the soonest first ("Toor dal · 2 packets");
  // a passed Use by is red with Binned first and To freezer greyed out
  // ("Too late to freeze"); a passed Best before is grey. Either just says "Date passed"
  // (cabledrawer 15 Nov). Swipe a phone row right for Used…, left for Binned. Each row
  // also has its buttons in `actions()` order, so a keyboard or a screen reader can reach
  // every one (SwipeRow's rule; S5 review r1 M2). Binned and To freezer take every packet the
  // row stands for, with one Undo (S5 review r1 M1).
  import { resolve } from '$app/paths';
  import type { UseSoonLot, UseSoonTub } from '#lib/client/types.js';
  import { whenWords } from '#lib/dates.js';
  import { network } from '#lib/network.svelte.js';
  import type { PantryModel } from '#lib/pantry.svelte.js';
  import { blockedWhileDown } from '#lib/serverNeeded.js';
  import { TOO_LATE_TO_FREEZE, tooLateToFreeze } from '#lib/tooLateToFreeze.js';
  import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
  import SwipeRow from './SwipeRow.svelte';

  let {
    lots,
    tubs = [],
    model,
    phone,
    onhowmuch,
    oneaton
  }: {
    lots: UseSoonLot[];
    /** Leftover tubs that are Use soon: a card each, with "Eat it on…" (cabledrawer 7 Nov). */
    tubs?: UseSoonTub[];
    model: PantryModel;
    phone: boolean;
    /** "Used…": open the How much? sheet for this row. */
    onhowmuch: (lot: UseSoonLot) => void;
    /** "Eat it on…": open the meal choice for this tub card. */
    oneaton?: (tub: UseSoonTub) => void;
  } = $props();

  const uid = $props.id();
  /** The strip shows 4 cards and the phone 3 rows, until "Show all N". */
  const FIRST = $derived(phone ? 3 : 4);
  let all = $state(false);
  /** Packets and tubs together, soonest first (the same order as the server's: date, then name). */
  type Card = { key: string; lot?: UseSoonLot; tub?: UseSoonTub };
  const cards = $derived.by(() => {
    const found: { card: Card; by: string; name: string }[] = [
      ...lots.map((lot) => ({
        card: { key: `l${lot.id}`, lot },
        by: lot.use_by ?? '9999-12-31',
        name: lot.food.name
      })),
      ...tubs.map((tub) => ({
        card: { key: `t${tub.tub_id}`, tub },
        by: tub.use_by,
        name: tub.recipe_name
      }))
    ];
    found.sort(
      (a, b) =>
        a.by.localeCompare(b.by) || a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
    );
    return found.map((one) => one.card);
  });
  const shown = $derived(all ? cards : cards.slice(0, FIRST));
  const swiped = $state<Record<number, 'left' | 'right' | null>>({});

  function words(lot: UseSoonLot) {
    return whenWords(lot.date_kind, lot.use_by, lot.days_left, { capital: true, soon: true });
  }

  /** What is on a row: place and amount ("Fridge · 2 packets"). */
  const what = (lot: UseSoonLot) => `${lot.place.name} · ${lot.stock.short ?? lot.stock.display}`;

  /** Which buttons a row has, in order (cabledrawer 7 Nov): a passed Use by has Binned first;
   * anything else has Used, Binned and To freezer (To freezer only outside the freezer). A
   * packet too late to freeze keeps To freezer, greyed out with its note. */
  function actions(lot: UseSoonLot): ('used' | 'binned' | 'freezer')[] {
    const passed = lot.days_left !== null && lot.days_left < 0;
    const freezer = lot.place.kind === 'freezer' ? [] : (['freezer'] as const);
    if (passed && lot.date_kind === 'use_by') return ['binned', 'used', ...freezer];
    return ['used', 'binned', ...freezer];
  }

  const tubWhen = (tub: UseSoonTub) =>
    whenWords('use_by', tub.use_by, tub.days_left, { capital: true, soon: true });
  const tubWhat = (tub: UseSoonTub) => `${tub.place.name} · ${tub.words}`;

  const tooLate = (lot: UseSoonLot) => tooLateToFreeze(lot.date_kind, lot.days_left);

  const LABEL = { used: 'Used…', binned: 'Binned', freezer: 'To freezer' } as const;

  function press(lot: UseSoonLot, action: 'used' | 'binned' | 'freezer') {
    if (blockedWhileDown()) return;
    if (action === 'used') onhowmuch(lot);
    else if (action === 'binned') void model.binnedRow(lot);
    else void model.toFreezerRow(lot);
  }
</script>

<section class="soon" class:phone aria-labelledby="{uid}-h">
  <div class="head">
    <h2 id="{uid}-h">Use soon · {cards.length}</h2>
    {#if cards.length}
      <span class="links">
        <a href="{resolve('/(app)/recipes')}?filter=use-soon"
          >{phone ? 'Recipes that use them →' : 'Recipes that use them'}</a
        >
        {#if cards.length > FIRST}
          <button type="button" class="more" aria-expanded={all} onclick={() => (all = !all)}
            >{all ? 'Show fewer' : `Show all ${cards.length}`}</button
          >
        {/if}
      </span>
    {/if}
  </div>

  {#snippet pills(lot: UseSoonLot)}
    {#each actions(lot) as action (action)}
      <button
        type="button"
        class="pill"
        aria-describedby={action === 'freezer' && tooLate(lot)
          ? `${uid}-n${lot.id} ${uid}-f${lot.id}`
          : `${uid}-n${lot.id}`}
        disabled={network.offline || (action === 'freezer' && tooLate(lot))}
        onclick={() => press(lot, action)}>{LABEL[action]}</button
      >
    {/each}
  {/snippet}

  {#snippet lateNote(lot: UseSoonLot)}
    {#if tooLate(lot) && lot.place.kind !== 'freezer'}
      <p class="late-note" id="{uid}-f{lot.id}">{TOO_LATE_TO_FREEZE}</p>
    {/if}
  {/snippet}

  {#snippet eatIt(tub: UseSoonTub)}
    {#if tub.days_left < 0}
      <!-- A passed tub (cabledrawer 8 Nov): nothing to eat it on, so Binned. -->
      <button
        type="button"
        class="pill"
        aria-describedby="{uid}-nt{tub.tub_id}"
        disabled={network.offline}
        onclick={() => {
          if (!blockedWhileDown()) void model.binnedTub(tub);
        }}>Binned</button
      >
    {:else}
      <button
        type="button"
        class="pill"
        aria-describedby="{uid}-nt{tub.tub_id}"
        disabled={network.offline}
        onclick={() => {
          if (!blockedWhileDown()) oneaton?.(tub);
        }}>Eat it on…</button
      >
    {/if}
  {/snippet}

  {#snippet when(lot: UseSoonLot)}
    {@render whenTag(words(lot))}
  {/snippet}

  {#snippet whenTag(w: ReturnType<typeof words>)}
    <span class="when {w.tone}">{w.text}</span>
  {/snippet}

  {#if phone}
    <ul class="rows">
      {#each shown as card (card.key)}
        {@const lot = card.lot}
        {@const tub = card.tub}
        <li>
          {#if tub}
            <div class="r">
              <span class="name"
                ><b id="{uid}-nt{tub.tub_id}">{tub.recipe_name}</b><span>{tubWhat(tub)}</span></span
              >
              {@render whenTag(tubWhen(tub))}
            </div>
            <div class="btns row-btns">{@render eatIt(tub)}</div>
          {:else if lot}
            <SwipeRow
              bleed={0}
              bind:open={() => swiped[lot.id] ?? null, (side) => (swiped[lot.id] = side)}
              right={{
                label: 'Used…',
                describe: lot.food.name,
                icon: 'check',
                tone: 'used',
                run: () => {
                  if (!blockedWhileDown()) onhowmuch(lot);
                }
              }}
              left={{
                label: 'Binned',
                describe: lot.food.name,
                icon: 'trash',
                tone: 'danger',
                run: () => {
                  if (!blockedWhileDown()) void model.binnedRow(lot);
                }
              }}
            >
              <div class="r">
                <button
                  type="button"
                  class="name"
                  disabled={network.offline}
                  onclick={() => ingredientEditor.open(lot.food.id)}
                  ><b id="{uid}-n{lot.id}">{lot.food.name}</b><span>{what(lot)}</span></button
                >
                {@render when(lot)}
              </div>
              <div class="btns row-btns">{@render pills(lot)}</div>
              {@render lateNote(lot)}
            </SwipeRow>
          {/if}
        </li>
      {/each}
    </ul>
    <p class="note">Swipe a row: right for Used, left for Binned.</p>
  {:else if cards.length}
    <ul class="strip">
      {#each shown as card (card.key)}
        {@const lot = card.lot}
        {@const tub = card.tub}
        {#if tub}
          <li class="card" class:late={tubWhen(tub).tone === 'late'}>
            <span class="name"
              ><b id="{uid}-nt{tub.tub_id}">{tub.recipe_name}</b><span>{tubWhat(tub)}</span></span
            >
            {@render whenTag(tubWhen(tub))}
            <span class="btns">{@render eatIt(tub)}</span>
          </li>
        {:else if lot}
          <li class="card" class:late={words(lot).tone === 'late'}>
            <button
              type="button"
              class="name"
              disabled={network.offline}
              onclick={() => ingredientEditor.open(lot.food.id)}
              ><b id="{uid}-n{lot.id}">{lot.food.name}</b><span>{what(lot)}</span></button
            >
            {@render when(lot)}
            <span class="btns">{@render pills(lot)}</span>
            {@render lateNote(lot)}
          </li>
        {/if}
      {/each}
    </ul>
  {:else}
    <p class="hint">Nothing needs using up soon.</p>
  {/if}
</section>

<style>
  .soon {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-2) var(--space-8);
  }

  h2 {
    color: var(--color-use-soon-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  .links {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 var(--space-8);
  }

  .links a {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    color: var(--color-accent);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .more {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .hint,
  .note {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* The phone: a card of compact rows in a lighter style (F78). */
  .rows {
    padding: 2px 14px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .rows li {
    border-bottom: 1px solid var(--color-divider);
  }

  .rows li:last-child {
    border-bottom: none;
  }

  .r {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: 52px;
  }

  .name {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
    justify-content: center;
  }

  span.name {
    cursor: default;
  }

  .name b {
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .name span {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .when {
    display: inline-flex;
    flex-direction: column;
    max-width: 44%;
    padding: 4px 10px;
    border-radius: var(--radius-lg);
    background: var(--color-fill);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    line-height: 1.25;
  }

  .when.late {
    background: var(--color-use-soon-chip);
    color: var(--color-use-soon-text);
  }

  .when.soon {
    background: var(--color-tub-chip);
    color: var(--color-tub-chip-text);
  }

  .when.bb {
    background: var(--color-fill);
    color: var(--color-text-muted);
  }

  .pill {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .late-note {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .pill:disabled {
    color: var(--color-text-muted);
    cursor: default;
  }

  /* A computer: four cards across the top. */
  .strip {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 10px;
  }

  .card {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    min-width: 0;
    padding: 12px 14px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .card.late {
    border-color: var(--color-warning-border);
  }

  .card .name {
    flex: none;
    min-height: 0;
    width: 100%;
  }

  .card .name b {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .card .when {
    max-width: 100%;
  }

  .btns {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  /* The phone: a row's buttons on their own line under its name. */
  .row-btns {
    padding-bottom: 10px;
  }
</style>
