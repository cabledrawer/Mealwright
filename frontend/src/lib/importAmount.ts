import { readNumber } from './amountText.js';

// Reading the amount someone types into a line on the Check screen ("2", "½", "1½", "1 1/2",
// "0,5"). The unit has its own box, so this is only the number. Empty is no amount.

/** The most an amount box takes; the server's own limit is higher. */
const MOST = 100_000;

/** `{ amount }` (null for an empty box), or null when the box holds something that isn't a
 *  number above nothing. */
export function readAmount(text: string): { amount: number | null } | null {
  const typed = text.trim();
  if (typed === '') return { amount: null };
  const amount = readNumber(typed);
  if (amount === null || amount > MOST) return null;
  return { amount: Math.round(amount * 1000) / 1000 };
}
