// What to buy in whole packs on a Shopping line (F120; cabledrawer 31 Oct and 7 Nov), worked out
// on the phone from the line's amount and the ingredient's Usual size, so it stays right while
// offline. The server says the same in `pack` (backend mealwright.buying): "1 jar (500 g) ·
// 120 g needed". With no Usual size known, the line says nothing here: the need is the amount.

import type { FoodSize, ShopFood } from './types';

const NBSP = ' ';

/** Python's amounts.exact_text: "123 g", "7.3 g", "1.235 kg", "under 0.1 g" (half up). */
export function exactText(amount: number, countedAs: 'weight' | 'volume'): string {
  const [small, big] = countedAs === 'weight' ? ['g', 'kg'] : ['ml', 'L'];
  const unit = (value: number) =>
    value >= 1000 ? `${String(value / 1000)}${NBSP}${big}` : `${String(value)}${NBSP}${small}`;
  const milli = Math.round(amount * 1000);
  if (milli > 0 && milli < 50) return `under ${unit(0.1)}`;
  if (milli >= 10_000) return unit(Math.floor((milli + 500) / 1000));
  return unit(Math.floor((milli + 50) / 100) / 10);
}

/** Python's amounts.count_text without "left": "5 eggs", "1½ onions", "under ½ egg". */
export function countText(
  amount: number,
  word: string | null | undefined,
  wordPlural: string | null | undefined
): string {
  const milli = Math.round(amount * 1000);
  const halves = Math.floor((milli + 250) / 500);
  const whole = Math.floor(halves / 2);
  const half = halves % 2 === 1;
  const number = whole && half ? `${whole}½` : half ? '½' : String(whole);
  if (halves === 0 && milli > 0) return word ? `under ½${NBSP}${word}` : 'under ½';
  if (!word) return number;
  const many = halves !== 1 && halves !== 2;
  return `${number}${NBSP}${many ? (wordPlural ?? `${word}s`) : word}`;
}

function amountText(food: ShopFood, amount: number): string {
  return food.counted_as === 'count'
    ? countText(amount, food.count_word, food.count_word_plural)
    : exactText(amount, food.counted_as);
}

/** The fewest whole packs that hold the need (at least one for any need). */
export function wholePacks(need: number, size: number): number {
  return Math.max(1, Math.ceil(need / size - 1e-9));
}

/** The size a line is bought in (F122, as the server's `pack_bought`): the Usual size, else
 * the only size; null with none, or with several and none Usual. */
export function usualSize(food: Pick<ShopFood, 'sizes'> | undefined): FoodSize | null {
  const sizes = food?.sizes ?? [];
  return sizes.find((s) => s.usual) ?? (sizes.length === 1 ? (sizes[0] ?? null) : null);
}

/** "1 jar (500 g) · 120 g needed", or null with no amount, no Usual size or a staple. */
export function packLine(food: ShopFood | undefined, need: number | null): string | null {
  if (!food || food.staple || need === null || need <= 0) return null;
  const size = usualSize(food);
  if (!size || size.amount <= 0) return null;
  const packs = wholePacks(need, size.amount);
  const word = packs === 1 ? size.name : size.plural;
  const buy = `${packs}${NBSP}${word} (${amountText(food, size.amount)})`;
  return `${buy} · ${amountText(food, need)} needed`;
}
