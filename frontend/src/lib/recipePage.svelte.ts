// The recipe page's data: the recipe, and where its ingredients are in the pantry. Both come
// from the server (online only in 0.4, cabledrawer 19 Oct, question 33). An answer that arrives
// after a newer ask is ignored. The servings chosen with − / + live here and nowhere else: they
// change what the page shows, never the saved recipe (question 26), and are gone when the page
// is left.

import { ApiError } from './api';
import { getRecipe, getRecipeStock, type Recipe, type RecipeStock } from './client/recipes';
import { MAX_SERVES, MIN_SERVES, factorOf } from './recipeAmounts';

export class RecipeView {
  recipe = $state<Recipe | null>(null);
  stock = $state<RecipeStock | null>(null);
  /** False until the first answer, so the page can say "Loading…". */
  loaded = $state(false);
  /** The recipe is not there (deleted, or never was). */
  gone = $state(false);
  problem = $state<string | null>(null);
  /** Servings now; the recipe's own until − / + is used. Null when the recipe has none. */
  servesNow = $state<number | null>(null);

  #asked = 0;

  constructor(readonly id: number) {}

  /** How many times the recipe's own amounts: 1 until the servings change. */
  readonly factor = $derived(
    this.recipe?.serves && this.servesNow ? factorOf(this.servesNow, this.recipe.serves) : 1
  );

  setServes(value: number): void {
    this.servesNow = Math.min(MAX_SERVES, Math.max(MIN_SERVES, Math.round(value)));
  }

  /** Fetch the recipe and its stock. A stock that can't be read leaves the recipe without marks. */
  async load(): Promise<void> {
    const asked = ++this.#asked;
    try {
      const [recipe, stock] = await Promise.all([
        getRecipe(this.id),
        getRecipeStock(this.id).catch((error: unknown) => {
          // The recipe itself missing is the recipe's answer to give; anything else just
          // means no marks this time.
          if (error instanceof ApiError && error.status === 404) throw error;
          return null;
        })
      ]);
      if (asked !== this.#asked) return;
      this.recipe = recipe;
      this.stock = stock;
      this.gone = false;
      this.problem = null;
      // Keep the servings the person chose, as long as the recipe still has servings.
      if (recipe.serves === null) this.servesNow = null;
      else if (this.servesNow === null) this.servesNow = recipe.serves;
    } catch (error) {
      if (asked !== this.#asked) return;
      if (error instanceof ApiError && error.status === 404) {
        this.gone = true;
        this.recipe = null;
        this.stock = null;
      } else {
        this.problem =
          error instanceof ApiError && error.status === 0
            ? error.detail
            : 'Couldn’t load this recipe. Try again.';
      }
    } finally {
      if (asked === this.#asked) this.loaded = true;
    }
  }
}

/** The steps in runs: a heading, then the steps under it, numbered from 1 through the recipe. */
export type StepGroup = { heading: string | null; start: number; steps: string[] };

export function stepGroups(steps: { kind: 'step' | 'heading'; text: string }[]): StepGroup[] {
  const groups: StepGroup[] = [];
  let number = 0;
  for (const step of steps) {
    if (step.kind === 'heading') {
      groups.push({ heading: step.text, start: number + 1, steps: [] });
      continue;
    }
    let group = groups.at(-1);
    if (!group) {
      group = { heading: null, start: number + 1, steps: [] };
      groups.push(group);
    }
    group.steps.push(step.text);
    number++;
  }
  return groups;
}
