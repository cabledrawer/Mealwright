<script lang="ts">
  // Pick another food by typing any of its names: "Can use instead", "Merge with…".
  // Suggestions come from the server's search; Escape or leaving it empty closes it.
  import { listFoods } from '#lib/client/foods.js';
  import type { FoodRow, Ref } from '#lib/client/types.js';
  import Button from '#lib/components/Button.svelte';

  let {
    label,
    exclude = [],
    onpick,
    oncancel,
    oncreate,
    placeholder = 'Type a name'
  }: {
    /** What the box is for, read out by screen readers: "Can use instead of toor dal". */
    label: string;
    exclude?: number[];
    onpick: (food: Ref) => void;
    oncancel?: () => void;
    /** Offer "New ingredient: …" when nothing has exactly that name. */
    oncreate?: (name: string) => void;
    placeholder?: string;
  } = $props();

  const uid = $props.id();
  let query = $state('');
  let found = $state<FoodRow[]>([]);
  let asked = 0;

  const shown = $derived(found.filter((f) => !exclude.includes(f.id)).slice(0, 6));
  const typed = $derived(query.trim());
  const exact = $derived(
    found.some((f) => f.name.toLocaleLowerCase() === typed.toLocaleLowerCase())
  );

  $effect(() => {
    const q = query.trim();
    const mine = ++asked;
    if (!q) {
      found = [];
      return;
    }
    const timer = setTimeout(() => {
      listFoods({ q, limit: 8 })
        .then((list) => {
          if (mine === asked) found = list.foods;
        })
        .catch(() => {
          if (mine === asked) found = [];
        });
    }, 150);
    return () => clearTimeout(timer);
  });

  function focusOnShow(node: HTMLElement) {
    node.focus();
  }
</script>

<div class="picker">
  <input
    type="search"
    aria-label={label}
    aria-controls="{uid}-list"
    {placeholder}
    autocomplete="off"
    bind:value={query}
    use:focusOnShow
    onkeydown={(event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        event.stopPropagation();
        oncancel?.();
      }
      if (event.key === 'Enter' && shown[0]) onpick(shown[0]);
    }}
  />
  <ul id="{uid}-list" aria-label="Matching ingredients">
    {#each shown as food (food.id)}
      <li>
        <button type="button" onclick={() => onpick({ id: food.id, name: food.name })}>
          {food.name}
          {#if food.matched_name && food.matched_name !== food.name}
            <span class="also">also “{food.matched_name}”</span>
          {/if}
        </button>
      </li>
    {/each}
    {#if oncreate && typed && !exact}
      <li>
        <button type="button" class="new" onclick={() => oncreate?.(typed)}>
          + New ingredient: “{typed}”
        </button>
      </li>
    {/if}
  </ul>
  {#if oncancel}
    <Button small quiet onclick={oncancel}>Cancel</Button>
  {/if}
</div>

<style>
  .picker {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: var(--space-3);
    width: 100%;
  }

  input {
    flex: 1 1 12rem;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  ul {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    width: 100%;
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
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  ul .new {
    border: 1px dashed var(--color-add-border);
    background: transparent;
    color: var(--color-accent);
  }

  .also {
    color: var(--color-text-muted);
    font-weight: var(--weight-medium);
  }
</style>
