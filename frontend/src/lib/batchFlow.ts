// "Plan this batch" asks, for each recipe, what adding it to the plan asks (RF3, C6; cabledrawer
// 11 Nov: "which optional ingredients and, for two methods, which method, as adding to the plan
// does, the one used last pre-picked") before that recipe's Cook once sheet. These are the
// parts of that flow that need no screen, so they are tested on their own.

import type { BatchBody } from './client/plan';

/** What one recipe was asked: the way of cooking it, and the optional lines it will use. A key is
 * left out when there was nothing to ask (a recipe with one way, or no optional ingredient). */
export interface Picked {
  method_id?: number;
  optional_use?: number[];
}

/** The two questions, as the Plan asks them (`methodAsk.ask`, `optionalAsk.ask`): each resolves
 * with the answer, null when the person cancels and undefined when there is nothing to ask. */
export interface Asks {
  method: (recipeId: number, where: string) => Promise<number | null | undefined>;
  optional: (
    recipeId: number,
    where: string,
    method: number | undefined
  ) => Promise<number[] | null | undefined>;
}

/** Ask about one recipe: the way first, then the optional ingredients of that way (as adding to
 * the plan does). Null: the person cancelled, so nothing is planned. */
export async function askPicks(
  recipeId: number,
  where: string,
  asks: Asks
): Promise<Picked | null> {
  const method = await asks.method(recipeId, where);
  if (method === null) return null;
  const use = await asks.optional(recipeId, where, method);
  if (use === null) return null;
  return {
    ...(method === undefined ? {} : { method_id: method }),
    ...(use === undefined ? {} : { optional_use: use })
  };
}

/** The flow's state: which recipe's sheet is on show, the Cook once answers so far and each
 * recipe's picks. */
export interface Flow {
  at: number;
  bodies: BatchBody[];
  picked: Picked[];
}

/** After a Plan this batch that was refused (no connection, the meal is full…): the last sheet
 * is offered again with every earlier answer kept, so nothing is asked twice (H10). */
export function reopenLast(bodies: BatchBody[], picked: Picked[]): Flow {
  return { at: bodies.length - 1, bodies: bodies.slice(0, -1), picked };
}
