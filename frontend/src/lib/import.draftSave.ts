// "Save recipe" on a draft whose ingredients are all checked (mockups Drafts05-Phone and
// Drafts05-Desktop): the recipe is made from the draft exactly as Save on the review makes it
// (one Undo in Recent changes), and the draft goes with it. A draft with a line that still needs
// a choice is never saved from the list: "Carry on" is how to finish it.

import { ApiError } from './api';
import { getDraft } from './client/drafts';
import { ImportFlow } from './import.svelte';
import type { Saved } from './client/imports';
import { changesToast } from './import.save';

export const NEEDS_YOU = 'That draft has ingredients that still need you. Carry on to finish it.';

/** The new recipe's id (and what the save said), or the sentence to show on the draft's row.
 *  `quiet`: no toast of its own, for a caller that saves several and says it once (quick import,
 *  F216). */
export async function saveFromDraft(
  id: number,
  options: { quiet?: boolean } = {}
): Promise<{ recipeId: number; saved: Saved } | { problem: string }> {
  try {
    const flow = new ImportFlow();
    flow.load(await getDraft(id));
    if (flow.unlinked > 0) return { problem: NEEDS_YOU };
    const saved = await flow.save();
    if (!saved) return { problem: flow.saveProblem?.message ?? 'Couldn’t save. Try again.' };
    if (!options.quiet) changesToast(saved);
    return { recipeId: saved.recipe.id, saved };
  } catch (error) {
    return { problem: error instanceof ApiError ? error.detail : 'Couldn’t save. Try again.' };
  }
}
