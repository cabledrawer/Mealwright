// Amounts on the recipe page, scaled on screen only (cabledrawer 19 Oct, question 26): whole
// servings 1 to 99, and the saved recipe never changes. Spoons and cups show in quarters
// (¼ ½ ¾), counts in halves (the spec: counts to the nearest half), grams and millilitres as
// whole numbers. Kilograms and litres to two decimals is the builder's choice, for cabledrawer.
// At the recipe's own servings the amount is shown exactly as it was typed.

import type { RecipeLine } from './client/recipes';

/** A number and its unit stay on one line. */
const NBSP = '\u00a0';

export const MIN_SERVES = 1;
export const MAX_SERVES = 99;

const GLYPH: Record<number, string> = { 0.25: '¼', 0.5: '½', 0.75: '¾' };

/** 1.5 → "1½", 0.25 → "¼", 2 → "2". `value` must be a whole number of quarters. */
export function quarters(value: number): string {
  const whole = Math.floor(value);
  const glyph = GLYPH[value - whole];
  if (glyph) return `${whole || ''}${glyph}`;
  return String(whole);
}

const nearest = (value: number, step: number) => Math.max(step, Math.round(value / step) * step);

/** The scaled number for a unit: what to show, and the value it stands for. */
function scaled(value: number, unit: string | null): { text: string; value: number } {
  if (unit === 'g' || unit === 'ml') {
    const whole = Math.max(1, Math.round(value));
    return { text: String(whole), value: whole };
  }
  if (unit === 'kg' || unit === 'l') {
    const two = Math.round(value * 100) / 100;
    return { text: String(two), value: two };
  }
  // Spoons and cups in quarters; a count, a pinch or a packet in halves.
  const step = unit === 'tsp' || unit === 'tbsp' || unit === 'cup' ? 0.25 : 0.5;
  const near = nearest(value, step);
  return { text: quarters(near), value: near };
}

const PLURAL: Record<string, [string, string]> = {
  cup: ['cup', 'cups'],
  pinch: ['pinch', 'pinches']
};

/** The words after the number: "g", "cups", "packets"; null for a plain count. */
function unitWords(line: RecipeLine, value: number): string | null {
  if (line.size) return value > 1 ? line.size.plural : line.size.name;
  if (!line.unit) return null;
  const forms = PLURAL[line.unit];
  if (!forms) return line.unit;
  return value > 1 ? forms[1] : forms[0];
}

/**
 * The amount of an ingredient line at `factor` times the recipe's own servings: "200 g",
 * "1½ cups", "10", or null when the line has no amount.
 */
export function lineAmount(line: RecipeLine, factor: number): string | null {
  if (line.amount === null || line.amount_text === null) return null;
  const now =
    factor === 1
      ? { text: line.amount_text, value: line.amount }
      : scaled(line.amount * factor, line.size ? null : line.unit);
  const words = unitWords(line, now.value);
  return words ? `${now.text}${NBSP}${words}` : now.text;
}

/** "Makes 1.5 litres" without the word "Makes": the amount at `factor`, with its unit. */
export function makesAmount(
  makes: { amount: number; amount_text: string; unit: string },
  factor: number
): string {
  const known = ['g', 'kg', 'ml', 'l'].includes(makes.unit);
  const now =
    factor === 1
      ? { text: makes.amount_text, value: makes.amount }
      : scaled(makes.amount * factor, known ? makes.unit : null);
  const unit = makes.unit === 'l' ? (now.value === 1 ? 'litre' : 'litres') : makes.unit;
  return `${now.text}${NBSP}${unit}`;
}

/** Nutrition values: whole numbers for calories, up to one decimal for grams. */
export const kcalText = (value: number) => `${Math.round(value)}`;
export const gramsText = (value: number) => `${Math.round(value * 10) / 10}${NBSP}g`;

/** The scale: servings now over the recipe's own. */
export const factorOf = (now: number, own: number) => now / own;
