// "+ New ingredient: 'chilli flakes'" at the end of the Ingredients search results (F97, cabledrawer
// 31 Oct), the way Shopping's "Add an item" box offers one: when the typed text is not exactly the
// name, or another name, of an ingredient that is already there.

import type { FoodRow } from './client/types';

/** Case, accents and spacing ignored, the way the server folds a name for search
 *  ("Jalapeño" is "jalapeno", two spaces are one). */
const key = (text: string): string =>
  text.normalize('NFKD').replace(/\p{M}/gu, '').trim().replace(/\s+/gu, ' ').toLocaleLowerCase();

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
