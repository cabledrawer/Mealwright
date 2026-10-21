<script lang="ts">
  // "Add an item…" (mockup Shop): type a name; matching ingredients are offered, and a name
  // nobody has used offers + New ingredient: "tahini", which asks How do you count it?.
  import Icon from '$lib/components/Icon.svelte';
  import type { FoodRow } from '$lib/client/types';
  import { newIngredient } from '$lib/newIngredient.svelte';
  import type { ShoppingModel } from '$lib/shopping/store.svelte';
  import { toasts } from '$lib/toast.svelte';

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

  const typed = $derived(text.trim());
  const exact = $derived(
    found.some((f) => f.name.toLocaleLowerCase() === typed.toLocaleLowerCase())
  );

  $effect(() => {
    const q = typed;
    const mine = ++asked;
    if (!q) {
      found = [];
      return;
    }
    const timer = setTimeout(() => {
      model
        .search(q)
        .then((rows) => {
          if (mine !== asked) return;
          found = rows;
          answeredFor = q;
        })
        .catch(() => {
          if (mine !== asked) return;
          found = [];
          answeredFor = '';
        });
    }, 150);
    return () => clearTimeout(timer);
  });

  function reset() {
    text = '';
    found = [];
    answeredFor = '';
  }

  function pick(food: FoodRow) {
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
    const name = typed;
    reset();
    const chosen = await newIngredient.choose(name);
    if (chosen) void model.addNew(chosen);
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!typed || answeredFor !== typed) return; // the matches are still on their way
    const first =
      found.find((f) => f.name.toLocaleLowerCase() === typed.toLocaleLowerCase()) ?? found[0];
    if (first) pick(first);
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
        <button type="button" onclick={() => pick(food)}>
          {food.name}
          {#if food.matched_name && food.matched_name !== food.name}
            <span class="also">also “{food.matched_name}”</span>
          {/if}
        </button>
      </li>
    {/each}
    {#if typed && !exact && answeredFor === typed}
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
