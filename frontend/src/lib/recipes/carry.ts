// The editor's unsaved boxes, kept in the tab so a reload or an accidental close doesn't lose
// them (cabledrawer 28 Oct: "Carrying on where you left off"). sessionStorage only: it dies with the
// tab and never leaves the browser. Every call works without it (private windows, blocked
// storage): the editor then just doesn't carry on.

import type { Carried } from './draft.svelte';

const PREFIX = 'mw.recipeDraft.';

/** What the tab kept for this editor (a key from `editorKey`), or null. */
export function readCarried(key: string): unknown {
  try {
    const text = sessionStorage.getItem(PREFIX + key);
    return text ? JSON.parse(text) : null;
  } catch {
    return null;
  }
}

export function writeCarried(key: string, value: Carried): void {
  try {
    sessionStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // Full or blocked: the editor carries on without it.
  }
}

export function clearCarried(key: string): void {
  try {
    sessionStorage.removeItem(PREFIX + key);
  } catch {
    // Nothing to clear if the tab can't keep anything.
  }
}
