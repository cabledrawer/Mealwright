<script lang="ts">
  // The amount box on a shopping row (mockups ShopRows-editing; cabledrawer 20 Oct). It opens where
  // the row was: the ingredient's name and Done, − / + beside a box that holds the real amount,
  // a unit choice, and "Remove from list" (which asks first). Done, or Enter, saves it as one
  // change with its Undo; Escape leaves it as it was. Nothing is sent while you type.
  // "Edit ingredient" (spec, Shopping rows) saves the box as Done does, then opens the
  // ingredient editor. Hidden offline, like the recipe page's Edit (the editor needs the
  // server), and for an ingredient still being made (no server ID yet).
  import { untrack } from 'svelte';
  import { ingredientEditor } from '$lib/ingredientEditor.svelte';
  import { network } from '$lib/network.svelte';
  import {
    readDraft,
    startDraft,
    stepDraft,
    switchUnit,
    unitChoices,
    type Draft
  } from '$lib/shopping/amountBox';
  import type { ShoppingModel } from '$lib/shopping/store.svelte';
  import type { FoodSize } from '$lib/shopping/types';
  import type { ViewItem } from '$lib/shopping/view';
  import Icon from '../Icon.svelte';

  let {
    model,
    view,
    onclose,
    onremove
  }: {
    model: ShoppingModel;
    view: ViewItem;
    /** Leave the box (after saving, or Escape). */
    onclose: () => void;
    /** "Remove from list": the row asks "are you sure?". */
    onremove: () => void;
  } = $props();

  const uid = $props.id();
  const item = $derived(view.item);
  const food = $derived(view.food);

  // The ingredient's own sizes ("packet = 500 g") may need fetching; the box is usable
  // with g / kg (or ml / L) while they come.
  let fetched = $state<FoodSize[] | null>(null);
  const sizes = $derived(food.sizes ?? fetched ?? []);
  $effect(() => {
    const id = food.id;
    untrack(() => {
      void model
        .sizesOf(id)
        .then((s) => (fetched = s))
        .catch(() => {});
    });
  });

  const choices = $derived(unitChoices(food, sizes));
  const editFood = $derived({
    counted_as: food.counted_as,
    sizes,
    count_word: food.count_word ?? null,
    count_word_plural: food.count_word_plural ?? null
  });

  let draft = $state<Draft>(
    untrack(() => startDraft(item, food, unitChoices(food, food.sizes ?? [])))
  );
  let problem = $state<string | null>(null);
  let input = $state<HTMLInputElement>();

  // The sizes arrived after the box opened, for a line written in one of them.
  let settled = untrack(() => !!food.sizes);
  $effect(() => {
    if (settled || !sizes.length) return;
    settled = true;
    if (item.size_id !== null) draft = startDraft(item, food, choices);
    else if (!draft.text.trim()) draft = startDraft(item, food, choices);
  });

  const showUnits = $derived(choices.length > 1);

  /** Save what the box holds, if it changed. False when it can't be read (and says why). */
  function save(): boolean {
    const typed = draft.text.trim();
    if (!typed) {
      // An empty box on a line with no amount is "leave it"; on a line with one it's a mistake.
      if (!item.amount) return true;
      problem = 'Type an amount, like 500 g or 2 packets.';
      return false;
    }
    const read = readDraft(draft, choices, editFood);
    if ('problem' in read) {
      problem = read.problem;
      return false;
    }
    problem = null;
    if (read.amount !== item.amount || read.sizeId !== item.size_id) {
      void model.setAmount(item, read.amount, read.sizeId);
    }
    return true;
  }

  function done() {
    if (save()) onclose();
    else input?.focus();
  }

  function editIngredient() {
    if (!save()) return void input?.focus();
    onclose();
    ingredientEditor.open(food.id);
  }

  function step(direction: 1 | -1) {
    problem = null;
    draft = stepDraft(draft, direction, choices, editFood);
  }

  function chooseUnit(key: string) {
    problem = null;
    draft = switchUnit(draft, key, choices, editFood);
  }

  function focusOnShow(node: HTMLInputElement) {
    node.focus();
    node.select();
  }
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
<form
  class="box"
  aria-label="Change {food.name}"
  onsubmit={(event) => {
    event.preventDefault();
    done();
  }}
  onkeydown={(event) => {
    if (event.key === 'Escape') {
      event.stopPropagation();
      onclose();
    }
  }}
>
  <div class="head">
    <span class="name">{food.name}</span>
    <button type="submit" class="done">Done</button>
  </div>
  <div class="row">
    <button type="button" class="step" aria-label="Less" onclick={() => step(-1)}>−</button>
    <input
      bind:this={input}
      bind:value={draft.text}
      inputmode="decimal"
      aria-label="Amount"
      aria-describedby="{uid}-hint{problem ? ` ${uid}-p` : ''}"
      aria-invalid={problem ? 'true' : undefined}
      placeholder={item.amount ? undefined : 'e.g. 500'}
      oninput={() => (problem = null)}
      use:focusOnShow
    />
    <button type="button" class="step" aria-label="More" onclick={() => step(1)}>+</button>
    {#if showUnits}
      <select
        aria-label="Unit"
        value={draft.unit}
        onchange={(event) => chooseUnit(event.currentTarget.value)}
      >
        {#each choices as choice (choice.key)}
          <option value={choice.key}>{choice.label}</option>
        {/each}
      </select>
    {/if}
  </div>
  <span class="hint" id="{uid}-hint">The box holds the real amount: edit it, or use − / +.</span>
  {#if problem}<p id="{uid}-p" class="problem" role="alert">{problem}</p>{/if}
  <div class="foot">
    <button type="button" class="remove" onclick={onremove}>
      <Icon name="trash" size={20} stroke={2.2} />Remove from list
    </button>
    {#if !network.offline && food.id > 0}
      <button type="button" class="edit" onclick={editIngredient}>Edit ingredient</button>
    {/if}
  </div>
</form>

<style>
  .box {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    margin: var(--space-3) calc(-1 * var(--space-3));
    padding: var(--space-6);
    border: 2px solid var(--color-accent);
    border-radius: var(--radius-field);
    background: var(--color-surface);
  }

  .head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
  }

  .name {
    min-width: 0;
    font-size: 1rem;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .done {
    flex: none;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-fill);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .step {
    flex: none;
    width: 48px;
    height: 48px;
    padding: 0;
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text);
    font: var(--weight-bold) 1.375rem var(--font-ui);
    cursor: pointer;
  }

  input {
    flex: 1;
    min-width: 0;
    min-height: 48px;
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    text-align: center;
    font: var(--weight-bold) 1.125rem var(--font-ui);
  }

  input[aria-invalid='true'] {
    border-color: var(--color-warning-text);
  }

  select {
    flex: none;
    max-width: 9rem;
    min-height: 48px;
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .foot {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2) var(--space-6);
  }

  .edit {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
    cursor: pointer;
  }

  .remove {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-warning-text);
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }
</style>
