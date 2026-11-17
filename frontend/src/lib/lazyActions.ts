// Two actions that fetch their code the first time they are used, lifted out of their screens
// so a test can reach them (B7 follow-up to the B4 failed-load work, PR 252 review). When the
// fetch fails the toast shows (fetchCode) and the action ends with nothing changed.

import type { PlanItem } from './client/plan';
import { fetchCode } from './lazyCode.svelte';
import { loaders } from './lazyModules';

/**
 * Cook mode moved past the step that waits: mark the wait as begun, then fetch the plan again.
 * Nothing happens for an item with no wait or while offline; nothing is marked when the code
 * fails to load (the next step past the wait tries again).
 */
export async function markWaitBegun(
  item: PlanItem | null,
  offline: boolean,
  reload: () => Promise<unknown>
): Promise<void> {
  if (!item?.ahead || offline) return;
  const loaded = await fetchCode(loaders.startNow);
  if (!loaded) return;
  await loaded.markStarted(item.id, item.recipe?.name ?? 'it', { withUndo: false });
  await reload();
}

/**
 * The Batch cook way-of-cooking question. When its code fails to load this answers null, as if
 * cancelled: nothing is planned.
 */
export async function askBatchMethod(
  id: number,
  where: string
): Promise<number | null | undefined> {
  const loaded = await fetchCode(loaders.methodAsk);
  if (!loaded) return null;
  return loaded.methodAsk.ask({ id }, where, { button: 'Next' });
}
