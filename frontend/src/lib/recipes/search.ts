// Searching recipes for the "Pick an ingredient" list, which offers recipes as well as
// ingredients. The server's search (`GET /recipes?q=`) also looks in tags and ingredient names,
// so "dal" would find Sambar; the picker only offers recipes whose name has what was typed, so
// the server's answer is filtered by name here.

import { listFoods } from '#lib/client/foods.js';
import { listRecipes, type RecipeBrief } from '#lib/client/recipes.js';
import type { FoodRow } from '#lib/client/types.js';

/** Lower case, no accents, so "Rasam" finds "rasam" and "Pâté" finds "pate". */
export function fold(text: string): string {
  return text.normalize('NFD').replace(/\p{M}/gu, '').toLocaleLowerCase();
}

/** The recipes whose names contain what was typed, best matches (the name starts with it) first. */
export function pickRecipes(all: RecipeBrief[], query: string, limit = 6): RecipeBrief[] {
  const q = fold(query.trim());
  if (!q) return [];
  const found = all.filter((r) => fold(r.name).includes(q));
  found.sort(
    (a, b) =>
      Number(!fold(a.name).startsWith(q)) - Number(!fold(b.name).startsWith(q)) ||
      fold(a.name).localeCompare(fold(b.name))
  );
  return found.slice(0, limit);
}

/** Asks the server for each search, then keeps the recipes whose names match. */
export function recipeSearch(): (query: string) => Promise<RecipeBrief[]> {
  return async (query) => {
    if (!query.trim()) return [];
    const list = await listRecipes({ q: query, limit: 100 });
    return pickRecipes(list.recipes, query);
  };
}

/** The server's ingredients and the recipes whose names match what was typed, for a picker that
 *  links a line (the recipe editor's, and Check's). */
export function lineSearch(): (q: string) => Promise<{ foods: FoodRow[]; recipes: RecipeBrief[] }> {
  const findRecipes = recipeSearch();
  return async (q) => {
    const [foods, recipes] = await Promise.all([
      listFoods({ q, limit: 8 }).then((list) => list.foods),
      findRecipes(q).catch(() => [])
    ]);
    return { foods, recipes };
  };
}

/** One row of a picker's list. `paired`: a recipe and an ingredient have this very name (F189),
 *  so the two rows are labelled Recipe and Ingredient. */
export type Found =
  | { kind: 'ingredient'; food: FoodRow; paired: boolean }
  | { kind: 'recipe'; recipe: RecipeBrief; paired: boolean };

/** The order a picker lists what it found (F189, cabledrawer 8 Nov: "a recipe is offered before a
 *  plain ingredient of the same name"): the ingredients in the order the server gave them, each
 *  preceded by the recipe with exactly its name when there is one; then the other recipes. */
export function arrange(foods: FoodRow[], recipes: RecipeBrief[]): Found[] {
  const out: Found[] = [];
  const used = new Set<number>();
  for (const food of foods) {
    const same = recipes.find((r) => !used.has(r.id) && fold(r.name) === fold(food.name));
    if (same) {
      used.add(same.id);
      out.push({ kind: 'recipe', recipe: same, paired: true });
    }
    out.push({ kind: 'ingredient', food, paired: !!same });
  }
  for (const recipe of recipes) {
    if (!used.has(recipe.id)) out.push({ kind: 'recipe', recipe, paired: false });
  }
  return out;
}
