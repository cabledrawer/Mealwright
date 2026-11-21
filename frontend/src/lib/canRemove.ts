// Removing an ingredient (cabledrawer 17 Oct, spec section 6): only when nothing depends on
// it. That means none of it in the pantry, and it isn't a recipe's own made-ahead
// ingredient (cabledrawer 19 Oct). Recipes that use it don't block it: their lines keep
// their words and say "not linked". (The server checks shopping lists itself.)

import type { Food } from './client/types';

/** Whether "Delete from Ingredients" is offered for this ingredient. */
export function canRemove(food: Pick<Food, 'stock'> & Partial<Pick<Food, 'made_by'>>): boolean {
  if (food.made_by) return false;
  return !food.stock || food.stock.amount === 0;
}
