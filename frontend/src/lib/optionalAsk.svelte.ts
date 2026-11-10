// "Which optional ingredients will you use?" (R3, cabledrawer 6 and 9 Nov; mockup PlanOptional08): a
// recipe with Optional ingredient lines asks before it is added to the plan, and again from its
// meal when the person wants to change the answer. PlanOptional.svelte shows the question; the
// ticked ones go on the shopping list if they are needed and come out of the pantry at Cooked
// it, the others don't. Online only, like the rest of the Plan.

import { getRecipe, getRecipeStock, type LineStock, type RecipeLine } from './client/recipes';
import { lineAmount } from './recipeAmounts';

export interface OptionalRow {
  id: number;
  words: string;
  /** "2 tbsp · not in the pantry". */
  detail: string;
}

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

/** Where a line is in the pantry, in words (proposed, for cabledrawer; the mockup's two are exact). */
export function stateWords(stock: LineStock | undefined): string {
  if (!stock) return '';
  switch (stock.state) {
    case 'in_stock':
      return stock.place ? `in the ${stock.place.toLocaleLowerCase()}` : 'in the pantry';
    case 'staple':
      return 'a staple';
    case 'short':
      return 'not enough in the pantry';
    default:
      return 'not in the pantry';
  }
}

/** The sheet's own line about how many there are (the singular is proposed, for cabledrawer). */
export function optionalQuestionWords(count: number): string {
  return count === 1
    ? 'This recipe has 1 optional ingredient. Will you use it?'
    : `This recipe has ${count} optional ingredients. Will you use them?`;
}

export function rowOf(line: RecipeLine, stock: LineStock | undefined): OptionalRow {
  const detail = [lineAmount(line, 1), stateWords(stock)].filter(Boolean).join(' · ');
  return { id: line.id, words: line.food?.name ?? line.words, detail };
}

class OptionalAsk {
  current = $state<Pending | null>(null);

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
    options: { skipped?: number[]; button?: string } = {}
  ): Promise<number[] | null | undefined> {
    if (recipe.optionalCount === 0) return undefined;
    let rows: OptionalRow[];
    let name: string;
    let serves: number | null;
    try {
      const [found, stock] = await Promise.all([
        getRecipe(recipe.id),
        getRecipeStock(recipe.id).catch(() => null)
      ]);
      const by = new Map((stock?.lines ?? []).map((s) => [s.line_id, s]));
      rows = found.lines
        .filter((l) => l.kind === 'ingredient' && l.optional)
        .map((l) => rowOf(l, by.get(l.id)));
      name = found.name;
      serves = found.serves;
    } catch {
      return undefined;
    }
    if (!rows.length) return undefined;
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
