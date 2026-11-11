// The add box while the server can't be reached: search the offline copy's ingredients by
// any of their names (sync-protocol 11.1: the copy keeps every ingredient for the add box).
// The same matching and order as the server's search (backend names.py, search_match):
// the name starts with it, the name contains it, another name starts with it, another name
// contains it; then by name. Like the server, it leaves out removed and merged ingredients.

import type { FoodRow } from '#lib/client/types.js';
import type { ShoppingCopy } from './types';

/** Lower case without accents: "Jalapeño" → "jalapeno" (as the server's fold). */
export function fold(text: string): string {
  return text.toLocaleLowerCase().normalize('NFKD').replace(/\p{M}/gu, '').trim();
}

function match(name: string, others: string[], needle: string): [number, string | null] | null {
  const folded = fold(name);
  if (folded.startsWith(needle)) return [0, null];
  if (folded.includes(needle)) return [1, null];
  let best: [number, string | null] | null = null;
  for (const other of others) {
    const o = fold(other);
    if (!o.includes(needle)) continue;
    const rank = o.startsWith(needle) ? 2 : 3;
    if (!best || rank < best[0]) best = [rank, other];
  }
  return best;
}

/** Up to `limit` ingredients of the copy that `text` finds, best first. */
export function searchCopy(copy: ShoppingCopy, text: string, limit = 8): FoodRow[] {
  const needle = fold(text);
  if (!needle) return [];
  const places = new Map(copy.places.map((p) => [p.id, { id: p.id, name: p.name }]));
  return (
    copy.foods
      // Made on this phone and not sent yet: no ID the server knows. Removed or merged
      // into another: the server's search doesn't offer them either.
      .filter((food) => food.id > 0 && !food.removed && !food.merged_into_id)
      .flatMap((food) => {
        const found = match(food.name, food.other_names, needle);
        return found ? [{ food, rank: found[0], matched: found[1] }] : [];
      })
      .sort((a, b) => a.rank - b.rank || fold(a.food.name).localeCompare(fold(b.food.name)))
      .slice(0, limit)
      .map(({ food, matched }) => ({
        id: food.id,
        name: food.name,
        other_names: food.other_names,
        matched_name: matched,
        counted_as: food.counted_as,
        staple: food.staple,
        counted_as_display: '',
        place: food.place_id === null ? null : (places.get(food.place_id) ?? null),
        stand_ins: [],
        maybe_same: []
      }))
  );
}

/**
 * The matches the add box offers, best first (F224): the name typed exactly, then its plural or
 * singular ("Onion" finds "Onions"), then the rest in the order they came ("Onion powder"). The
 * server and the offline copy both list "Onion powder" before "Onions" (by name), which made
 * "Onion" offer "Add as bought" for the powder. Stable: matches of one kind keep their order.
 */
export function rankMatches<T extends { name: string }>(found: T[], typed: string): T[] {
  const needle = fold(typed);
  if (!needle) return found;
  const kind = (name: string): number => {
    const folded = fold(name);
    if (folded === needle) return 0;
    const plural = (a: string, b: string) => a === `${b}s` || a === `${b}es`;
    return plural(folded, needle) || plural(needle, folded) ? 1 : 2;
  };
  return found
    .map((food, index) => ({ food, index, rank: kind(food.name) }))
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map(({ food }) => food);
}
