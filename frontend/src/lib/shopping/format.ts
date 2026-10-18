// Amount wording for the pack sheet: base amounts (g, ml, items) in plain words.

import type { ShopFood } from './types';

const NBSP = '\u00a0';
const trim = (n: number) => String(Math.round(n * 100) / 100).replace(/\.0+$/, '');

export function baseText(amount: number, countedAs: ShopFood['counted_as']): string {
  if (countedAs === 'weight')
    return amount >= 1000 ? `${trim(amount / 1000)}${NBSP}kg` : `${trim(amount)}${NBSP}g`;
  if (countedAs === 'volume')
    return amount >= 1000 ? `${trim(amount / 1000)}${NBSP}L` : `${trim(amount)}${NBSP}ml`;
  return trim(amount);
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
  return `Pantry gets ${count} ${count === 1 ? 'pack' : 'packs'} · ${total}.`;
}
