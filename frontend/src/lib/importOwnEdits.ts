// A section as its own recipe on Check (F190, cabledrawer 8 Nov): make a heading's section its own
// recipe, change it, or keep it in the recipe again, with an Undo (toast and Ctrl+Z) for each. The
// change lives on the heading line of the review itself, so a draft keeps it and Save sends it.
// Loaded when first asked for, so the Check page does not grow for it.
import type { ImportFlow } from './import.svelte';
import type { OwnRecipe } from './client/imports';
import { undoHistory, type UndoEntry } from './undo.svelte';

/** A heading as it reads in a toast: cut at 40 characters, at a word where it can. */
function shorter(text: string): string {
  const one = text.replace(/\s+/g, ' ').trim();
  if (one.length <= 40) return one;
  return `${(one.slice(0, 40).replace(/\s+\S*$/, '') || one.slice(0, 40)).trimEnd()}…`;
}

/** Said when an Undo finds its heading gone (proposed, for cabledrawer). */
export const CANT_PUT_BACK_OWN = 'Couldn’t put it back: the section has changed.';

function set(flow: ImportFlow, heading: number, own: OwnRecipe | null, label: string): boolean {
  const review = flow.review;
  const line = review?.lines[heading];
  if (!review || !line || line.kind !== 'heading') return false;
  const before = line.own ?? null;
  line.own = own;
  flow.saveProblem = null;
  const entry: UndoEntry = {
    label,
    undo: () => {
      if (flow.review !== review || !review.lines.includes(line)) return CANT_PUT_BACK_OWN;
      line.own = before;
      flow.saveProblem = null;
    }
  };
  flow.keepLineUndo(entry);
  undoHistory.record(entry);
  return true;
}

/** Make the section under the heading at `heading` its own recipe (or change what it says). */
export function makeOwn(flow: ImportFlow, heading: number, own: OwnRecipe): boolean {
  const line = flow.review?.lines[heading];
  if (!line) return false;
  const words = shorter(line.words);
  return set(
    flow,
    heading,
    own,
    line.own ? `Changed the recipe made from “${words}”` : `Made “${words}” its own recipe`
  );
}

/** Keep the section in this recipe again. */
export function keepInMain(flow: ImportFlow, heading: number): boolean {
  const line = flow.review?.lines[heading];
  if (!line?.own) return false;
  return set(flow, heading, null, `Kept “${shorter(line.words)}” in this recipe`);
}
