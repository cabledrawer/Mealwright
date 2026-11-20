// Amount wording for the pack sheet: base amounts (g, ml, items) in plain words.

import type { ShopFood } from './types';
import { NBSP } from '../words.js';
import { plural } from '../words.js';

const trim = (n: number) => String(Math.round(n * 100) / 100).replace(/\.0+$/, '');

export function baseText(amount: number, countedAs: ShopFood['counted_as']): string {
  if (countedAs === 'weight')
    return amount >= 1000 ? `${trim(amount / 1000)}${NBSP}kg` : `${trim(amount)}${NBSP}g`;
  if (countedAs === 'volume')
    return amount >= 1000 ? `${trim(amount / 1000)}${NBSP}L` : `${trim(amount)}${NBSP}ml`;
  return trim(amount);
}

/** A part of an amount in words, to two significant figures with "about" when that changed it
 * (F183: a quarter of 250 g is "about 63 g", never "62.5 g"). Counts keep their own wording. */
export function partText(amount: number, countedAs: ShopFood['counted_as']): string {
  if (countedAs === 'count') return baseText(amount, countedAs);
  const rounded = Number(amount.toPrecision(2));
  const text = baseText(rounded, countedAs);
  return rounded === amount ? text : `about${NBSP}${text}`;
}

/** "2 × 200 g". */
export function packText(count: number, pack: number, countedAs: ShopFood['counted_as']): string {
  return `${count}${NBSP}×${NBSP}${baseText(pack, countedAs)}`;
}

/** The unit names a person may type in "Other…", with how many base units each is. */
export function unitsFor(countedAs: ShopFood['counted_as']): { name: string; factor: number }[] {
  if (countedAs === 'weight')
    return [
      { name: 'g', factor: 1 },
      { name: 'kg', factor: 1000 }
    ];
  if (countedAs === 'volume')
    return [
      { name: 'ml', factor: 1 },
      { name: 'L', factor: 1000 }
    ];
  return [{ name: 'items', factor: 1 }];
}

/** "Pantry gets 1 pack · 400 g." */
export function pantryGets(count: number, pack: number, countedAs: ShopFood['counted_as']): string {
  const total = baseText(count * pack, countedAs);
  return `Pantry gets ${count} ${plural(count, 'pack', 'packs')} · ${total}.`;
}
