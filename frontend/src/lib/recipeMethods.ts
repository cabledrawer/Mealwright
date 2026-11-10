// A recipe with two ways of cooking it (M2): the recipe as the server sends it holds the first
// way's lines, steps and time and the second beside them. A screen that shows one way at a time
// (the recipe page, Cook mode) asks for the recipe as that way.

import type { Recipe } from './client/recipes';

/** The recipe with the lines, steps, time and wait of the way `methodId` (the first when it is
 *  null or not the second's). A recipe with one way comes back as it is. */
export function withMethod(recipe: Recipe, methodId: number | null): Recipe {
  const second = recipe.second_method;
  if (!second || methodId !== second.id) return recipe;
  return {
    ...recipe,
    lines: second.lines,
    steps: second.steps,
    time_minutes: second.time_minutes,
    wait: second.wait ?? null
  };
}
