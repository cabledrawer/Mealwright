<script lang="ts" module>
  import type { Ref } from '#lib/client/types.js';

  export type Pick =
    { kind: 'ingredient'; food: Ref; otherNames?: string[] } | { kind: 'recipe'; recipe: Ref };
</script>

<script lang="ts">
  // The pick-list under a line's ingredient box (mockup RecipeLines): a listbox of what the
  // typed words find, shown while the person types. Ingredients first, each with "also called …"
  // and "in N recipes" (by any of their other names too: "thuvaram" finds Toor dal), then recipes,
  // and last "+ New ingredient “dru”", which opens the same "Pantry keeps it by" as Shopping.
  // A recipe and an ingredient with the very same name sit together, the recipe first, each
  // labelled Recipe or Ingredient (F189, cabledrawer 8 Nov).
  // A recipe that would make a loop is greyed out with the reason.
  //
  // The box is a combobox and keeps the focus; its owner (LineList) hands the arrow keys and Enter
  // to `key()`, and reads `activeId` for aria-activedescendant. Nothing is linked until an option
  // is picked: typing alone never changes the person's words.
  import '#lib/styles/fields.css';
  import Icon from '../Icon.svelte';
  import type { Blocked, RecipeBrief } from '#lib/client/recipes.js';
  import type { FoodRow } from '#lib/client/types.js';
  import { arrange } from '#lib/recipes/search.js';

  let {
    id,
    query,
    search,
    blocked = [],
    activeId = $bindable(),
    onpick,
    oncreate
  }: {
    /** The listbox's id, for the box's aria-controls. */
    id: string;
    /** What is typed on the line. */
    query: string;
    search: (q: string) => Promise<{ foods: FoodRow[]; recipes: RecipeBrief[] }>;
    /** Recipes that can't be used here, and why (the loop guard). */
    blocked?: Blocked[];
    /** The option the arrow keys are on (aria-activedescendant); undefined when none. */
    activeId?: string | undefined;
    onpick: (pick: Pick) => void;
    oncreate: (name: string) => void;
  } = $props();

  type Option =
    | { key: string; kind: 'ingredient'; food: FoodRow; paired: boolean }
    | { key: string; kind: 'recipe'; recipe: RecipeBrief; why: string | undefined; paired: boolean }
    | { key: string; kind: 'new' };

  let foods = $state<FoodRow[]>([]);
  let recipes = $state<RecipeBrief[]>([]);
  /** The text the results on show are for. */
  let answered = $state('');
  let failed = $state(false);
  let asked = 0;
  /** Which option the arrow keys are on; -1 is none. */
  let at = $state(-1);

  const typed = $derived(query.trim());
  const reasons = $derived(new Map(blocked.map((b) => [b.id, b.reason])));
  const exact = $derived(
    foods.some((f) => f.name.toLocaleLowerCase() === typed.toLocaleLowerCase())
  );
  const current = $derived(answered === typed);

  const options = $derived.by((): Option[] => {
    const out: Option[] = arrange(foods, recipes).map((row) =>
      row.kind === 'ingredient'
        ? { key: `f${row.food.id}`, kind: 'ingredient', food: row.food, paired: row.paired }
        : {
            key: `r${row.recipe.id}`,
            kind: 'recipe',
            recipe: row.recipe,
            why: reasons.get(row.recipe.id),
            paired: row.paired
          }
    );
    if (typed && current && !exact) out.push({ key: 'new', kind: 'new' });
    return out;
  });
  /** The "Recipes" heading goes before the first recipe that isn't beside its same-named ingredient. */
  const firstRecipe = $derived(options.findIndex((o) => o.kind === 'recipe' && !o.paired));
  const newAt = $derived(options.findIndex((o) => o.kind === 'new'));

  const optionId = (key: string) => `${id}-${key}`;
  $effect(() => {
    const on = options[at];
    activeId = on ? optionId(on.key) : undefined;
  });

  $effect(() => {
    const q = typed;
    const mine = ++asked;
    at = -1;
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
          at = -1;
        })
        .catch(() => {
          if (mine === asked) failed = true;
        });
    }, 150);
    return () => clearTimeout(timer);
  });

  const makes = (r: RecipeBrief) =>
    r.makes ? `recipe · makes ${r.makes.amount_text}\u00a0${r.makes.unit}` : 'recipe';

  /** "also called murungakkai · in 2 recipes". */
  function foodSub(food: FoodRow): string {
    const parts: string[] = [];
    const other =
      food.matched_name && food.matched_name !== food.name
        ? food.matched_name
        : food.other_names[0];
    if (other) parts.push(`also called ${other}`);
    const n = food.used_in_recipes;
    if (n !== undefined)
      parts.push(n === 0 ? 'in no recipes' : `in ${n} ${n === 1 ? 'recipe' : 'recipes'}`);
    return parts.join(' · ');
  }

  function choose(option: Option) {
    if (option.kind === 'ingredient') {
      const { food } = option;
      onpick({
        kind: 'ingredient',
        food: { id: food.id, name: food.name },
        otherNames: food.other_names
      });
    } else if (option.kind === 'recipe') {
      if (option.why) return;
      onpick({ kind: 'recipe', recipe: { id: option.recipe.id, name: option.recipe.name } });
    } else oncreate(typed);
  }

  /**
   * The box's key presses: ↓ and ↑ move through the options, Enter picks the one they are on.
   * Returns true when the key was used (so the box doesn't also act on it).
   */
  export function key(event: KeyboardEvent): boolean {
    if (!options.length) return false;
    if (event.key === 'ArrowDown') {
      at = at + 1 >= options.length ? 0 : at + 1;
    } else if (event.key === 'ArrowUp') {
      at = at <= 0 ? options.length - 1 : at - 1;
    } else if (event.key === 'Enter') {
      const on = options[at];
      if (!on) return false;
      choose(on);
    } else return false;
    document.getElementById(activeId ?? '')?.scrollIntoView({ block: 'nearest' });
    return true;
  }

  const count = $derived(foods.length + recipes.length);
</script>

<div class="picker">
  {#if failed}
    <p class="mw-error" role="alert">Couldn’t search. Try again.</p>
  {/if}

  <!-- Mouse and touch picks; keyboards use the box's arrow keys, so options aren't tab stops. -->
  <div class="list" role="listbox" {id} aria-label="Matching ingredients">
    {#each options as option, i (option.key)}
      {#if i === firstRecipe}
        <p class="group" aria-hidden="true">Recipes</p>
      {/if}
      {#if i === newAt && i > 0}
        <span class="rule" aria-hidden="true"></span>
      {/if}
      {#if option.kind === 'ingredient'}
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_interactive_supports_focus -->
        <div
          class="item"
          role="option"
          id={optionId(option.key)}
          aria-selected={at === i}
          onmousedown={(e) => e.preventDefault()}
          onclick={() => choose(option)}
        >
          <span class="name"
            >{option.food.name}{#if option.paired}<span class="kind">Ingredient</span>{/if}</span
          >
          {#if foodSub(option.food)}<span class="sub">{foodSub(option.food)}</span>{/if}
        </div>
      {:else if option.kind === 'recipe'}
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_interactive_supports_focus -->
        <div
          class="item recipe"
          class:blocked={!!option.why}
          role="option"
          id={optionId(option.key)}
          aria-selected={at === i}
          aria-disabled={option.why ? 'true' : undefined}
          onmousedown={(e) => e.preventDefault()}
          onclick={() => choose(option)}
        >
          <span class="name"
            ><Icon name="recipes" size={16} />{option.recipe.name}{#if option.paired}<span
                class="kind recipe-kind">Recipe</span
              >{/if}</span
          >
          <span class="sub" class:why={!!option.why}>{option.why ?? makes(option.recipe)}</span>
        </div>
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_interactive_supports_focus -->
        <div
          class="item new"
          role="option"
          id={optionId(option.key)}
          aria-selected={at === i}
          onmousedown={(e) => e.preventDefault()}
          onclick={() => choose(option)}
        >
          + New ingredient “{typed}”
        </div>
      {/if}
    {/each}
  </div>

  <p class="visually-hidden" role="status">
    {#if current && typed}{count === 0
        ? 'No matches'
        : count === 1
          ? '1 match'
          : `${count} matches`}{/if}
  </p>
</div>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .list {
    display: flex;
    flex-direction: column;
  }

  .group {
    padding: var(--space-4) var(--space-4) var(--space-1);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .rule {
    height: 1px;
    margin: var(--space-2) var(--space-3);
    background: var(--color-divider);
  }

  .item {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: var(--space-1);
    min-height: var(--touch-target);
    padding: var(--space-3) var(--space-5);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
  }

  .item:hover {
    background: var(--color-fill);
  }

  .item[aria-selected='true'] {
    background: var(--color-accent-soft);
    outline: 2px solid var(--color-focus);
    outline-offset: -2px;
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

  /* "Recipe" and "Ingredient" beside two rows with the same name (F189). */
  .kind {
    padding: 2px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    white-space: nowrap;
  }

  .recipe-kind {
    background: var(--color-accent-soft);
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
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }
</style>
