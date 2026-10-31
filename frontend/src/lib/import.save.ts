// After a Save: the toast that says what was imported, with the one Undo that takes the whole
// save back (the recipe, its new ingredients and the other names it learned). If the recipe was
// saved from a draft, that Undo brings the draft back too (spec section 6, question 36); the
// Drafts store fetches its list again after any Undo of an import (`drafts.svelte.ts`).

import { serverUndo } from './client/changes';
import type { Saved } from './client/imports';
import { kitchen } from './freshness.svelte';
import { undoHistory } from './undo.svelte';

export function changesToast(saved: Saved): void {
  kitchen.changed();
  undoHistory.record({
    label: saved.change.summary,
    needsServer: true,
    undo: serverUndo(saved.change.id)
  });
}
