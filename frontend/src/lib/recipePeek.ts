// A recipe's page shows its name, picture and time at once when it is opened from a list that
// already has them (0.9.5 speed work; proposed, for cabledrawer): the list's row is kept here for
// the moment between the tap and the server's answer. The rest of the page (ingredients, steps,
// what is in stock) follows when the answer comes. The row is only ever shown for its own
// recipe, and never in place of an answer: when the recipe has arrived, or is not found, or
// can't be reached, the page says so as before.

import type { RecipeRow } from './client/recipes';

let held: RecipeRow | null = null;

export const recipePeek = {
  /** Keep a list row that is about to be opened. */
  hold(row: RecipeRow): void {
    held = row;
  },
  /** The row held for this recipe, or null (another recipe's row is never given). */
  of(id: number): RecipeRow | null {
    return held !== null && held.id === id ? held : null;
  },
  forget(): void {
    held = null;
  }
};
