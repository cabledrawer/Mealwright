<script lang="ts">
  // One food in one place on the Pantry screen (mockups Phone-Pantry, Desktop-Pantry):
  // "Paneer · 2 packs · 400 g", its soonest date, and, opened, each packet with its date
  // and what you can do with it (Used, Binned, To freezer, Move, change the date). An
  // open packet gets the ¼ · ½ · ¾ · Full picks straight away (spec, Part-used packets).
  import type { Group, Lot, Place } from '$lib/client/types';
  import { dateWords, useByWords } from '$lib/dates';
  import { ingredientEditor } from '$lib/ingredientEditor.svelte';
  import type { PantryModel } from '$lib/pantry.svelte';
  import Icon from './Icon.svelte';

  let {
    group,
    place,
    places,
    model
  }: {
    group: Group;
    place: Place;
    places: Place[];
    model: PantryModel;
  } = $props();

  const uid = $props.id();
  let open = $state(false);
  /** The pick just made, shown before the server answers. */
  let picked = $state<Record<number, number>>({});
  let typing = $state<number | null>(null);

  const PICKS: { value: number; label: string }[] = [
    { value: 0.25, label: '¼' },
    { value: 0.5, label: '½' },
    { value: 0.75, label: '¾' },
    { value: 1, label: 'Full' }
  ];

  const name = $derived(group.food.name);
  const single = $derived(group.lots.length === 1 ? group.lots[0] : undefined);
  const date = $derived(dateWords(group.use_by, group.days_left));
  /** "½ tub · about 250 g · open · running low". */
  const amountWords = $derived(
    [group.stock.display, single?.open ? 'open' : '', group.running_low ? 'running low' : '']
      .filter(Boolean)
      .join(' · ')
  );
  const baseUnit = $derived(
    group.food.counted_as === 'weight' ? 'g' : group.food.counted_as === 'volume' ? 'ml' : 'count'
  );

  /** The pick nearest to what's left of a packet (to the nearest ¼). */
  function currentPick(lot: Lot): number | undefined {
    if (lot.id in picked) return picked[lot.id];
    const count = lot.stock.as_sold?.count;
    if (count === undefined) return undefined;
    return Math.min(1, Math.max(0.25, Math.round(count * 4) / 4));
  }

  function pick(lot: Lot, fraction: number) {
    picked = { ...picked, [lot.id]: fraction };
    void model.setLeft(lot.id, name, { fraction }).then((outcome) => {
      if (!outcome.ok) {
        const { [lot.id]: _dropped, ...rest } = picked;
        void _dropped;
        picked = rest;
      }
    });
  }

  function typeLeft(lot: Lot, event: Event) {
    const text = (event.currentTarget as HTMLInputElement).value.trim().replace(',', '.');
    typing = null;
    const amount = Number(text);
    if (!text || !(amount >= 0)) return;
    void model.setLeft(lot.id, name, { amount: { amount, unit: baseUnit } });
  }

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
    if (group.food.counted_as === 'count') {
      void model.leftOf(group.food.id, name, { amount: n, unit: 'count' }, place.id);
    } else if (n > 0) {
      void model.usedSome(group.food.id, name, { amount: n, unit: baseUnit }, place.id);
    }
  }

  function move(lot: Lot, event: Event) {
    const id = Number((event.currentTarget as HTMLSelectElement).value);
    const to = places.find((p) => p.id === id);
    if (to && to.id !== place.id) void model.move(lot.id, name, to);
  }

  function changeDate(lot: Lot, event: Event) {
    const value = (event.currentTarget as HTMLInputElement).value || null;
    if (value !== lot.use_by) void model.setUseBy(lot.id, name, value);
  }

  const capitalise = (text: string) => text.charAt(0).toLocaleUpperCase() + text.slice(1);

  function focusOnShow(node: HTMLElement) {
    node.focus();
  }
</script>

{#snippet picks(lot: Lot)}
  <div class="picks">
    <span class="hint" id="{uid}-{lot.id}-q">How much is left? Best guess is fine.</span>
    <div class="pick-row" role="radiogroup" aria-labelledby="{uid}-{lot.id}-q">
      {#each PICKS as p (p.value)}
        <button
          type="button"
          role="radio"
          aria-checked={currentPick(lot) === p.value}
          aria-label={p.label === 'Full' ? 'Full' : `${p.label} left`}
          onclick={() => pick(lot, p.value)}>{p.label}</button
        >
      {/each}
    </div>
    <span class="hint">
      {capitalise(lot.stock.display.split(' · ').at(-1) ?? '')} ·
      {#if typing === lot.id}
        <label class="type-left">
          <span class="visually-hidden"
            >What's left, in {baseUnit === 'count' ? 'items' : baseUnit}</span
          >
          <input
            inputmode="decimal"
            use:focusOnShow
            onchange={(event) => typeLeft(lot, event)}
            onblur={() => (typing = null)}
            onkeydown={(event) => {
              if (event.key === 'Enter') (event.currentTarget as HTMLInputElement).blur();
              if (event.key === 'Escape') typing = null;
            }}
          />
          {baseUnit === 'count' ? '' : baseUnit}
        </label>
      {:else}
        <button type="button" class="link" onclick={() => (typing = lot.id)}
          >type {baseUnit === 'g' ? 'grams' : baseUnit === 'ml' ? 'millilitres' : 'a number'} instead</button
        >
      {/if}
    </span>
  </div>
{/snippet}

<li class="group" class:has-picks={single?.open}>
  <button
    type="button"
    class="row"
    aria-expanded={open}
    aria-controls="{uid}-more"
    onclick={() => (open = !open)}
  >
    <span class="what">
      <span class="name">{name}</span>
      <span class="amount" class:low={group.running_low}>
        {amountWords}
        {#if group.lots_count > 1 && group.dates_count > 1}
          <span class="tap">· tap for dates</span><span class="click">· click for dates</span>
        {/if}
      </span>
    </span>
    {#if date}
      <span class="date" class:soon={group.use_soon}>{date}</span>
    {/if}
    <span class="chevron" class:flipped={open}
      ><Icon name="chevron-down" size={16} stroke={2.4} /></span
    >
  </button>

  {#if single?.open && !open}
    {@render picks(single)}
  {/if}

  {#if open}
    <div class="more" id="{uid}-more">
      {#each group.lots as lot (lot.id)}
        <div class="lot">
          <div class="lot-head">
            <span class="lot-amount">{lot.stock.display}{lot.open ? ' · open' : ''}</span>
            <span class="lot-date" class:soon={lot.use_soon}
              >{useByWords(lot.use_by, lot.days_left)}</span
            >
          </div>
          {#if lot.open}{@render picks(lot)}{/if}
          <div class="actions">
            <button type="button" class="pill" onclick={() => void model.used(lot.id, name)}
              >Used</button
            >
            <button type="button" class="pill" onclick={() => void model.binned(lot.id, name)}
              >Binned</button
            >
            {#if place.kind !== 'freezer'}
              <button type="button" class="pill" onclick={() => void model.toFreezer(lot.id, name)}
                >To freezer</button
              >
            {/if}
            <label class="small-field">
              Move to
              <select value={place.id} onchange={(event) => move(lot, event)}>
                {#each places as p (p.id)}<option value={p.id}>{p.name}</option>{/each}
              </select>
            </label>
            <label class="small-field">
              Use by
              <input
                type="date"
                value={lot.use_by ?? ''}
                onchange={(event) => changeDate(lot, event)}
              />
            </label>
          </div>
        </div>
      {/each}
      {#if group.lots.length > 1}<span class="hint">Oldest gets used first.</span>{/if}
      <form class="some" onsubmit={useSome}>
        {#if group.food.counted_as === 'count'}
          <label class="small-field">
            How many left?
            <input name="n" inputmode="numeric" placeholder="e.g. 3" />
          </label>
          <button type="submit" class="pill">Save</button>
        {:else}
          <label class="small-field">
            Used some ({baseUnit})
            <input name="n" inputmode="decimal" placeholder="e.g. 200" />
          </label>
          <button type="submit" class="pill">Used</button>
        {/if}
      </form>
      <button type="button" class="link" onclick={() => ingredientEditor.open(group.food.id)}>
        Edit {name.toLocaleLowerCase()}
      </button>
    </div>
  {/if}
</li>

<style>
  .group {
    list-style: none;
    border-top: 1px solid var(--color-divider);
  }

  .group:first-child {
    border-top: none;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    width: 100%;
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

  .chevron {
    flex: none;
    color: var(--color-text-muted);
    transition: transform 150ms ease;
  }

  .chevron.flipped {
    transform: rotate(180deg);
  }

  .picks {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0 -14px;
    padding: var(--space-5) 14px var(--space-6);
    background: var(--color-ground);
  }

  .pick-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--space-3);
  }

  .pick-row button {
    min-height: var(--touch-target);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .pick-row button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
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

  .type-left {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }

  .type-left input {
    width: 6rem;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .more {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: 0 0 var(--space-6) var(--space-6);
  }

  .lot {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding-top: var(--space-4);
    border-top: 1px dashed var(--color-divider);
  }

  .lot:first-child {
    border-top: none;
  }

  .lot .picks {
    margin: 0;
    padding: var(--space-4);
    border-radius: var(--radius-md);
  }

  .lot-head {
    display: flex;
    justify-content: space-between;
    gap: var(--space-4);
    font-size: var(--text-md);
  }

  .lot-amount {
    font-weight: var(--weight-semibold);
  }

  .lot-date {
    color: var(--color-text-muted);
    font-weight: var(--weight-semibold);
  }

  .lot-date.soon {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-bold);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-3);
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

  .some {
    display: flex;
    align-items: flex-end;
    gap: var(--space-3);
  }

  .some input {
    width: 7rem;
  }

  .small-field {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-bold);
  }

  .small-field select,
  .small-field input {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  /* Desktop: a little denser, inside a place column. */
  @media (min-width: 768px) {
    .row {
      min-height: var(--touch-target);
    }
    .name {
      font-size: var(--text-base);
    }
    .amount,
    .lot-head {
      font-size: var(--text-sm);
    }
    .date {
      font-size: var(--text-xs);
    }
    .tap {
      display: none;
    }
    .click {
      display: inline;
    }
    .picks {
      margin: 0 -8px;
      padding: var(--space-5) 8px;
      border-radius: var(--radius-md);
    }
    .small-field select,
    .small-field input {
      font-size: var(--text-md);
    }
  }
</style>
