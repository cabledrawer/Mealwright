// Removing an ingredient (cabledrawer 17 Oct, spec section 6): only when nothing depends on
// it. In 0.2 that means none of it in the pantry. Shopping lists (0.3) and recipes
// (0.4) will add their checks here, in this one place.

import type { Food } from './client/types';

/** Whether "Remove from Ingredients" is offered for this ingredient. */
export function canRemove(food: Pick<Food, 'stock'>): boolean {
  return !food.stock || food.stock.amount === 0;
}
