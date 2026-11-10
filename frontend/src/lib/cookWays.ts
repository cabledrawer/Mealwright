// Two ways of cooking it, in Cook mode (M2): telling the meal which way was cooked, so the list,
// Can cook now and Cooked it follow it. Kept apart from the Cook page and loaded when a recipe
// with two ways is cooked (the size limit).

import { newChangeId } from './changeId';
import { setPlanMethod } from './client/plan';
import { network } from './network.svelte';

/** The meal's item (a recipe in a planned meal) is set to the way `id` unless it already is.
 *  False when it couldn't be (offline, or the server said no): the caller says so. */
export async function setMealWay(
  item: { id: number; method_id?: number | null },
  id: number
): Promise<boolean> {
  if (item.method_id === id) return true;
  if (network.offline) return false;
  try {
    await setPlanMethod(item.id, id, newChangeId());
    return true;
  } catch {
    return false;
  }
}
