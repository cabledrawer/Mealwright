// "Which optional ingredients will you use?" (R3, cabledrawer 6 and 9 Nov; mockup PlanOptional08): a
// recipe with Optional ingredient lines asks before it is added to the plan, and again from its
// meal when the person wants to change the answer. PlanOptional.svelte shows the question; the
// ticked ones go on the shopping list if they are needed and come out of the pantry at Cooked
// it, the others don't. Online only, like the rest of the Plan.

import type { OptionalRow } from './optionalQuestion';
// What reads the recipe for the rows (optionalQuestion.ts) loads when the question is first
// asked, so every page doesn't carry it (the size limit).
export type { OptionalRow };

export interface OptionalQuestion {
  recipeName: string;
  /** "Sat dinner". */
  where: string;
  serves: number | null;
  rows: OptionalRow[];
  /** The lines ticked to begin with. */
  ticked: number[];
  /** The main button: "Add to plan", or "Save" when the meal's answer is being changed. */
  button: string;
}

interface Pending {
  question: OptionalQuestion;
  resolve: (use: number[] | null) => void;
}

class OptionalAsk {
  current = $state<Pending | null>(null);
  /** The "which way of cooking it?" sheet is open (M2): the layout loads it when first asked. */
  methodOpen = $state(false);

  /**
   * Ask which Optional ingredients of the recipe the meal will use. Resolves with the ids of the
   * ones to use (the others are left out), null when the person cancels, and undefined when
   * there is nothing to ask: the recipe has no Optional ingredient (or can't be read, in which
   * case adding it goes on as it always did and counts every line).
   * `optionalCount` is the number the caller already knows (0: no question, nothing is fetched).
   * `skipped`: the lines the meal leaves out now, for changing it; left out, every line starts
   * ticked.
   */
  async ask(
    recipe: { id: number; optionalCount?: number },
    where: string,
    options: {
      skipped?: number[];
      button?: string;
      servings?: number | null;
      /** The way of cooking it the meal uses (M2); left out: the one used last, else the first. */
      method?: number | null;
    } = {}
  ): Promise<number[] | null | undefined> {
    if (recipe.optionalCount === 0) return undefined;
    const { optionalRows } = await import('./optionalQuestion');
    const found = await optionalRows(recipe.id, options);
    if (!found) return undefined;
    const { name, serves, rows } = found;
    this.current?.resolve(null);
    const ids = rows.map((r) => r.id);
    return new Promise((resolve) => {
      this.current = {
        question: {
          recipeName: name,
          where,
          serves,
          rows,
          ticked: ids.filter((id) => !(options.skipped ?? []).includes(id)),
          button: options.button ?? 'Add to plan'
        },
        resolve
      };
    });
  }

  answer(use: number[]): void {
    const pending = this.current;
    this.current = null;
    pending?.resolve(use);
  }

  dismiss(): void {
    const pending = this.current;
    this.current = null;
    pending?.resolve(null);
  }
}

export const optionalAsk = new OptionalAsk();
