// The recipe page's data: the recipe, and where its ingredients are in the pantry. Both come
// from the server (online only in 0.4, cabledrawer 19 Oct, question 33). An answer that arrives
// after a newer ask is ignored. The servings chosen with − / + live here and nowhere else: they
// change what the page shows, never the saved recipe (question 26), and are gone when the page
// is left. The stock marks follow the chosen servings (cabledrawer 19 Oct, Q22): after − / + the
// page asks the server again, once the taps stop.

import { ApiError, cantReachWords, cantReach } from './api';
import { getRecipe, getRecipeStock, type Recipe, type RecipeStock } from './client/recipes';
import { MAX_SERVES, MIN_SERVES, factorOf } from './recipeAmounts';
import type { StepWait } from './timeWords';

/** How long to wait after the last − / + before asking for the stock again. */
export const STOCK_WAIT_MS = 300;

export class RecipeView {
  recipe = $state<Recipe | null>(null);
  stock = $state<RecipeStock | null>(null);
  /** False until the first answer, so the page can say "Loading…". */
  loaded = $state(false);
  /** The recipe is not there (deleted, or never was). */
  gone = $state(false);
  problem = $state<string | null>(null);
  /** What − / + chose; null until it is used (then the page follows the recipe's own Serves). */
  chosen = $state<number | null>(null);

  #asked = 0;
  #stockAsked = 0;
  #timer: ReturnType<typeof setTimeout> | null = null;

  constructor(readonly id: number) {}

  /** Servings now: the chosen number, else the recipe's own. Null when the recipe has none. */
  readonly servesNow = $derived(this.recipe?.serves ? (this.chosen ?? this.recipe.serves) : null);

  /**
   * A recipe with Makes and no Serves: how many times what it makes, from 1 (Makes 200 g →
   * 400 g → 600 g), chosen with the same − / +. Null for any other recipe.
   */
  readonly timesNow = $derived(
    this.recipe && !this.recipe.serves && this.recipe.makes ? (this.chosen ?? 1) : null
  );

  /** How many times the recipe's own amounts: 1 until the servings (or the times) change. */
  readonly factor = $derived(
    this.recipe?.serves && this.servesNow
      ? factorOf(this.servesNow, this.recipe.serves)
      : (this.timesNow ?? 1)
  );

  /**
   * The stock marks to show. The server scales them by servings only, so for a recipe without
   * Serves they are right at 1× alone; at 2× and up the page shows none rather than wrong ones.
   */
  readonly stockNow = $derived(this.timesNow !== null && this.timesNow > 1 ? null : this.stock);

  setServes(value: number): void {
    this.chosen = Math.min(MAX_SERVES, Math.max(MIN_SERVES, Math.round(value)));
    // Without Serves the server can't scale the marks (see stockNow): nothing to ask.
    if (this.timesNow !== null) return;
    // A run of taps makes one request, a little after the last one.
    if (this.#timer !== null) clearTimeout(this.#timer);
    this.#timer = setTimeout(() => {
      this.#timer = null;
      void this.#refreshStock();
    }, STOCK_WAIT_MS);
  }

  /** Leaving the page: nothing more is asked. */
  stop(): void {
    if (this.#timer !== null) clearTimeout(this.#timer);
    this.#timer = null;
    this.#asked++;
    this.#stockAsked++;
  }

  /** Ask for the stock again at the chosen servings. Only the newest answer counts. */
  async #refreshStock(): Promise<void> {
    const asked = ++this.#stockAsked;
    try {
      const stock = await getRecipeStock(this.id, this.chosen);
      if (asked === this.#stockAsked) this.stock = stock;
    } catch (error) {
      if (asked !== this.#stockAsked) return;
      // Marks for the wrong servings would mislead: better none this time.
      this.stock = null;
      if (error instanceof ApiError && error.status === 404) void this.load();
    }
  }

  /** Fetch the recipe and its stock. A stock that can't be read leaves the recipe without marks. */
  async load(): Promise<void> {
    const asked = ++this.#asked;
    const stockAsked = ++this.#stockAsked;
    try {
      const [recipe, stock] = await Promise.all([
        getRecipe(this.id),
        getRecipeStock(this.id, this.chosen).catch((error: unknown) => {
          // The recipe itself missing is the recipe's answer to give; anything else just
          // means no marks this time.
          if (error instanceof ApiError && error.status === 404) throw error;
          return null;
        })
      ]);
      if (asked !== this.#asked) return;
      this.recipe = recipe;
      // A newer stock answer (after − / +) is the one to keep.
      if (stockAsked === this.#stockAsked) this.stock = stock;
      this.gone = false;
      this.problem = null;
    } catch (error) {
      if (asked !== this.#asked) return;
      if (error instanceof ApiError && error.status === 404) {
        this.gone = true;
        this.recipe = null;
        this.stock = null;
      } else {
        this.problem = cantReach(error)
          ? cantReachWords()
          : 'Couldn’t load this recipe. Try again.';
      }
    } finally {
      if (asked === this.#asked) this.loaded = true;
    }
  }
}

/** The steps in runs: a heading, then the steps under it, numbered from 1 through the recipe. */
export type StepGroup = {
  heading: string | null;
  start: number;
  steps: string[];
  /** Which of `steps` are Optional steps, one for one. */
  optional: boolean[];
  /** The wait on each of `steps` (marinate, soak...), one for one; null for none. */
  waits: (StepWait | null)[];
};

export function stepGroups(
  steps: { kind: 'step' | 'heading'; text: string; optional?: boolean; wait?: StepWait | null }[]
): StepGroup[] {
  const groups: StepGroup[] = [];
  let number = 0;
  for (const step of steps) {
    if (step.kind === 'heading') {
      groups.push({ heading: step.text, start: number + 1, steps: [], optional: [], waits: [] });
      continue;
    }
    let group = groups.at(-1);
    if (!group) {
      group = { heading: null, start: number + 1, steps: [], optional: [], waits: [] };
      groups.push(group);
    }
    group.steps.push(step.text);
    group.optional.push(!!step.optional);
    group.waits.push(step.wait ?? null);
    number++;
  }
  return groups;
}
