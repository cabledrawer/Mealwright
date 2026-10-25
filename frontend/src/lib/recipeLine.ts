// The quiet line under a recipe's name in the All recipes list:
// "50 min · 320 kcal · all in stock but 1". Each part is there only when it is known; the
// calories say "nutrition unknown", never 0 (spec, Recipes; cabledrawer 19 Oct).

import type { RecipeRow } from './client/recipes';
import { dateWords } from './dates';

/** A number and its unit stay on one line. */
const NBSP = ' ';

export interface Part {
  text: string;
  /** Orange: something about to go off. */
  soon?: boolean;
}

/**
 * "all in stock", "all in stock but 1", "2 missing"; nothing when no ingredient counts.
 * When some line uses a recipe that isn't checked (`unchecked`), "all in stock" would say too
 * much: it says only what is missing, and nothing when nothing is (cabledrawer 20 Oct).
 */
export function stockWords(stock: RecipeRow['stock'], unchecked = false): string {
  if (!stock || stock.counted === 0) return '';
  if (unchecked) return stock.missing === 0 ? '' : `${stock.missing} missing`;
  if (stock.missing === 0) return 'all in stock';
  if (stock.missing === 1 && stock.counted > 1) return 'all in stock but 1';
  return `${stock.missing} missing`;
}

function lowerFirst(name: string): string {
  // "Spinach" → "spinach", "Toor dal" → "toor dal". A name with another capital in it ("Toor
  // Dal", "TVP", "Greek yoghurt from M&S") is left as it is written, never half lowered
  // ("toor Dal", 0.5.1).
  return /^[A-Z][^A-Z]*$/.test(name) ? name[0]!.toLowerCase() + name.slice(1) : name;
}

/** "Uses spinach (today)", "Uses spinach and paneer (tomorrow)", "Uses spinach and 2 more (Mon)". */
export function useSoonWords(soon: NonNullable<RecipeRow['use_soon']>): string {
  const names = soon.foods.map((food) => lowerFirst(food.name));
  const what =
    names.length <= 1
      ? (names[0] ?? '')
      : names.length === 2
        ? `${names[0]} and ${names[1]}`
        : `${names[0]} and ${names.length - 1} more`;
  const day = dateWords(soon.use_by, soon.days_left);
  const when = day === 'Today' || day === 'Tomorrow' ? day.toLowerCase() : day;
  return `Uses ${what} (${when})`;
}

/** The parts of a recipe's line, in order. */
export function recipeParts(recipe: RecipeRow): Part[] {
  const parts: Part[] = [];
  if (recipe.time_minutes !== null) parts.push({ text: `${recipe.time_minutes}${NBSP}min` });
  parts.push({
    text: recipe.kcal === null ? 'nutrition unknown' : `${Math.round(recipe.kcal)}${NBSP}kcal`
  });
  const stock = stockWords(recipe.stock, recipe.stock_unchecked);
  // Something about to go off is the better news; what is missing is still said.
  if (recipe.use_soon) parts.push({ text: useSoonWords(recipe.use_soon), soon: true });
  if (stock && (!recipe.use_soon || (recipe.stock?.missing ?? 0) > 0)) parts.push({ text: stock });
  return parts;
}

/** The same line as plain text, for tests and screen readers. */
export const recipeLine = (recipe: RecipeRow): string =>
  recipeParts(recipe)
    .map((part) => part.text)
    .join(' · ');
