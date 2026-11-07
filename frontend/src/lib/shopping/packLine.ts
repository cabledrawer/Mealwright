// What to buy in whole packs on a Shopping line (F120; cabledrawer 31 Oct and 7 Nov), worked out
// on the phone from the line's amount and the ingredient's Usual size, so it stays right while
// offline. The server says the same in `pack` (backend mealwright.buying): "1 jar (500 g) ·
// 120 g needed". With no Usual size known, the line says nothing here: the need is the amount.

import { baseText } from './format';
import type { FoodSize, ShopFood } from './types';

const NBSP = ' ';

/** The fewest whole packs that hold the need (at least one for any need). */
export function wholePacks(need: number, size: number): number {
  return Math.max(1, Math.ceil(need / size - 1e-9));
}

/** The Usual size, else the first one; null when there is none. */
export function usualSize(food: Pick<ShopFood, 'sizes'> | undefined): FoodSize | null {
  const sizes = food?.sizes ?? [];
  return sizes.find((s) => s.usual) ?? sizes[0] ?? null;
}

/** "1 jar (500 g) · 120 g needed", or null with no amount, no Usual size or a staple. */
export function packLine(food: ShopFood | undefined, need: number | null): string | null {
  if (!food || food.staple || need === null || need <= 0) return null;
  const size = usualSize(food);
  if (!size || size.amount <= 0) return null;
  const packs = wholePacks(need, size.amount);
  const word = packs === 1 ? size.name : size.plural;
  const buy = `${packs}${NBSP}${word} (${baseText(size.amount, food.counted_as)})`;
  return `${buy} · ${baseText(need, food.counted_as)} needed`;
}
