<script lang="ts">
  // One ingredient in one place on the Pantry screen (mockups Phone-Pantry,
  // Desktop-Pantry): "Paneer · 400 g · 2 packs" and its soonest date. Opened, it lists
  // each packet ("200 g · 1 pack · use by Mon"), oldest first; tapping a packet opens
  // its menu (LotMenu: Used · Binned · To freezer · Move to… · Change use-by date…, and
  // the ¼ · ½ · ¾ · Full picks for an open one).
  import type { Group, Lot, Place } from '#lib/client/types.js';
  import { boughtWords, whenWords } from '#lib/dates.js';
  import { network } from '#lib/network.svelte.js';
  import { blockedWhileDown } from '#lib/serverNeeded.js';
  import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
  import type { PantryModel } from '#lib/pantry.svelte.js';
  import { listLabel, type PantryList } from '#lib/pantryList.svelte.js';
  import Icon from './Icon.svelte';
  import LotMenu from './LotMenu.svelte';
  import PackPicks from './PackPicks.svelte';
  import SwipeRow from './SwipeRow.svelte';
  import UsedSheet from './UsedSheet.svelte';
  import { pickFor } from '#lib/picks.js';

  let {
    group,
    place,
    places,
    model,
    shopping,
    showPlace = false,
    also = null,
    swipes = false,
    today = ''
  }: {
    group: Group;
    place: Place;
    places: Place[];
    model: PantryModel;
    /** "+ List" on a running-low row adds to the shopping list. */
    shopping: PantryList;
    /** In search results: "Toor dal · Cupboard". */
    showPlace?: boolean;
    /** In search results: "also called thuvaram paruppu". */
    also?: string | null;
    /** A phone: swipe right for Used…, left for Binned (the pack menu has both as buttons). */
    swipes?: boolean;
    /** The household's today: a row with no use-by says when it was bought. */
    today?: string;
  } = $props();

  const uid = $props.id();
  let open = $state(false);
  /** The packet whose menu is open, and the row it was opened from. */
  let menuFor = $state<Lot | null>(null);
  let anchor = $state<HTMLElement | null>(null);
  let menuStart = $state<'actions' | 'grams'>('actions');

  const name = $derived(group.food.name);
  const single = $derived(group.lots.length === 1 ? group.lots[0] : undefined);
  /** The soonest use-by; with none, "bought 20 Oct" (when the oldest packet went in). */
  const bought = $derived(
    !group.use_by && today && group.lots[0]?.added_on
      ? boughtWords(group.lots[0].added_on, today, group.lots[0].how_added)
      : ''
  );
  /** "Use by Mon" · "best before 1 Nov" · red or grey "Date passed" (red for a Use by, grey
   * for a Best before). Capital on the phone, where the words stand alone on a line. */
  const when = $derived(
    whenWords(group.date_kind, group.use_by, group.days_left, {
      capital: swipes,
      soon: group.use_soon
    })
  );
  const date = $derived(when.text || bought);
  /** "about 250 g · ½ tub · open · running low". */
  const amountParts = $derived(
    [
      group.stock.display,
      single?.open ? 'open' : '',
      group.running_low ? 'running low' : ''
    ].filter(Boolean)
  );
  const listed = $derived(shopping.onList(group.food.id));
  const baseUnit = $derived(
    group.food.counted_as === 'weight' ? 'g' : group.food.counted_as === 'volume' ? 'ml' : 'count'
  );

  // --- Swipes (phone) ------------------------------------------------------------------------------
  let usedOpen = $state(false);
  let swiped = $state<'left' | 'right' | null>(null);
  /** Binned takes the packet that goes first: the soonest use-by (the list is oldest first). */
  const first = $derived(group.lots[0]);
  const detail = $derived([place.name, group.stock.display, when.text].filter(Boolean).join(' · '));

  function usedAll() {
    usedOpen = false;
    if (single) void model.used(single.id, name);
    else void model.leftOf(group.food.id, name, { amount: 0, unit: baseUnit }, place.id);
  }

  function usedPart(amount: number) {
    usedOpen = false;
    void model.usedSome(group.food.id, name, { amount, unit: baseUnit }, place.id);
  }

  function leftNow(amount: number) {
    usedOpen = false;
    void model.leftOf(group.food.id, name, { amount, unit: 'count' }, place.id);
  }

  function openMenu(lot: Lot, event: MouseEvent, start: 'actions' | 'grams' = 'actions') {
    anchor = event.currentTarget as HTMLElement;
    menuStart = start;
    menuFor = lot;
  }

  /** A tap on a pick the server can't work out (needs_amount): open the typed-amount step. */
  function needsAmount(lot: Lot) {
    anchor = (document.activeElement as HTMLElement | null) ?? anchor;
    menuStart = 'grams';
    menuFor = lot;
  }

  /** "About 250 g left": what is left of the single packet, as its line says it. */
  const leftWords = $derived.by(() => {
    const about = single?.stock.display.split(' · ')[0] ?? '';
    return `${about.charAt(0).toLocaleUpperCase()}${about.slice(1)} left`;
  });

  /** What is typed in the "Used some" / "How many left?" box. */
  let typed = $state('');
  const typedNumber = $derived(Number(typed.trim().replace(',', '.')));
  /** "Used" waits for an amount: any number for "How many left?" (0 is fine), above 0 otherwise. */
  const canSave = $derived(
    typed.trim() !== '' && (group.food.counted_as === 'count' ? typedNumber >= 0 : typedNumber > 0)
  );

  /** "Used some" (weight, volume) or "How many left?" (count foods), for the whole food. */
  function useSome(event: SubmitEvent) {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const text = String(new FormData(form).get('n') ?? '')
      .trim()
      .replace(',', '.');
    const n = Number(text);
    if (!text || !(n >= 0)) return;
    form.reset();
    typed = '';
    if (group.food.counted_as === 'count') {
      void model.leftOf(group.food.id, name, { amount: n, unit: 'count' }, place.id);
    } else if (n > 0) {
      void model.usedSome(group.food.id, name, { amount: n, unit: baseUnit }, place.id);
    }
  }
</script>

<li class="group">
  {#snippet headRow()}
    <div class="head">
      <button
        type="button"
        class="row"
        aria-expanded={open}
        aria-controls="{uid}-more"
        onclick={() => (open = !open)}
      >
        <span class="what">
          <span class="name">{showPlace ? `${name} · ${place.name}` : name}</span>
          {#if also}<span class="also">{also}</span>{/if}
          <span class="amount" class:low={group.running_low}>
            {#each amountParts as part, i (i)}{i ? ' · ' : ''}<span class="part">{part}</span
              >{/each}
            {#if group.lots_count > 1 && group.dates_count > 1}
              <span class="tap">· tap for dates</span><span class="click">· click for dates</span>
            {/if}
          </span>
        </span>
        {#if date}
          <span
            class="date"
            class:soon={group.use_soon && !when.passed}
            class:late={when.tone === 'late'}
            class:bb={when.tone === 'bb'}>{date}</span
          >
        {/if}
        <span class="chevron" class:flipped={open}
          ><Icon name="chevron-down" size={16} stroke={2.4} /></span
        >
      </button>
      {#if group.running_low}
        <button
          type="button"
          class="to-list"
          class:listed
          aria-label={listLabel(name, listed)}
          onclick={() => void shopping.tap(group.food)}
        >
          {#if listed}<Icon name="check" size={14} stroke={3} />{/if}+ List
        </button>
      {/if}
    </div>
  {/snippet}
  {#if swipes && !open && first}
    <SwipeRow
      bleed={14}
      bind:open={swiped}
      right={{
        label: 'Used…',
        describe: name,
        icon: 'check',
        tone: 'used',
        run: () => {
          if (!blockedWhileDown()) usedOpen = true;
        }
      }}
      left={{
        label: 'Binned',
        describe: name,
        icon: 'trash',
        tone: 'danger',
        run: () => {
          if (!blockedWhileDown()) void model.binned(first.id, name);
        }
      }}
    >
      {@render headRow()}
    </SwipeRow>
  {:else}
    {@render headRow()}
  {/if}

  {#if open}
    <div class="more" id="{uid}-more">
      <ul class="lots" aria-label="Packets of {name}">
        {#each group.lots as lot (lot.id)}
          <li>
            <button
              type="button"
              class="lot"
              aria-haspopup="dialog"
              disabled={network.offline}
              onclick={(event) => openMenu(lot, event)}
            >
              <span class="lot-amount">{lot.stock.display}{lot.open ? ' · open' : ''}</span>
              <span class="lot-date" class:soon={lot.use_soon}
                >{whenWords(lot.date_kind, lot.use_by, lot.days_left).text || 'no date'}</span
              >
              <span class="lot-go" aria-hidden="true"
                ><Icon name="chevron-down" size={16} stroke={2.4} /></span
              >
            </button>
          </li>
        {/each}
      </ul>
      {#if group.lots.length > 1}<span class="hint">Oldest gets used first.</span>{/if}
      <!-- "What's left" on every packet (F122): the picks when its size is known, and always a
           way to type it, beside "Used some". Counted things have "How many left?" below. -->
      {#if single && (pickFor(single) !== undefined || group.food.counted_as !== 'count')}
        <div class="marks">
          {#if pickFor(single) !== undefined}
            <span class="small-label" id="{uid}-left">How much is left? Best guess is fine.</span>
            <PackPicks
              lot={single}
              {name}
              {model}
              labelledby="{uid}-left"
              onneedsamount={() => needsAmount(single)}
            />
          {/if}
          <span class="small-label"
            >{leftWords} ·
            <button
              type="button"
              class="link"
              disabled={network.offline}
              aria-label="type it instead: how much is left"
              onclick={(event) => openMenu(single, event, 'grams')}>type it instead</button
            ></span
          >
        </div>
      {/if}
      <form class="some" onsubmit={useSome}>
        {#if group.food.counted_as === 'count'}
          <label class="small-field">
            How many left?
            <input
              name="n"
              inputmode="numeric"
              maxlength="20"
              placeholder="for example 3"
              bind:value={typed}
            />
          </label>
          <button type="submit" class="pill" disabled={!canSave || network.offline}>Save</button>
        {:else}
          <label class="small-field">
            Used some ({baseUnit})
            <input
              name="n"
              inputmode="decimal"
              maxlength="20"
              placeholder="for example 200"
              bind:value={typed}
            />
          </label>
          <button type="submit" class="pill" disabled={!canSave || network.offline}>Used</button>
        {/if}
      </form>
      <button
        type="button"
        class="link"
        disabled={network.offline}
        onclick={() => ingredientEditor.open(group.food.id)}
      >
        Edit {name}
      </button>
    </div>
  {/if}

  {#if swipes}
    <UsedSheet
      open={usedOpen}
      {name}
      {detail}
      countedAs={group.food.counted_as}
      total={group.stock.amount}
      allWords={group.stock.short ?? group.stock.display}
      onall={usedAll}
      onpart={usedPart}
      onleft={leftNow}
      onclose={() => (usedOpen = false)}
    />
  {/if}

  <LotMenu
    lot={menuFor}
    {name}
    {place}
    {places}
    countedAs={group.food.counted_as}
    {anchor}
    {model}
    startAt={menuStart}
    onclose={() => (menuFor = null)}
  />
</li>

<style>
  .group {
    list-style: none;
    border-top: 1px solid var(--color-divider);
  }

  .group:first-child {
    border-top: none;
  }

  /* In a narrow column "+ List" drops under the amount instead of squeezing it. */
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0 var(--space-3);
  }

  /* "+ List" on a running-low row (mockups Desktop-Pantry, Dark-Pantry). */
  .to-list {
    display: inline-flex;
    flex: none;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .to-list.listed {
    border-color: transparent;
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .row {
    flex: 1 1 12rem;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 52px;
    padding: var(--space-3) 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .what {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .also {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-style: italic;
  }

  /* Each part of the amount stays whole ("about 50 g"), so a narrow column stacks the parts and
     never one word to a line (F223). */
  .part {
    white-space: nowrap;
  }

  .amount {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .amount.low {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-semibold);
  }

  .click {
    display: none;
  }

  .date {
    flex: none;
    max-width: 45%;
    text-align: right;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .date.soon {
    padding: 3px 9px;
    border-radius: var(--radius-full);
    background: var(--color-use-soon-chip);
    color: var(--color-use-soon-text);
    font-weight: var(--weight-bold);
  }

  /* A passed Use by is red; a passed Best before is grey and quiet (0.8). */
  .date.late {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-bold);
  }

  .date.bb {
    color: var(--color-text-muted);
  }

  .chevron {
    flex: none;
    color: var(--color-text-muted);
    transition: transform 150ms ease;
  }

  .chevron.flipped {
    transform: rotate(180deg);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
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

  .more {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: 0 0 var(--space-6) var(--space-6);
  }

  .lots {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  /* "200 g · 1 pack · use by Mon": tap for what you can do with it. */
  .lot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    column-gap: var(--space-3);
    width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-2) var(--space-3);
    font-size: var(--text-md);
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .lot:hover {
    background: var(--color-fill);
  }

  .lot:active {
    background: var(--color-fill-strong);
  }

  /* A small arrow at the end says "tap me": the packet's menu opens. */
  .lot-go {
    display: inline-flex;
    margin-left: auto;
    color: var(--color-text-muted);
    transform: rotate(-90deg);
  }

  .lot-amount {
    font-weight: var(--weight-semibold);
  }

  .lot-date::before {
    content: '· ';
    color: var(--color-text-muted);
  }

  .lot-date {
    color: var(--color-text-muted);
    font-weight: var(--weight-semibold);
  }

  .lot-date.soon {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-bold);
  }

  .pill {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .pill:disabled {
    border-color: var(--color-border);
    background: var(--color-fill);
    color: var(--color-text-muted);
    cursor: default;
  }

  .marks {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .small-label {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
  }

  .some {
    display: flex;
    align-items: flex-end;
    gap: var(--space-3);
  }

  .some label {
    flex: 1;
    min-width: 0;
  }

  .some input {
    width: 100%;
    max-width: 8rem;
  }

  .small-field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
  }

  .small-field input {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  /* Desktop: one line per ingredient, name · amount · date, inside a place card (F66). */
  @media (min-width: 768px) {
    .row {
      min-height: var(--touch-target);
    }
    .what {
      display: contents;
    }
    /* Neither the name nor the amount is ever cut: each wraps between words, the amount
       takes the room the name doesn't need, and "+ List" goes on its own line under. */
    .row {
      flex-basis: 100%;
      display: grid;
      grid-template-columns: minmax(auto, max-content) minmax(min-content, 1fr) auto 16px;
      column-gap: var(--space-4);
    }
    .name {
      /* At least 6rem; only a word longer than the room left breaks inside. */
      min-width: 6rem;
      font-size: var(--text-base);
      font-weight: var(--weight-semibold);
    }
    .also {
      grid-column: 1;
      grid-row: 2;
      font-size: var(--text-sm);
    }
    .amount,
    .lot {
      font-size: var(--text-sm);
    }
    .amount {
      min-width: 0;
      color: var(--color-text);
      text-align: right;
    }
    .date {
      max-width: 10rem;
      font-size: var(--text-xs);
    }
    .tap,
    .click {
      display: none;
    }
  }
</style>
