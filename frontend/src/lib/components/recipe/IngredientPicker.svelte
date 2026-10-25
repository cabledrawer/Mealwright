<script lang="ts" module>
  import type { Ref } from '#lib/client/types.js';

  export type Pick =
    { kind: 'ingredient'; food: Ref; otherNames?: string[] } | { kind: 'recipe'; recipe: Ref };
</script>

<script lang="ts">
  // "Pick an ingredient" (mockups RecipeEditor-*, EditorState-picker): what is typed on the line
  // finds ingredients (by any of their other names too: "thuvaram" finds Toor dal) and recipes,
  // and a name nobody has used offers "+ New ingredient", which opens the same "How do you
  // count it?" as Shopping. A recipe that would make a loop is greyed out with the reason.
  // Where the results go (a sheet on a phone, under the line on a computer) is the caller's.
  import '#lib/styles/fields.css';
  import Icon from '../Icon.svelte';
  import type { Blocked, RecipeBrief } from '#lib/client/recipes.js';
  import type { FoodRow } from '#lib/client/types.js';

  let {
    query,
    search,
    blocked = [],
    onpick,
    oncreate,
    onback
  }: {
    /** What is typed on the line. */
    query: string;
    search: (q: string) => Promise<{ foods: FoodRow[]; recipes: RecipeBrief[] }>;
    /** Recipes that can't be used here, and why (the loop guard). */
    blocked?: Blocked[];
    onpick: (pick: Pick) => void;
    oncreate: (name: string) => void;
    /** ArrowUp from the first result: back to the box being typed in. */
    onback?: () => void;
  } = $props();

  const uid = $props.id();
  let foods = $state<FoodRow[]>([]);
  let recipes = $state<RecipeBrief[]>([]);
  /** The text the results on show are for. */
  let answered = $state('');
  let failed = $state(false);
  let asked = 0;
  let list: HTMLElement;

  const typed = $derived(query.trim());
  const reasons = $derived(new Map(blocked.map((b) => [b.id, b.reason])));
  const exact = $derived(
    foods.some((f) => f.name.toLocaleLowerCase() === typed.toLocaleLowerCase())
  );
  const current = $derived(answered === typed);

  $effect(() => {
    const q = typed;
    const mine = ++asked;
    if (!q) {
      foods = [];
      recipes = [];
      answered = '';
      failed = false;
      return;
    }
    const timer = setTimeout(() => {
      search(q)
        .then((found) => {
          if (mine !== asked) return;
          foods = found.foods.slice(0, 6);
          recipes = found.recipes;
          answered = q;
          failed = false;
        })
        .catch(() => {
          if (mine === asked) failed = true;
        });
    }, 150);
    return () => clearTimeout(timer);
  });

  const makes = (r: RecipeBrief) =>
    r.makes ? `recipe · makes ${r.makes.amount_text}\u00a0${r.makes.unit}` : 'recipe';

  function keydown(event: KeyboardEvent) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    const items = [...list.querySelectorAll<HTMLElement>('.item')];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const to = at + (event.key === 'ArrowDown' ? 1 : -1);
    event.preventDefault();
    if (to < 0) onback?.();
    else items[Math.min(to, items.length - 1)]?.focus();
  }
</script>

<!-- Arrow keys move between the results. -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="picker" bind:this={list} onkeydown={keydown}>
  <p class="mw-hint">Your words stay on the line. Other names count: “thuvaram” finds Toor dal.</p>

  {#if !typed}
    <p class="mw-hint">Type an ingredient or a recipe.</p>
  {/if}

  {#if failed}
    <p class="mw-error" role="alert">Couldn’t search. Try again.</p>
  {/if}

  {#if foods.length}
    <p class="group" id="{uid}-foods">Ingredients</p>
    <ul aria-labelledby="{uid}-foods">
      {#each foods as food (food.id)}
        <li>
          <button
            type="button"
            class="item"
            onclick={() =>
              onpick({
                kind: 'ingredient',
                food: { id: food.id, name: food.name },
                otherNames: food.other_names
              })}
          >
            <span class="name">{food.name}</span>
            {#if food.matched_name && food.matched_name !== food.name}
              <span class="sub">also called: {food.matched_name}</span>
            {/if}
          </button>
        </li>
      {/each}
    </ul>
  {/if}

  {#if recipes.length}
    <p class="group" id="{uid}-recipes">Recipes</p>
    <ul aria-labelledby="{uid}-recipes">
      {#each recipes as recipe (recipe.id)}
        {@const why = reasons.get(recipe.id)}
        <li>
          {#if why}
            <button
              type="button"
              class="item blocked"
              aria-disabled="true"
              aria-describedby="{uid}-why-{recipe.id}"
            >
              <span class="name"><Icon name="recipes" size={16} />{recipe.name}</span>
              <span class="sub why" id="{uid}-why-{recipe.id}">{why}</span>
            </button>
          {:else}
            <button
              type="button"
              class="item recipe"
              onclick={() =>
                onpick({ kind: 'recipe', recipe: { id: recipe.id, name: recipe.name } })}
            >
              <span class="name"><Icon name="recipes" size={16} />{recipe.name}</span>
              <span class="sub">{makes(recipe)}</span>
            </button>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  {#if typed && current && !exact}
    <button type="button" class="item new" onclick={() => oncreate(typed)}
      >+ New ingredient “{typed}”</button
    >
    <p class="mw-hint">
      A new ingredient opens “How do you count it?”, with packet sizes, as on Shopping.
    </p>
  {/if}
</div>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .group {
    padding: var(--space-4) var(--space-2) 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  ul {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .item {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-5) var(--space-4);
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
  }

  .item:hover {
    background: var(--color-fill);
  }

  .recipe {
    background: var(--color-accent-soft);
    color: var(--color-text);
  }

  .recipe:hover {
    background: var(--color-accent-soft);
    filter: brightness(0.97);
  }

  .name {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .recipe .name {
    color: var(--color-accent-on-soft);
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .blocked {
    color: var(--color-text-muted);
    cursor: not-allowed;
  }

  .blocked:hover {
    background: transparent;
  }

  .why {
    font-weight: var(--weight-semibold);
  }

  .new {
    flex-direction: row;
    align-items: center;
    margin-top: var(--space-3);
    border-top: 1px solid var(--color-divider);
    border-radius: 0;
    color: var(--color-accent);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }
</style>
