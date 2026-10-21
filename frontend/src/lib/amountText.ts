// Reading an amount someone typed ("½ packet", "1½ packets", "250 g", "2") into the
// API's AmountIn (contract 4.3). The server does the maths and says no to units it
// doesn't know; this only splits the number from the unit.

import type { AmountIn, Food } from './client/types';

const FRACTIONS: Record<string, number> = { '¼': 0.25, '½': 0.5, '¾': 0.75 };

/** The most characters an amount's number may have ("1 1/2", "0,75"): the server's limit too. */
export const MAX_AMOUNT_TEXT = 20;
/** The longest unit or size name the server takes after the number. */
const MAX_UNIT_TEXT = 40;
/** The number, a space, the unit and a full stop. Longer text is no amount, and is refused
 * before the pattern below reads it: that takes time growing with the square of the length. */
export const MAX_TYPED_AMOUNT = MAX_AMOUNT_TEXT + 1 + MAX_UNIT_TEXT + 1;

/** The unit to use when only a number was typed: the usual size, else g / ml / items. */
export function defaultUnit(food: Pick<Food, 'counted_as' | 'sizes'>): string {
  const usual = food.sizes.find((size) => size.usual);
  if (usual && food.counted_as !== 'count') return usual.name;
  return food.counted_as === 'weight' ? 'g' : food.counted_as === 'volume' ? 'ml' : 'count';
}

export function parseAmount(
  text: string,
  food: Pick<Food, 'counted_as' | 'sizes' | 'count_word' | 'count_word_plural'>
): AmountIn | null {
  const typed = text.trim().toLowerCase();
  if (typed.length > MAX_TYPED_AMOUNT) return null;
  if (/^[\d.,¼½¾/\s]*/u.exec(typed)![0].trimEnd().length > MAX_AMOUNT_TEXT) return null;
  const match = typed.match(/^(\d+(?:[.,]\d+)?)?\s*([¼½¾]|\d+\/\d+)?\s*([\p{L} ]*?)\.?$/u);
  if (!match) return null;
  const [, whole, part, unitText = ''] = match;
  if (!whole && !part) return null;
  let amount = whole ? Number(whole.replace(',', '.')) : 0;
  if (part) {
    if (part in FRACTIONS) amount += FRACTIONS[part]!;
    else {
      const [top, bottom] = part.split('/').map(Number) as [number, number];
      if (!bottom) return null;
      amount += top / bottom;
    }
  }
  if (!(amount > 0) || !Number.isFinite(amount)) return null;
  const unit = unitText.trim();
  if (!unit) return { amount, unit: defaultUnit(food) };
  const countWords = [food.count_word, food.count_word_plural, 'item', 'items'].filter(Boolean);
  if (countWords.includes(unit)) return { amount, unit: 'count' };
  const size = food.sizes.find((s) => s.name === unit || s.plural === unit);
  return { amount, unit: size ? size.name : unit };
}
