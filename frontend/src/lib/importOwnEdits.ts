// A section as its own recipe on Check (F190, cabledrawer 8 Nov): make a heading's section its own
// recipe, change it, or keep it in the recipe again, with an Undo (toast and Ctrl+Z) for each. The
// change lives on the heading line of the review itself, so a draft keeps it and Save sends it.
// Loaded when first asked for, so the Check page does not grow for it.
import type { ImportFlow } from './import.svelte';
import type { Choice } from './import.svelte';
import type { OwnRecipe, ReviewLine } from './client/imports';
import { sectionOf } from './importOwn';
import { undoHistory, type UndoEntry } from './undo.svelte';

/** A heading as it reads in a toast: cut at 40 characters, at a word where it can. */
function shorter(text: string): string {
  const one = text.replace(/\s+/g, ' ').trim();
  if (one.length <= 40) return one;
  return `${(one.slice(0, 40).replace(/\s+\S*$/, '') || one.slice(0, 40)).trimEnd()}…`;
}

/** Said when an Undo finds its heading gone (proposed, for cabledrawer). */
export const CANT_PUT_BACK_OWN = 'Couldn’t put it back: the section has changed.';

/** The choice a line had before it became the stand-in for a section made its own recipe, kept
 *  by the heading's line so "Keep in this recipe" (and Undo) can put it back exactly. */
interface Held {
  line: ReviewLine;
  choice: Choice;
  from: number | null;
}
const held = new WeakMap<ReviewLine, Held>();

function set(flow: ImportFlow, heading: number, own: OwnRecipe | null, label: string): boolean {
  const review = flow.review;
  const line = review?.lines[heading];
  if (!review || !line || line.kind !== 'heading') return false;
  const before = line.own ?? null;
  line.own = own;
  flow.saveProblem = null;
  // The line that stands for the section shows and sends the new recipe, never an older choice:
  // its choice is set aside while the section is its own recipe, and given back after.
  const heldBefore = held.get(line);
  const changed: Held[] = []; // lines whose choice this change moved, for the Undo
  const give = (h: Held) => {
    const at = review.lines.indexOf(h.line);
    if (at < 0 || flow.choices[at]) return;
    flow.choose(at, h.choice);
    if (h.from !== null) flow.sharedFrom = { ...flow.sharedFrom, [at]: h.from };
  };
  if (heldBefore) {
    give(heldBefore);
    held.delete(line);
  }
  const use = own ? sectionOf(review, heading, own.name).use : null;
  if (use !== null && flow.choices[use]) {
    const h: Held = {
      line: review.lines[use]!,
      choice: flow.choices[use]!,
      from: flow.sharedFrom[use] ?? null
    };
    held.set(line, h);
    flow.unchoose(use);
    changed.push(h);
  }
  const entry: UndoEntry = {
    label,
    undo: () => {
      if (flow.review !== review || !review.lines.includes(line)) return CANT_PUT_BACK_OWN;
      line.own = before;
      // Choices go back as they were: the one this change set aside comes back, and the one it
      // gave back is set aside again.
      held.delete(line);
      for (const h of changed) give(h);
      if (heldBefore) {
        const at = review.lines.indexOf(heldBefore.line);
        if (at >= 0) flow.unchoose(at);
        held.set(line, heldBefore);
      }
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
