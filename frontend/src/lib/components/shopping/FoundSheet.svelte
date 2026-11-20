<script lang="ts">
  // "How much Ghee is at home?" (mockup Dark-ShopInShop08-Phone; cabledrawer 6-7 Nov, F117): Already
  // have it takes the line off the list and puts what is at home into the pantry as found at
  // home, not bought. It starts from the list's amount, offers the pack's ½ and ¼, Other…, and
  // where it goes. A sheet from the bottom on a phone, a small dialog on a computer. Works offline:
  // the answer is one `found_at_home` action in the queue.
  import { onMount, tick } from 'svelte';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import { radioKeys } from '#lib/radioKeys.js';
  import { readDraft, unitChoices } from '#lib/shopping/amountBox.js';
  import { localDisplay } from '#lib/shopping/applyLocal.js';
  import { baseText, partText } from '#lib/shopping/format.js';
  import { packParts, usualSize, wholePacks } from '#lib/shopping/packLine.js';
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import type { FoodSize, ListItem, ShopFood } from '#lib/shopping/types.js';

  let {
    model,
    item,
    food,
    onclose
  }: {
    model: ShoppingModel;
    item: ListItem;
    food: ShopFood;
    onclose: () => void;
  } = $props();

  let choicesEl: HTMLElement | undefined;

  let fetched = $state<FoodSize[] | null>(null);
  const sizes = $derived(food.sizes ?? fetched ?? []);
  $effect(() => {
    void model
      .sizesOf(food.id)
      .then((s) => (fetched = s))
      .catch(() => {});
  });
  const withSizes = $derived<ShopFood>({ ...food, sizes });
  const words = (amount: number, sizeId: number | null) =>
    localDisplay(amount, sizeId, withSizes) ?? baseText(amount, food.counted_as);

  /** A half or quarter of the list's amount: a size's own words, else two figures (F183). */
  const partWords = (amount: number, sizeId: number | null) =>
    localDisplay(amount, sizeId, withSizes) ?? partText(amount, food.counted_as);

  interface Choice {
    key: string;
    label: string;
    amount: number;
    sizeId: number | null;
  }

  /** The list's amount first, then the pack's halves and quarters; with no amount, ready-made. */
  const choices = $derived.by(() => {
    const out: Choice[] = [];
    const add = (label: string, exact: number, sizeId: number | null) => {
      // The server takes at most 3 decimal places (RF2 Sh5): a quarter of an amount that is
      // already small is rounded to that, and left out if it rounds to nothing.
      const amount = Math.round(exact * 1000) / 1000;
      if (amount > 0 && !out.some((c) => c.amount === amount && c.sizeId === sizeId)) {
        out.push({ key: `${amount}:${sizeId}`, label, amount, sizeId });
      }
    };
    const need = item.amount;
    const usual = usualSize(withSizes);
    if (need && need > 0) {
      if (usual && !food.staple && usual.amount > 0) {
        const packs = wholePacks(need, usual.amount);
        add(
          packParts(withSizes, need)?.buy ?? words(packs * usual.amount, usual.id),
          packs * usual.amount,
          usual.id
        );
        add(words(usual.amount / 2, usual.id), usual.amount / 2, usual.id);
        add(words(usual.amount / 4, usual.id), usual.amount / 4, usual.id);
      } else {
        add(item.display ?? words(need, item.size_id), need, item.size_id);
        add(partWords(need / 2, item.size_id), need / 2, item.size_id);
        add(partWords(need / 4, item.size_id), need / 4, item.size_id);
      }
    } else if (usual) {
      add(words(usual.amount, usual.id), usual.amount, usual.id);
      add(words(usual.amount / 2, usual.id), usual.amount / 2, usual.id);
      add(words(usual.amount / 4, usual.id), usual.amount / 4, usual.id);
    } else {
      const ready = {
        weight: [100, 250, 500, 1000],
        volume: [250, 500, 1000],
        count: [1, 2, 6, 12]
      };
      for (const amount of ready[food.counted_as])
        add(baseText(amount, food.counted_as), amount, null);
    }
    return out;
  });

  let picked = $state<string | null>(null);
  let typed = $state('');
  let problem = $state<string | null>(null);
  $effect(() => {
    if (picked === null && choices.length) picked = choices[0]!.key;
  });

  const unitList = $derived(unitChoices(food, sizes));
  const editFood = $derived({
    counted_as: food.counted_as,
    sizes,
    count_word: food.count_word ?? null,
    count_word_plural: food.count_word_plural ?? null
  });

  /** What the sheet would put in, or null while "Other…" can't be read. */
  const chosen = $derived.by((): { amount: number; sizeId: number | null } | null => {
    if (picked === 'other') {
      if (!typed.trim()) return null;
      const read = readDraft({ text: typed, unit: unitList[0]!.key }, unitList, editFood);
      return 'problem' in read ? null : read;
    }
    return choices.find((c) => c.key === picked) ?? null;
  });

  // Where: the line's place, the ingredient's usual one, else the Cupboard (the server does the same).
  const placeIds = $derived(model.placeChoices);
  let place = $state<number | null>(null);
  $effect(() => {
    if (place === null) {
      place =
        model.placeOf(item) ??
        model.copy.places.find((p) => p.kind === 'cupboard')?.id ??
        placeIds[0]?.id ??
        null;
    }
  });

  function put() {
    if (picked === 'other' && !chosen) {
      const read = typed.trim()
        ? readDraft({ text: typed, unit: unitList[0]!.key }, unitList, editFood)
        : null;
      problem = read && 'problem' in read ? read.problem : 'Type how much, like 250 g.';
      return;
    }
    if (!chosen) return;
    void model.foundAtHome(item, {
      amount: chosen.amount,
      sizeId: chosen.sizeId,
      placeId: place,
      words: words(chosen.amount, chosen.sizeId)
    });
    onclose();
  }

  onMount(() => {
    void tick().then(() => choicesEl?.querySelector<HTMLElement>('[role="radio"]')?.focus());
  });
</script>

<Sheet title="How much {food.name} is at home?" size="small" {onclose}>
  <div class="body">
    <p class="sub">It comes off the list and goes into the pantry as found at home, not bought.</p>
    <div
      class="choices"
      role="radiogroup"
      aria-label="Amount at home"
      use:radioKeys
      bind:this={choicesEl}
    >
      {#each choices as choice (choice.key)}
        <button
          type="button"
          role="radio"
          aria-checked={picked === choice.key}
          onclick={() => {
            picked = choice.key;
            problem = null;
          }}>{choice.label}</button
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
      <label class="other">
        How much is at home
        <input
          inputmode="decimal"
          maxlength="20"
          bind:value={typed}
          placeholder={baseText(250, food.counted_as)}
          oninput={() => (problem = null)}
        />
      </label>
    {/if}
    {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
    <label class="where">
      <span>Where</span>
      <select bind:value={place} aria-label="Where">
        {#each placeIds as p (p.id)}
          <option value={p.id}>{p.name}</option>
        {/each}
      </select>
    </label>
    <ButtonRow>
      <Button disabled={picked !== 'other' && !chosen} onclick={put}
        >Put {chosen ? words(chosen.amount, chosen.sizeId) : 'it'} in the pantry</Button
      >
      <Button quiet onclick={onclose}>Cancel</Button>
    </ButtonRow>
  </div>
</Sheet>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .choices {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .choices button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .choices button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }

  .other,
  .where {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .other input,
  .where select {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-base) var(--font-ui);
  }

  .other input {
    flex: 1;
    min-width: 0;
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
  }
</style>
