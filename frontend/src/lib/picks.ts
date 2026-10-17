// The ¼ · ½ · ¾ · Full picks for any packet whose size is known, open or not (spec, Part-used packets; cabledrawer's 0.2 hand test: a full pack gets them too): which one
// matches what's left now. It's the packet's amount ÷ its size's amount, to the
// nearest ¼: eggs "9 left · bought as a dozen" are ¾, bread 14 of 20 slices is ¾,
// yoghurt 250 g of a 500 g tub is ½. (Not as_sold.count: for count foods that's
// the number of items.)

import type { Lot } from './client/types';

export const PICKS: readonly { value: number; label: string }[] = [
  { value: 0.25, label: '¼' },
  { value: 0.5, label: '½' },
  { value: 0.75, label: '¾' },
  { value: 1, label: 'Full' }
];

/** The pick for what's left, or undefined when the packet's size isn't known. */
export function pickFor(lot: Pick<Lot, 'stock'>): number | undefined {
  const size = lot.stock.as_sold?.size.amount;
  if (!size || !(lot.stock.amount >= 0)) return undefined;
  const quarters = Math.round((lot.stock.amount / size) * 4) / 4;
  return Math.min(1, Math.max(0.25, quarters));
}
