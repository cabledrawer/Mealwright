// After a Save: the toast that says what was imported, with the one Undo that takes the whole
// save back (the recipe, its new ingredients and the other names it learned). If the recipe was
// saved from a draft, that Undo brings the draft back too (cabledrawer 24 Oct, question 36), so the
// Drafts list and its count are fetched again.

import { serverUndo } from './client/changes';
import type { Saved } from './client/imports';
import { drafts } from './drafts.svelte';
import { kitchen } from './freshness.svelte';
import { undoHistory } from './undo.svelte';

export function changesToast(saved: Saved): void {
  kitchen.changed();
  undoHistory.record({
    label: saved.change.summary,
    undo: serverUndo(saved.change.id, () => {
      if (drafts.loaded) void drafts.load();
    })
  });
}
