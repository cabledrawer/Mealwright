// A cancelled editor, kept in memory so "Changes not saved · Undo" can open it again exactly as
// it was (cabledrawer 19 Oct). Only while the page stays open: nothing is written anywhere.

import type { RecipeDraft } from './draft.svelte';

let kept: { key: string; draft: RecipeDraft } | null = null;
let reopening: string | null = null;

/** Which editor: a new recipe, or the one being edited. */
export const editorKey = (id: number | null) => (id === null ? 'new' : `edit:${id}`);

export function keep(key: string, draft: RecipeDraft): void {
  kept = { key, draft };
}

/** Undo was pressed: the next editor opened for this key takes what was kept. */
export function reopen(key: string): boolean {
  if (kept?.key !== key) return false;
  reopening = key;
  return true;
}

/** What the editor for `key` should start from, if it is being reopened. */
export function claim(key: string): RecipeDraft | null {
  if (!kept || kept.key !== key || reopening !== key) return null;
  const draft = kept.draft;
  kept = null;
  reopening = null;
  return draft;
}
