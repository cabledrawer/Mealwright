// Check screen, F111 (spec "Import Check (PR A4)"): change a step's text, or take a step or a
// heading out, before anything is saved. The edits are made on the review's own steps, so Save
// (and Save as a draft) send them. Kept apart from the flow and loaded only when first asked for,
// so the page's size does not grow for it.
import type { ImportFlow } from './import.svelte';
import { stepNumberAt } from './importSteps';
import { undoHistory, type UndoEntry } from './undo.svelte';

/** A heading as it reads in a toast: cut at 40 characters, at a word where it can. */
function shorter(text: string): string {
  const one = text.replace(/\s+/g, ' ').trim();
  if (one.length <= 40) return one;
  return `${(one.slice(0, 40).replace(/\s+\S*$/, '') || one.slice(0, 40)).trimEnd()}…`;
}

/** Change the text of the step or heading at `at`. False when the text is empty (an empty step
 *  can't be kept: the caller says so and offers Remove). The words are tidied at the ends only. */
export function changeStep(flow: ImportFlow, at: number, text: string): boolean {
  const step = flow.review?.steps[at];
  const words = text.trim();
  if (!step) return false;
  if (!words) return false;
  step.text = words;
  flow.previewStep = null; // the split preview was of the old words
  return true;
}

/** Take the step or heading at `at` out, with an Undo (toast and Ctrl+Z) that puts it back where
 *  it was. It is found again by itself, not by number: other steps may have moved since. */
export function removeStep(flow: ImportFlow, at: number): void {
  const review = flow.review;
  const gone = review?.steps[at];
  if (!review || !gone) return;
  const number = stepNumberAt(review.steps, at);
  const label = number === null ? `Removed “${shorter(gone.text)}”` : `Removed step ${number}`;
  const after = review.steps[at + 1];
  review.steps.splice(at, 1);
  flow.previewStep = null; // its number was an index into the steps that were
  const entry: UndoEntry = {
    label,
    undo: () => {
      const now = flow.review?.steps;
      if (flow.review !== review || !now) return false; // another recipe is on the screen now
      const next = after ? now.indexOf(after) : now.length;
      now.splice(next >= 0 ? next : Math.min(at, now.length), 0, gone);
      flow.previewStep = null;
    }
  };
  flow.keepUndo(entry);
  undoHistory.record(entry);
}
