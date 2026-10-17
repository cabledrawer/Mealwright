// "Maybe the same" pairs (spec "Decided for 0.2"). Each pair shows once, on the food
// that would be merged away, as in the mockup: "Drumsticks (moringa): Maybe the same as
// 'Drumsticks' · Merge". The API lists a pair on both foods without saying which side
// goes, so the app decides: the longer, more particular name is merged into the
// shorter one (its name then becomes an other name, so nothing is lost); on a tie, the
// newer food goes.

import type { Ref } from './client/types';

/** Whether `food` is the one to merge away from the pair with `other`. */
export function goesInto(food: Ref, other: Ref): boolean {
  if (food.name.length !== other.name.length) return food.name.length > other.name.length;
  return food.id > other.id;
}

/** The food this one would merge into, if it's the side of a pair that goes. */
export function mergeTarget(food: Ref & { maybe_same: Ref[] }): Ref | undefined {
  return food.maybe_same.find((other) => goesInto(food, other));
}
