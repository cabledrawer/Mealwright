// "+ New ingredient: 'chilli flakes'" at the end of the Ingredients search results (F97, cabledrawer
// 31 Oct), the way Shopping's "Add an item" box offers one: when the typed text is not exactly the
// name, or another name, of an ingredient that is already there.

import type { FoodRow } from './client/types';

/** Case, accents and spacing ignored, the way the server folds a name for search
 *  ("Jalape\u00f1o" is "jalapeno", "Wei\u00dfwurst" is "weisswurst", two spaces are one). Only the
 *  marks that sit on a letter are dropped (\p{Mn}); the spacing marks of Devanagari and the like
 *  are part of the letter. */
const key = (text: string): string =>
  text
    .toLocaleLowerCase()
    .replace(/[\u00df\u1e9e]/gu, 'ss')
    .replace(/\u03c2/gu, '\u03c3')
    .normalize('NFKD')
    .replace(/\p{Mn}/gu, '')
    .trim()
    .replace(/\s+/gu, ' ');

/** The name to offer ("chilli flakes"), or null when the text is empty or is exactly the name or
 *  another name of one of the ingredients found for it. Partial matches don't stop the offer. */
export function newNameFor(typed: string, found: readonly FoodRow[]): string | null {
  const wanted = key(typed);
  if (!wanted) return null;
  const taken = found.some(
    (food) => key(food.name) === wanted || (food.other_names ?? []).some((n) => key(n) === wanted)
  );
  return taken ? null : typed.trim().replace(/\s+/gu, ' ');
}
