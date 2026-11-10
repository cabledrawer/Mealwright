// "Done already" and Cook mode past the step that waits (M3, F124): the recipe's long wait is
// begun now. What this records is the moment, so Cook mode on the next day starts after that step
// and says how long it has waited; nothing else changes (no pantry, no shopping). It is offered
// for Undo like any change to the plan. Online only, like the Plan.

import { serverUndo } from './client/changes';
import { setPlanStarted } from './client/plan';
import { kitchen } from './freshness.svelte';
import { save, type Outcome } from './save';
import type { PlanWrite } from './client/plan';

/** The words of the toast ("Marked Masala dosa as started"). */
export const startedWords = (name: string) => `Marked ${name} as started`;

/**
 * Mark the plan item's wait as begun. `withUndo: false` is for Cook mode, which offers no Undo:
 * the person only moved to the next step (a failure is still said, as every failed save is).
 * Resolves with the outcome; nothing is shown on screen before the server answers (the caller
 * fetches the plan again).
 */
export function markStarted(
  itemId: number,
  name: string,
  options: { withUndo?: boolean } = {}
): Promise<Outcome<PlanWrite>> {
  let undoer: (() => Promise<string | void>) | null = null;
  return save<PlanWrite>({
    apply: () => {},
    rollback: () => {},
    send: (key) => setPlanStarted(itemId, true, key),
    saved: () => kitchen.changed(),
    undo:
      options.withUndo === false
        ? undefined
        : {
            label: startedWords(name),
            labelFrom: () => startedWords(name),
            skip: (value) => value.change === null,
            run: (value) => {
              const change = value.change;
              if (!change?.can_undo) return false;
              undoer ??= serverUndo(change.id);
              return undoer();
            }
          }
  });
}
