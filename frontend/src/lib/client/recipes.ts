// Recipes (docs/dev/api-0.4-recipes.md): the All recipes list, one recipe, and the editor's
// saving, loop guard, tags and photos. Online only in 0.4: nothing here touches the offline queue.

import { api } from '#lib/api.js';
import type { Change, Ref, Who } from './types';

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

/** The few fields every recipe answer has: the editor's picker uses them. */
export interface RecipeBrief {
  id: number;
  name: string;
  description: string | null;
  makes: { amount: number; amount_text: string; unit: string } | null;
  /** The cover photo; null when there is none. */
  photo: PhotoOut | null;
  version: number;
}

export interface RecipeRow extends RecipeBrief {
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
    /** Only recipes that use something about to go off (`use_soon=true`). */
    useSoon?: boolean;
    after?: string | null;
    limit?: number;
  } = {}
): Promise<RecipePage> {
  const params = new URLSearchParams();
  if (options.q?.trim()) params.set('q', options.q.trim());
  if (options.tag) params.set('tag', options.tag);
  if (options.canCookNow) params.set('can_cook_now', 'true');
  if (options.useSoon) params.set('use_soon', 'true');
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
  /** With its other names, so words like "thu" can show as its name (cabledrawer 25 Oct). */
  food: (Ref & { other_names: string[] }) | null;
  recipe: Ref | null;
  /** recipe_removed: the recipe it used was deleted; none: not linked. Null for a heading. */
  link: 'ingredient' | 'recipe' | 'recipe_removed' | 'none' | null;
  note: string | null;
}

export interface RecipeStep {
  id: number;
  kind: 'step' | 'heading';
  text: string;
  /** The ingredient lines the step uses (Cook mode's per-step ingredients); none for a heading. */
  lines?: { line_id: number; line: number; kind: 'guessed' | 'by_hand' }[];
}

export interface Nutrition {
  kcal: number | null;
  protein: number | null;
  carbs: number | null;
  fat: number | null;
  fibre: number | null;
}

export interface PhotoOut {
  id: number;
  width: number;
  height: number;
  url: string;
  list_width: number;
  list_height: number;
  list_url: string;
}

/** Where an imported recipe came from (null for one that wasn't imported from a link). The
 * server never visits `url` again; opening it is the person's own click. */
export interface RecipeSource {
  url: string;
  /** The address without "www.": "bbcgoodfood.com". */
  site: string;
  imported_at: string;
  author: string | null;
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
  nutrition: Nutrition;
  lines: RecipeLine[];
  steps: RecipeStep[];
  source_note: string | null;
  /** Set for a recipe imported from a link. Older answers may leave it out. */
  source?: RecipeSource | null;
  /** The cover photo; null when there is none. */
  photo: PhotoOut | null;
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

/** The whole answer: the recipe page uses the `Recipe` part, the editor all of it. */
export interface RecipeOut extends Recipe {
  homemade: Ref | null;
  used_by: Ref[];
  updated_at: string;
  updated_by: Who;
}

/** The editor's names for a line and a step. */
export type LineOut = RecipeLine;
export type StepOut = RecipeStep;

export const getRecipe = (id: number | string) => api<RecipeOut>('GET', `/recipes/${id}`);
/** `servings` is what − / + chose (1 to 99); left out, the recipe's own Serves is used. */
export const getRecipeStock = (id: number | string, servings?: number | null) =>
  api<RecipeStock>(
    'GET',
    `/recipes/${id}/stock${servings === undefined || servings === null ? '' : `?servings=${servings}`}`
  );

// --- The editor ---------------------------------------------------------------------------

/** One line as it is sent. */
export interface LineIn {
  id?: number;
  kind: 'ingredient' | 'heading';
  words: string;
  amount?: string | null;
  unit?: string | null;
  size_id?: number | null;
  food_id?: number | null;
  recipe_id?: number | null;
  note?: string | null;
}

/** What `POST /recipes` takes; `PUT` adds `version` and `overwrite`. */
export interface RecipeIn {
  name: string;
  description: string | null;
  time_minutes: number | null;
  serves: number | null;
  makes: { amount: string; unit: string } | null;
  made_ahead: boolean;
  homemade_name: string | null;
  tags: string[];
  nutrition: Record<keyof Nutrition, string | null>;
  lines: LineIn[];
  steps: { kind: 'step' | 'heading'; text: string }[];
  source_note: string | null;
  /** Left out: the photo stays. null: no photo. A number: that upload. */
  photo_id?: number | null;
}

export interface Blocked {
  id: number;
  name: string;
  reason: string;
  chain: string[];
}

const key = (idempotencyKey: string) => ({ idempotencyKey });

export const createRecipe = (body: RecipeIn, idempotencyKey: string) =>
  api<RecipeOut>('POST', '/recipes', body, key(idempotencyKey));

/** A copy named "<name> (copy)": everything in the recipe, none of its cooked history or plan. */
export const duplicateRecipe = (id: number, idempotencyKey: string) =>
  api<RecipeOut>('POST', `/recipes/${id}/duplicate`, undefined, key(idempotencyKey));

export const saveRecipe = (
  id: number,
  body: RecipeIn,
  version: number,
  overwrite: boolean,
  idempotencyKey: string
) => api<RecipeOut>('PUT', `/recipes/${id}`, { ...body, version, overwrite }, key(idempotencyKey));

export const deleteRecipe = (id: number, idempotencyKey: string) =>
  api<{ change: Change }>('DELETE', `/recipes/${id}`, undefined, key(idempotencyKey));

/** The recipes this one can't use as an ingredient, and why (the loop guard). */
export const cannotUse = (id: number) =>
  api<{ recipes: Blocked[] }>('GET', `/recipes/${id}/cannot-use`).then((r) => r.recipes);

/** Tags the household already uses, the ones starting with `q` first. */
export const suggestTags = (q: string) =>
  api<{ tags: { name: string; recipes: number }[] }>(
    'GET',
    `/recipes/tags?q=${encodeURIComponent(q)}`
  ).then((r) => r.tags);

/** A photo's own file is the body; the server finds out what it is from its bytes. */
export const uploadPhoto = (file: Blob) =>
  api<PhotoOut>('POST', '/recipes/photos', file, { timeoutMs: 120_000 });

/** An upload that isn't on a recipe (a cancelled editor, or a photo swapped before Save). */
export const deletePhoto = (id: number) => api<void>('DELETE', `/recipes/photos/${id}`);
