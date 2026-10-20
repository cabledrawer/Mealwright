// Recipes: the All recipes list (docs/dev/api-0.4-recipes.md, sections 2 and 4).

import { api } from '$lib/api';
import type { Ref } from './types';

/** What the pantry says about a recipe's ingredients. */
export interface StockHint {
  /** The ingredients that count (lines with no amount and headings never do). */
  counted: number;
  missing: number;
  can_cook_now: boolean;
}

/** What a recipe uses that is about to go off. `days_left` 0 is today. */
export interface UseSoonHint {
  foods: Ref[];
  use_by: string;
  days_left: number;
}

export interface RecipeRow {
  id: number;
  name: string;
  description: string | null;
  time_minutes: number | null;
  serves: number | null;
  tags: string[];
  ingredient_count: number;
  /** Per serving; null is unknown, never 0. */
  kcal: number | null;
  stock: StockHint | null;
  use_soon: UseSoonHint | null;
  /** Some line uses a recipe that isn't checked (not made ahead): never "all in stock". */
  stock_unchecked: boolean;
}

export interface RecipePage {
  /** How many match the search and filters. */
  total: number;
  /** Every recipe the household has: the number in the title. */
  all_recipes: number;
  recipes: RecipeRow[];
  next: string | null;
}

export interface TagCount {
  name: string;
  recipes: number;
}

export function listRecipes(
  options: {
    q?: string;
    tag?: string | null;
    canCookNow?: boolean;
    after?: string | null;
    limit?: number;
  } = {}
): Promise<RecipePage> {
  const params = new URLSearchParams();
  if (options.q?.trim()) params.set('q', options.q.trim());
  if (options.tag) params.set('tag', options.tag);
  if (options.canCookNow) params.set('can_cook_now', 'true');
  if (options.after) params.set('after', options.after);
  if (options.limit) params.set('limit', String(options.limit));
  const query = params.toString();
  return api<RecipePage>('GET', `/recipes${query ? `?${query}` : ''}`);
}

/** The tags the household uses, A to Z: the filter row. */
export const listTags = () => api<{ tags: TagCount[] }>('GET', '/recipes/tags');

// --- One recipe (the recipe page) ---------------------------------------------------------

export interface SizeRef extends Ref {
  plural: string;
}

/** One ingredient line, or a heading. */
export interface RecipeLine {
  id: number;
  kind: 'ingredient' | 'heading';
  /** As the recipe's author wrote it: "thuvaram paruppu". */
  words: string;
  amount: number | null;
  /** The amount as typed: "1½". */
  amount_text: string | null;
  /** g, kg, ml, l, tsp, tbsp, cup or pinch; null is a count (or a size). */
  unit: string | null;
  size: SizeRef | null;
  food: Ref | null;
  recipe: Ref | null;
  /** recipe_removed: the recipe it used was deleted; none: not linked. Null for a heading. */
  link: 'ingredient' | 'recipe' | 'recipe_removed' | 'none' | null;
  note: string | null;
}

export interface RecipeStep {
  id: number;
  kind: 'step' | 'heading';
  text: string;
}

export interface Recipe {
  id: number;
  name: string;
  description: string | null;
  time_minutes: number | null;
  serves: number | null;
  makes: { amount: number; amount_text: string; unit: string } | null;
  made_ahead: boolean;
  tags: string[];
  /** Per serving; null is unknown, never 0. */
  nutrition: {
    kcal: number | null;
    protein: number | null;
    carbs: number | null;
    fat: number | null;
    fibre: number | null;
  };
  lines: RecipeLine[];
  steps: RecipeStep[];
  source_note: string | null;
  version: number;
}

/** Where one ingredient line is in the pantry (GET /recipes/{id}/stock). */
export interface LineStock {
  line_id: number;
  /** The pantry ingredient it is checked against (a made-ahead recipe's own, for a recipe). */
  food: Ref;
  state: 'in_stock' | 'staple' | 'short' | 'missing';
  /** Where most of it is, when in stock: "Cupboard". */
  place: string | null;
}

export interface RecipeStock {
  lines: LineStock[];
  counted: number;
  missing: number;
  stock_unchecked: boolean;
}

export const getRecipe = (id: number | string) => api<Recipe>('GET', `/recipes/${id}`);
export const getRecipeStock = (id: number | string) =>
  api<RecipeStock>('GET', `/recipes/${id}/stock`);
