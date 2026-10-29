// "Add an item" with an amount in front: "1 l milk" is Milk, 1 litre (F63, cabledrawer 28 Oct), so
// the add joins an existing 1 L line as 0.5's rule does. This only cuts the typed text into
// "1 l" and "milk"; the number and unit are read by the same reader as the amount box
// (amountText.parseAmount through amountEdit.toBaseAmount), and it all works offline.

import { parseAmount } from '#lib/amountText.js';
import type { Food } from '#lib/client/types.js';

/** The number as parseAmount reads it: 1, 1.5, 1,5, ½, 1½, 1/2, 1 1/2. */
const NUMBER = String.raw`(?:\d+(?:[.,]\d+)?\s*(?:[¼½¾]|\d+\/\d+)?|[¼½¾]|\d+\/\d+)`;

/** Units a phone can read without knowing the ingredient (amountEdit.ts: g, kg, ml, l). */
const UNITS = String.raw`(?:g|gr|gram|grams|kg|kgs|kilo|kilos|kilogram|kilograms|ml|mls|millilitres?|milliliters?|l|ltr|litres?|liters?)`;

const ONLY_UNIT = new RegExp(`^${UNITS}\\.?$`, 'iu');
const LEADING = new RegExp(`^(${NUMBER})\\s*(${UNITS})?\\.?\\s+(\\S.*)$`, 'iu');

/** The longest an ingredient's name may be (the server's limit, foods.py Name), plus room for
 * the amount in front of it. Longer text is no amount and a name the server would refuse. */
export const MAX_NAME = 100;
export const MAX_ADD_TEXT = MAX_NAME + 33;

export interface TypedAmount {
  /** What goes to the reader: "1 l", "3". */
  amountText: string;
  /** What is left to search for: "milk". */
  name: string;
}

/** A number (with a unit) in front of a name, or null when the text has none. */
export function splitAmount(text: string): TypedAmount | null {
  if (text.length > MAX_ADD_TEXT) return null;
  const match = LEADING.exec(text.trim());
  if (!match) return null;
  const [, number, unit, name] = match;
  // "0 g butter", "00 flour", "007": a number that is nothing, or starts with a zero and goes
  // on, is the start of a name, not an amount.
  if (!(Number.parseFloat(number!.replace(',', '.')) > 0) && !/[¼½¾]|\//.test(number!)) return null;
  if (/^0\d/.test(number!.trim())) return null;
  if (!unit && ONLY_UNIT.test(name!.trim())) return null; // "250 g": an amount, no name
  return {
    amountText: unit ? `${number!.trim()} ${normalUnit(unit)}` : number!.trim(),
    name: name!.trim()
  };
}

/** The spellings above as the reader's own g, kg, ml and l. */
function normalUnit(unit: string): string {
  const u = unit.toLowerCase();
  if (u.startsWith('k')) return 'kg';
  if (u.startsWith('m')) return 'ml';
  if (u.startsWith('l')) return 'l';
  return 'g';
}

/**
 * The amount as it will be read for this ingredient, for the match row: a bare 2 for garlic
 * weighed in grams is "2 g", not "2". The same reader as the amount box.
 */
export function readAs(
  amountText: string,
  food: Pick<Food, 'counted_as' | 'sizes' | 'count_word' | 'count_word_plural'>
): string | null {
  const asked = parseAmount(amountText, food);
  if (!asked) return null;
  const number = String(Math.round(asked.amount * 1000) / 1000);
  if (!asked.unit || asked.unit === 'count') return number;
  // Written as the app writes it: "1 L", and a packet size in the plural when it isn't one.
  const size = food.sizes.find((s) => s.name === asked.unit);
  const unit = asked.unit === 'l' ? 'L' : size && asked.amount !== 1 ? size.plural : asked.unit;
  return `${number} ${unit}`;
}
