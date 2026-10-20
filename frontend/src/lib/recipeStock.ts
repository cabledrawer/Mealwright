// The recipe page's stock marks and its "N missing · Add to the list" line. The rules are the
// list's (cabledrawer 19 and 20 Oct); the server decides what is in stock (GET /recipes/{id}/stock),
// and the page adds what only it knows: what is on the shopping list right now.
// "On list" is orange, "Cupboard" and the other places green, "Staple" grey, and an ingredient
// that is short or missing has a dashed ring. Colour never carries the meaning alone: the ring
// is solid, dashed or hollow, and every mark but "missing" has its words.

import type { LineStock } from './client/recipes';
import type { Ref } from './client/types';

export type MarkKind = 'in' | 'staple' | 'list' | 'short' | 'missing';

export interface Mark {
  kind: MarkKind;
  /** The words at the end of the line; null for missing (the line under the list says it). */
  label: string | null;
}

/**
 * What to show beside a line: in stock (the place), a staple, on the list, short ("Not
 * enough") or missing. A line the server does not count has no mark. Something in stock
 * or a staple stays that; otherwise being on the shopping list wins.
 */
export function markFor(stock: LineStock | undefined, onList: boolean): Mark | null {
  if (!stock) return null;
  if (stock.state === 'staple') return { kind: 'staple', label: 'Staple' };
  if (stock.state === 'in_stock') return { kind: 'in', label: stock.place ?? 'In stock' };
  if (onList) return { kind: 'list', label: 'On list' };
  if (stock.state === 'short') return { kind: 'short', label: 'Not enough' };
  return { kind: 'missing', label: null };
}

/** The ingredients to add to the shopping list: short or missing, not already on it, once each. */
export function toAdd(lines: LineStock[], onList: (foodId: number) => boolean): Ref[] {
  const found = new Map<number, Ref>();
  for (const stock of lines) {
    if (stock.state !== 'short' && stock.state !== 'missing') continue;
    if (onList(stock.food.id)) continue;
    found.set(stock.food.id, stock.food);
  }
  return [...found.values()];
}
