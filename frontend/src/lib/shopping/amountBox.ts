// The amount box on a shopping row (mockups ShopRows-*, cabledrawer 20 Oct): a box that holds the
// line's real amount, − / + beside it, and a unit choice. This file is the sums behind it:
// which units to offer, what to show for an amount, what − and + do, and how a changed unit
// keeps the same amount. Only conversions a phone can do offline (g/kg, ml/L and the
// ingredient's own sizes), the same as amountEdit.ts, which does the final reading.

import { baseText } from './format';
import { toBaseAmount, type EditFood, type Parsed } from './amountEdit';
import type { FoodSize, ListItem, ShopFood } from './types';

export interface UnitChoice {
  /** "g", "kg", "count" or "size:12". */
  key: string;
  /** What the choice says: "g", "packet (500 g)". */
  label: string;
  /** The unit as toBaseAmount reads it. Empty for a bare count. */
  text: string;
  /** How many base units (g, ml or items) one of it is. */
  factor: number;
  sizeId: number | null;
  /** How far − and + move the number. */
  step: number;
}

/** The units on offer for an ingredient: its base units, then its own sizes. */
export function unitChoices(food: Pick<ShopFood, 'counted_as'>, sizes: FoodSize[]): UnitChoice[] {
  const out: UnitChoice[] = [];
  if (food.counted_as === 'weight') {
    out.push({ key: 'g', label: 'g', text: 'g', factor: 1, sizeId: null, step: 50 });
    out.push({ key: 'kg', label: 'kg', text: 'kg', factor: 1000, sizeId: null, step: 0.5 });
  } else if (food.counted_as === 'volume') {
    out.push({ key: 'ml', label: 'ml', text: 'ml', factor: 1, sizeId: null, step: 50 });
    out.push({ key: 'l', label: 'L', text: 'l', factor: 1000, sizeId: null, step: 0.5 });
  } else {
    out.push({ key: 'count', label: 'items', text: '', factor: 1, sizeId: null, step: 1 });
  }
  for (const size of sizes) {
    out.push({
      key: `size:${size.id}`,
      label: `${size.name} (${baseText(size.amount, food.counted_as)})`,
      text: size.name,
      factor: size.amount,
      sizeId: size.id,
      step: food.counted_as === 'count' ? 1 : 0.5
    });
  }
  return out;
}

/** A number as people write it: no trailing zeros, at most three decimals. */
export const numberText = (n: number): string => String(Math.round(n * 1000) / 1000);

export interface Draft {
  text: string;
  unit: string;
}

/** What the box shows when it opens: the line's amount, in the unit it was written in. */
export function startDraft(
  item: Pick<ListItem, 'amount' | 'size_id'>,
  food: Pick<ShopFood, 'counted_as'>,
  choices: UnitChoice[]
): Draft {
  const first = choices[0]!;
  const amount = item.amount;
  if (!amount || amount <= 0) {
    // Nothing yet: the usual size is the natural unit, as a bare number would be read.
    const usual = food.counted_as === 'count' ? undefined : choices.find((c) => c.sizeId !== null);
    return { text: '', unit: (usual ?? first).key };
  }
  const size = choices.find((c) => c.sizeId !== null && c.sizeId === item.size_id);
  if (size) {
    const ratio = amount / size.factor;
    // Whole and half packets read well; a strange ratio is better shown in g, ml or items.
    if (Math.abs(ratio * 100 - Math.round(ratio * 100)) < 1e-6) {
      return { text: numberText(ratio), unit: size.key };
    }
  }
  const big = choices.find((c) => c.factor === 1000 && c.sizeId === null);
  if (big && amount >= 1000 && amount % 1000 === 0) {
    return { text: numberText(amount / 1000), unit: big.key };
  }
  return { text: numberText(amount), unit: first.key };
}

/** The draft as an amount to send, or what is wrong with it, in words. */
export function readDraft(draft: Draft, choices: UnitChoice[], food: EditFood): Parsed {
  const choice = choices.find((c) => c.key === draft.unit) ?? choices[0]!;
  return toBaseAmount(`${draft.text} ${choice.text}`.trim(), food);
}

/** The same amount in another unit: 500 g becomes 0.5 kg or 1 packet. */
export function switchUnit(draft: Draft, to: string, choices: UnitChoice[], food: EditFood): Draft {
  const target = choices.find((c) => c.key === to);
  if (!target || to === draft.unit) return { ...draft, unit: to };
  if (!draft.text.trim()) return { text: '', unit: to };
  const read = readDraft(draft, choices, food);
  if ('problem' in read) return { ...draft, unit: to };
  return { text: numberText(read.amount / target.factor), unit: to };
}

/** − and +: one step in the chosen unit; never to zero or below. */
export function stepDraft(
  draft: Draft,
  direction: 1 | -1,
  choices: UnitChoice[],
  food: EditFood
): Draft {
  const choice = choices.find((c) => c.key === draft.unit) ?? choices[0]!;
  const read = draft.text.trim() ? readDraft(draft, choices, food) : null;
  const now = read && !('problem' in read) ? read.amount / choice.factor : 0;
  const next = Math.round((now + direction * choice.step) * 1000) / 1000;
  if (!(next > 0)) return draft;
  return { ...draft, text: numberText(next) };
}
