// After a Save: the toast that says what was imported, with the one Undo that takes the whole
// save back (the recipe, its new ingredients and the other names it learned).

import { serverUndo } from './client/changes';
import type { Saved } from './client/imports';
import { kitchen } from './freshness.svelte';
import { undoHistory } from './undo.svelte';

export function changesToast(saved: Saved): void {
  kitchen.changed();
  undoHistory.record({ label: saved.change.summary, undo: serverUndo(saved.change.id) });
}
