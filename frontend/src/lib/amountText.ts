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
  // A plain fraction first, and a space before a fraction with a slash after a whole number:
  // "10/3" is ten thirds, never 1 and 0/3 (RF4 I11, as in importAmount.ts).
  const match = typed.match(
    /^(?:(?<plain>\d+\/\d+)|(?<whole>\d+(?:[.,]\d+)?)?(?:\s*(?<glyph>[¼½¾])|\s+(?<slash>\d+\/\d+))?)\s*(?<unit>[\p{L} ]*?)\.?$/u
  );
  if (!match?.groups) return null;
  const { plain, whole, glyph, slash, unit: unitText = '' } = match.groups;
  const part = plain ?? glyph ?? slash;
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

const IRREGULAR: Record<string, string> = {
  loaf: 'loaves',
  leaf: 'leaves',
  half: 'halves',
  knife: 'knives',
  dozen: 'dozen',
  fish: 'fish',
  sheep: 'sheep',
  potato: 'potatoes',
  tomato: 'tomatoes'
};

/**
 * An ingredient counted one by one, as it reads in a sentence: "lemons" ("How many lemons?"),
 * lower case. The same rule as the server's `counted_name` (F197, cabledrawer 8 Nov): a name that
 * already ends in "s" ("Eggs", "Chickpeas") is left as it is.
 */
export function manyOf(name: string): string {
  const word = name.trim().toLocaleLowerCase();
  if (!word || (word.endsWith('s') && !word.endsWith('ss'))) return word;
  const at = word.lastIndexOf(' ') + 1;
  const head = word.slice(0, at);
  const last = word.slice(at);
  const irregular = IRREGULAR[last];
  if (irregular) return head + irregular;
  if (/(s|x|z|ch|sh)$/.test(last)) return `${head}${last}es`;
  if (/[^aeiou]y$/.test(last)) return `${head}${last.slice(0, -1)}ies`;
  return `${head}${last}s`;
}
