<script lang="ts">
  // "Add an item…" (mockup Shop): type a name; matching ingredients are offered, and a name
  // nobody has used offers + New ingredient: "tahini", which asks Pantry keeps it by.
  import Icon from '#lib/components/Icon.svelte';
  import type { FoodRow } from '#lib/client/types.js';
  import type { FoodSize } from '#lib/shopping/types.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import {
    countedAsFor,
    readForNew,
    MAX_ADD_TEXT,
    readAs,
    splitAmount,
    ZERO_AMOUNT
  } from '#lib/shopping/addAmount.js';
  import { toBaseAmount } from '#lib/shopping/amountEdit.js';
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';

  let {
    model,
    desktop = false,
    onexisting
  }: {
    model: ShoppingModel;
    /** Desktop: the button says "Add", as in the mockup; the phone has a round "+". */
    desktop?: boolean;
    /** The ingredient is already a line on the list: edit that line (cabledrawer 18 Oct). */
    onexisting: (itemId: string) => void;
  } = $props();

  const uid = $props.id();
  let text = $state('');
  let found = $state<FoodRow[]>([]);
  let asked = 0;
  /** The text the matches on show are for: "+ New ingredient" waits until they are. */
  let answeredFor = $state('');

  // "1 l milk" is the name "milk" with the amount "1 l" in front (F63). Unless an ingredient is
  // named exactly as the whole text ("5 spice", "00 flour"): then that name, with no amount.
  const whole = $derived(text.trim());
  const raw = $derived(splitAmount(text));
  /** The text whose whole is an ingredient's name, found by the last look-up. */
  let namedWhole = $state('');
  const split = $derived(raw && namedWhole !== whole ? raw : null);
  const typed = $derived(split ? split.name : whole);
  const exact = $derived(
    found.some((f) => f.name.toLocaleLowerCase() === typed.toLocaleLowerCase())
  );
  /** What each match would add, as it will be read ("Garlic · 2 g"), once its sizes are known. */
  let sizesOf = $state<Record<number, FoodSize[]>>({});

  $effect(() => {
    const q = whole;
    const r = raw;
    const mine = ++asked;
    if (!q) {
      found = [];
      namedWhole = '';
      return;
    }
    const timer = setTimeout(async () => {
      try {
        let rows = await model.search(q);
        let named = '';
        if (r) {
          const lower = q.toLocaleLowerCase();
          if (rows.some((f) => f.name.toLocaleLowerCase() === lower)) named = q;
          else rows = await model.search(r.name);
        }
        if (mine !== asked) return;
        found = rows;
        namedWhole = named;
        answeredFor = q;
        if (r && !named) {
          for (const food of rows) {
            if (food.id > 0 && !sizesOf[food.id]) {
              void model
                .sizesOf(food.id)
                .then((z) => (sizesOf = { ...sizesOf, [food.id]: z }))
                .catch(() => {});
            }
          }
        }
      } catch {
        if (mine !== asked) return;
        found = [];
        answeredFor = '';
      }
    }, 150);
    return () => clearTimeout(timer);
  });

  /** The amount as the box will read it for this ingredient. */
  const readAsFor = (food: FoodRow): string | null =>
    split && !split.zero
      ? readAs(split.amountText, {
          counted_as: food.counted_as,
          sizes: (sizesOf[food.id] ?? []) as never,
          count_word: null,
          count_word_plural: null
        })
      : null;

  function reset() {
    text = '';
    found = [];
    answeredFor = '';
  }

  /** The typed amount for this ingredient, or why it can't be read (said in a toast). */
  async function amountFor(
    food: Pick<FoodRow, 'id' | 'counted_as'>,
    amountText: string
  ): Promise<{ amount: number; sizeId: number | null } | null> {
    // Its sizes may need the server; offline, g / kg / ml / L and bare numbers still read.
    const sizes = food.id > 0 ? await model.sizesOf(food.id).catch(() => []) : [];
    const read = toBaseAmount(amountText, {
      counted_as: food.counted_as,
      sizes,
      count_word: null,
      count_word_plural: null
    });
    if ('problem' in read) {
      toasts.show(read.problem, { tone: 'problem' });
      return null;
    }
    return read;
  }

  /** An add is under way (waiting for sizes or for "Pantry keeps it by"): a second tap or
   * Enter is ignored, so the same thing isn't added twice. */
  let busy = false;

  async function pick(food: FoodRow) {
    if (busy) return;
    busy = true;
    try {
      await pickNow(food);
    } finally {
      busy = false;
    }
  }

  /** "0 g butter": nothing is added, and the text stays so the amount can be fixed. */
  function zeroTyped(): boolean {
    if (!split?.zero) return false;
    toasts.show(ZERO_AMOUNT, { tone: 'problem' });
    return true;
  }

  async function pickNow(food: FoodRow) {
    if (zeroTyped()) return;
    const typedAmount = split?.amountText;
    if (typedAmount) {
      // An amount was typed: the add carries it and joins a line already there (0.5's rule).
      // Read first: if it can't be read the text stays, so it can be fixed.
      const amount = await amountFor(food, typedAmount);
      if (!amount) return;
      reset();
      void model.add(food, `${food.name} added`, undefined, amount);
      return;
    }
    reset();
    const line = model.lineFor(food.id);
    if (line) {
      const amount = line.display ? ` · ${line.display}` : '';
      toasts.show(`${food.name} is already on the list${amount}`);
      onexisting(line.id);
      return;
    }
    void model.add(food);
  }

  async function create() {
    if (busy) return;
    busy = true;
    try {
      await createNow();
    } finally {
      busy = false;
    }
  }

  async function createNow() {
    if (zeroTyped()) return; // never a new item called "0 g butter"
    const name = typed;
    const typedAmount = split?.amountText;
    const chosen = await newIngredient.choose(name, typedAmount ? countedAsFor(typedAmount) : null);
    if (!chosen) return;
    // The amount is read for the way it was just counted, and for the sizes just made in the
    // dialog ("2 packets milk" with packet = 1 L). A size isn't saved yet, so it has no id; the
    // amount goes in as the plain total. Unreadable: the item is still added, with no amount.
    let amount: { amount: number; sizeId: number | null } | null = null;
    if (typedAmount) {
      const read = readForNew(typedAmount, chosen);
      if ('problem' in read) toasts.show(read.problem, { tone: 'problem' });
      else amount = { amount: read.amount, sizeId: null };
    }
    reset();
    void model.addNew(chosen, amount ?? undefined);
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!typed || answeredFor !== whole) return; // the matches are still on their way
    const first =
      found.find((f) => f.name.toLocaleLowerCase() === typed.toLocaleLowerCase()) ?? found[0];
    if (first) void pick(first);
    else if (typed) void create();
  }
</script>

<div class="box">
  <form onsubmit={submit}>
    <label for="{uid}-in" class="visually-hidden">Add an item</label>
    <input
      id="{uid}-in"
      type="text"
      placeholder="Add an item…"
      autocomplete="off"
      aria-controls="{uid}-list"
      maxlength={MAX_ADD_TEXT}
      bind:value={text}
    />
    {#if desktop}
      <button type="submit" class="plus wide" disabled={!typed}>Add</button>
    {:else}
      <button type="submit" class="plus" aria-label="Add item" disabled={!typed}
        ><Icon name="plus" size={20} stroke={2.6} /></button
      >
    {/if}
  </form>
  <ul id="{uid}-list" aria-label="Matching ingredients">
    {#each found as food (food.id)}
      <li>
        <button type="button" onclick={() => void pick(food)}>
          {food.name}{#if readAsFor(food)}<span class="also">&nbsp;· {readAsFor(food)}</span>{/if}
          {#if food.matched_name && food.matched_name !== food.name}
            <span class="also">also “{food.matched_name}”</span>
          {/if}
        </button>
      </li>
    {/each}
    {#if typed && !exact && answeredFor === whole}
      <li>
        <button type="button" class="new" onclick={() => void create()}>
          + New ingredient: “{typed}”
        </button>
      </li>
    {/if}
  </ul>
</div>

<style>
  .box {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  form {
    display: flex;
    gap: var(--space-4);
  }

  .visually-hidden {
    position: absolute;
    left: -9999px;
  }

  input {
    flex: 1;
    min-width: 0;
    min-height: 48px;
    padding: 0 14px;
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-lg);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .plus {
    display: grid;
    place-items: center;
    padding: 0;
    width: 48px;
    height: 48px;
    border: none;
    border-radius: var(--radius-lg);
    background: #2e7d5b; /* white on this green passes AA in both themes, as in the mockups */
    color: #ffffff;
    cursor: pointer;
  }

  .plus.wide {
    width: auto;
    padding: 0 20px;
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
  }

  .plus:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  ul {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  ul:empty {
    display: none;
  }

  ul button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .also {
    color: var(--color-text-muted);
    font-weight: var(--weight-regular);
  }

  .new {
    color: var(--color-accent);
  }
</style>
