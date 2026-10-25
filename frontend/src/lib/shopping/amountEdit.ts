// Turning what someone types for "how much to buy" ("500 g", "1½ packets", "2 kg", "3") into a
// base amount (g, ml or items) with an optional size, using only conversions a phone can
// do offline: kg and L, and the ingredient's own sizes (sync-protocol 4.3).

import { parseAmount } from '#lib/amountText.js';

export interface EditFood {
  counted_as: 'weight' | 'volume' | 'count';
  sizes: { id: number; name: string; plural: string; amount: number; usual: boolean }[];
  count_word: string | null;
  count_word_plural: string | null;
}

export type Parsed = { amount: number; sizeId: number | null } | { problem: string };

export function toBaseAmount(text: string, food: EditFood): Parsed {
  const asked = parseAmount(text, {
    counted_as: food.counted_as,
    sizes: food.sizes as never,
    count_word: food.count_word,
    count_word_plural: food.count_word_plural
  });
  if (!asked || !asked.unit) return { problem: 'Type an amount, like 500 g or 2 packets.' };
  const unit = asked.unit.toLowerCase();
  const size = food.sizes.find((s) => s.name === unit || s.plural === unit);
  if (size) return { amount: round(asked.amount * size.amount), sizeId: size.id };
  const base = food.counted_as;
  if (base === 'weight' && (unit === 'g' || unit === 'kg')) {
    return { amount: round(asked.amount * (unit === 'kg' ? 1000 : 1)), sizeId: null };
  }
  if (base === 'volume' && (unit === 'ml' || unit === 'l')) {
    return { amount: round(asked.amount * (unit === 'l' ? 1000 : 1)), sizeId: null };
  }
  if (base === 'count' && unit === 'count') return { amount: asked.amount, sizeId: null };
  return {
    problem:
      base === 'weight'
        ? 'Use g, kg or one of its sizes, like packet.'
        : base === 'volume'
          ? 'Use ml, L or one of its sizes, like bottle.'
          : 'Type a number, or one of its sizes, like dozen.'
  };
}

const round = (n: number) => Math.round(n * 1000) / 1000;
