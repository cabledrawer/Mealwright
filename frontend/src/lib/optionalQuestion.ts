// The rows of "Which optional ingredients will you use?" (R3, M2): reading the recipe and its
// stock for the way of cooking it the meal uses, and the words on each row. Kept apart from
// optionalAsk.svelte.ts, which every page loads, and loaded when the question is first asked
// (the size limit).

import { getRecipe, getRecipeStock, type LineStock, type RecipeLine } from './client/recipes';
import { lineAmount } from './recipeAmounts';

export interface OptionalRow {
  id: number;
  words: string;
  /** "2 tbsp · not in the pantry". */
  detail: string;
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

export function rowOf(line: RecipeLine, stock: LineStock | undefined, factor = 1): OptionalRow {
  const detail = [lineAmount(line, factor), stateWords(stock)].filter(Boolean).join(' · ');
  return { id: line.id, words: line.food?.name ?? line.words, detail };
}

/**
 * The recipe's Optional lines as rows for the way of cooking it the meal uses (`method`; left
 * out: the one used last, else the first), with the amounts for the meal's own servings. Null when
 * there is nothing to ask: no Optional line, or the recipe can't be read (adding it then goes on as
 * it always did and counts every line).
 */
export async function optionalRows(
  recipeId: number,
  options: { servings?: number | null; method?: number | null }
): Promise<{ name: string; serves: number | null; rows: OptionalRow[] } | null> {
  try {
    const found0 = await getRecipe(recipeId);
    const second = found0.second_method;
    const wanted = options.method ?? found0.methods?.find((m) => m.used_last)?.id ?? null;
    const useSecond = !!second && wanted === second.id;
    const found = useSecond && second ? { ...found0, lines: second.lines } : found0;
    const stock = await getRecipeStock(recipeId, undefined, wanted).catch(() => null);
    // Amounts for the meal's own servings, not the recipe's (a meal for 3 of a recipe for 6).
    const factor = found.serves && options.servings ? options.servings / found.serves : 1;
    const by = new Map((stock?.lines ?? []).map((s) => [s.line_id, s]));
    const rows = found.lines
      .filter((l) => l.kind === 'ingredient' && l.optional)
      .map((l) => rowOf(l, by.get(l.id), factor));
    return rows.length ? { name: found.name, serves: found.serves, rows } : null;
  } catch {
    return null;
  }
}
