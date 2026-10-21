// Where a ticked line went, in the three ways it can (cabledrawer 20 Oct, hand test, option A):
//  - with an amount: it went into the pantry ("In the Fridge · 2 L");
//  - with no amount: nothing went in yet ("Not in the pantry yet. No amount.");
//  - a staple: it is "restocked", and a staple's amount isn't counted.
// The row's status line and the tick's toast both read it from here, so they always agree.

import type { ListItem, ShopFood, Tick } from './types';

export type PutAway =
  { kind: 'amount'; place: string | null; amount: string } | { kind: 'none' } | { kind: 'staple' };

/**
 * `tick` is the line's standing tick, if the copy has it yet. A tick this phone has made but
 * the server hasn't answered (`waiting`) has no amount of its own yet: the line's amount is
 * what will go in, so the row says that meanwhile. Once the server has answered, only what
 * it really put in counts (a change of the line's amount after the tick puts nothing in).
 */
export function putAwayState(
  item: Pick<ListItem, 'amount' | 'display'>,
  food: Pick<ShopFood, 'staple'>,
  tick: Pick<Tick, 'bought'> | undefined,
  waiting: boolean,
  place: string | null
): PutAway {
  if (food.staple) return { kind: 'staple' };
  if (tick?.bought) {
    const amount = tick.bought.display || item.display;
    if (amount) return { kind: 'amount', place, amount };
  }
  if ((waiting || !tick) && item.amount && item.display) {
    return { kind: 'amount', place, amount: item.display };
  }
  return { kind: 'none' };
}

/** The status line's words. */
export function putAwayWords(state: PutAway): string {
  if (state.kind === 'staple') return 'Restocked · staples aren’t counted';
  if (state.kind === 'none') return 'Not in the pantry yet. No amount.';
  const where = state.place ? `In the ${state.place}` : 'In the pantry';
  return `${where} · ${state.amount}`;
}
