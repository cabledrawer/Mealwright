<script lang="ts">
  // "Different pack?" (mockup Shop): "What did you buy?" with the planned pack, one pack of
  // the planned amount, the ingredient's own sizes, and Other…; "Pantry gets 1 pack · 400 g."
  // and Done. The same panel, titled "How much?", for an item with no amount (spec L303).
  import { baseText, packText, pantryGets, unitsFor } from '$lib/shopping/format';
  import type { ShoppingModel } from '$lib/shopping/store.svelte';
  import type { FoodSize, ListItem, ShopFood, Tick } from '$lib/shopping/types';
  import { radioKeys } from '$lib/radioKeys';

  let {
    model,
    item,
    food,
    ticks,
    onclose
  }: {
    model: ShoppingModel;
    item: ListItem;
    food: ShopFood;
    /** The purchases still counted: more than one after "Did you buy 2?". */
    ticks: Tick[];
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let sizes = $state<FoodSize[]>([]);
  interface Choice {
    key: string;
    count: number;
    pack: number;
    sizeId: number | null;
  }
  let picked = $state<string | null>(null);
  let tickId = $state('');
  let problem = $state<string | null>(null);
  $effect.pre(() => {
    if (!tickId) tickId = ticks[0]?.id ?? '';
  });
  let initial: string | null = null;
  let otherCount = $state('1');
  let otherAmount = $state('');
  let otherUnit = $state('');

  $effect(() => {
    void model.sizesOf(food.id).then((s) => {
      sizes = s;
      if (initial === null && choices.length && item.amount) {
        initial = choices[0]!.key;
        picked = initial;
      }
    });
  });

  const units = $derived(unitsFor(food.counted_as));
  $effect(() => {
    if (!otherUnit) otherUnit = units[0]!.name;
  });

  const choices = $derived.by(() => {
    const out: Choice[] = [];
    const seen: string[] = [];
    const add = (count: number, pack: number, sizeId: number | null) => {
      const key = `${count}x${pack}`;
      if (seen.includes(key) || !(pack > 0)) return;
      seen.push(key);
      out.push({ key, count, pack, sizeId });
    };
    const planned = item.amount;
    const size = sizes.find((s) => s.id === item.size_id);
    if (planned) {
      if (size && Number.isInteger(planned / size.amount) && planned / size.amount > 1) {
        add(planned / size.amount, size.amount, size.id);
      }
      add(1, planned, size && planned === size.amount ? size.id : null);
    }
    for (const s of sizes) add(1, s.amount, s.id);
    return out;
  });

  const other = $derived.by(() => {
    const count = Math.floor(Number(otherCount));
    const unit = units.find((u) => u.name === otherUnit) ?? units[0]!;
    const amount = Number(otherAmount.replace(',', '.')) * unit.factor;
    return count >= 1 && count <= 99 && amount > 0 ? { count, pack: amount } : null;
  });

  const chosen = $derived.by(() => {
    if (picked === 'other') return other ? { ...other, sizeId: null } : null;
    return choices.find((c) => c.key === picked) ?? null;
  });

  function done() {
    if (picked === 'other' && !chosen) {
      problem = 'Type how many packs (1 to 99) and the size of one, like 1 kg.';
      return;
    }
    const tick = ticks.find((t) => t.id === tickId) ?? ticks[0];
    if (chosen && tick && picked !== initial) {
      void model.differentPack(item, tick, chosen.count, chosen.pack, chosen.sizeId);
    }
    onclose();
  }

  const title = $derived(item.amount ? 'What did you buy?' : 'How much?');
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<div
  class="sheet"
  role="group"
  aria-labelledby="{uid}-t"
  tabindex="-1"
  onkeydown={(event) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onclose();
    }
  }}
>
  <span class="title" id="{uid}-t">{title}</span>
  {#if ticks.length > 1}
    <span class="title" id="{uid}-w">Which purchase?</span>
    <div class="choices" role="radiogroup" aria-labelledby="{uid}-w" use:radioKeys>
      {#each ticks as t (t.id)}
        <button
          type="button"
          role="radio"
          aria-checked={tickId === t.id}
          onclick={() => (tickId = t.id)}
          >{t.by.name}{t.bought ? ` · ${t.bought.display}` : ''}</button
        >
      {/each}
    </div>
  {/if}
  <div class="choices" role="radiogroup" aria-labelledby="{uid}-t" use:radioKeys>
    {#each choices as choice (choice.key)}
      <button
        type="button"
        role="radio"
        aria-checked={picked === choice.key}
        onclick={() => (picked = choice.key)}
        >{packText(choice.count, choice.pack, food.counted_as)}</button
      >
    {/each}
    <button
      type="button"
      role="radio"
      aria-checked={picked === 'other'}
      onclick={() => (picked = 'other')}>Other…</button
    >
  </div>
  {#if picked === 'other'}
    <div class="other">
      <label>
        How many packs
        <input inputmode="numeric" maxlength="20" bind:value={otherCount} />
      </label>
      <label>
        Size of one
        <input
          inputmode="decimal"
          maxlength="20"
          bind:value={otherAmount}
          placeholder={baseText(250, food.counted_as)}
        />
      </label>
      {#if units.length > 1}
        <label>
          Unit
          <select bind:value={otherUnit}>
            {#each units as unit (unit.name)}<option>{unit.name}</option>{/each}
          </select>
        </label>
      {/if}
    </div>
  {/if}
  {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
  {#if chosen}
    <span class="gets" role="status">{pantryGets(chosen.count, chosen.pack, food.counted_as)}</span>
  {/if}
  <button type="button" class="done" onclick={done}>Done</button>
</div>

<style>
  .sheet {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: var(--space-3) 0 var(--space-3) 34px;
    padding: var(--space-6);
    border-radius: var(--radius-lg);
    background: var(--color-ground);
  }

  .title {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .choices {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .choices button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .choices button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }

  .other {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .other label {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-label);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .other input,
  .other select {
    width: 7rem;
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
  }

  .gets {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .done {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0 18px;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }
</style>
