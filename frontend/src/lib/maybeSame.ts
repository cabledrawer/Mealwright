// "Maybe the same" pairs (spec "Decided for 0.2"). Each pair shows once, on the food
// that would be merged away, as in the mockup: "Drumsticks (moringa): Maybe the same as
// 'Drumsticks' · Merge". The server says which way each merge goes (`merge_this`), so
// every app does the same.

import type { MaybeSame, Ref } from './client/types';

/** The food this one would merge into, if it's the side of a pair that goes. */
export function mergeTarget(food: Ref & { maybe_same: MaybeSame[] }): MaybeSame | undefined {
  return food.maybe_same.find((other) => other.merge_this);
}
