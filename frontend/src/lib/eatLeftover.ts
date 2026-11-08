// F65, "Eat it on…" in "Any left over?" (on the Plan and on Today): after "Cooked it" made the
// tubs, the first of them goes on the meal that was picked. The answer doesn't name the tubs, so
// they are the newest of that recipe cooked that day.
//
// It is part of "Cooked it": no toast of its own, and the Undo of "Cooked it" takes the placement
// back first (a tub in a meal can't be taken back until it is out of it), then the cook.

import { ApiError } from './api';
import { newChangeId } from './changeId';
import { serverUndo } from './client/changes';
import { getTubsLeft, placeTub } from './client/plan';
import { kitchen } from './freshness.svelte';
import { toasts } from './toast.svelte';

/** What takes the placement back; null until there is one. Shared by the Undo and the placing. */
export interface Placed {
  undo: (() => Promise<string | void>) | null;
}

export async function eatLeftover(
  placed: Placed,
  recipeName: string,
  cookedOn: string,
  count: number,
  to: { day: string; slotId: number }
): Promise<void> {
  try {
    const left = await getTubsLeft();
    const made = left.tubs
      .filter((t) => t.recipe_name === recipeName && t.cooked_on === cookedOn)
      .sort((a, b) => b.id - a.id)
      .slice(0, count);
    const tub = made.at(-1);
    if (!tub) return;
    // A tub another phone has put in a meal meanwhile is refused (409 tub_taken), not moved.
    const written = await placeTub(
      tub.id,
      { date: to.day, slot_id: to.slotId },
      newChangeId(),
      true
    );
    if (written.change?.can_undo) placed.undo = serverUndo(written.change.id);
    kitchen.changed();
  } catch (error) {
    // The tub stays in Tubs left, where it was made; the server's words say why, after saying
    // plainly that Cooked it itself is saved (F128). A server that can't be reached has its own
    // message everywhere else, so nothing is added to it here.
    if (error instanceof ApiError) toasts.show(refusedWords(error.detail), { tone: 'problem' });
  }
}

/** Proposed, for cabledrawer (F128): the cooking stands; only the tub's meal was refused. */
export function refusedWords(reason: string): string {
  return `Cooked it is saved, but the tub isn’t planned. ${reason} It stays in Tubs left.`;
}
