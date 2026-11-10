// Check screen, F111 (spec "Import Check (PR A4)"): change a step's text, or take a step or a
// heading out, before anything is saved. The edits are made on the review's own steps, so Save
// (and Save as a draft) send them. Kept apart from the flow and loaded only when first asked for,
// so the page's size does not grow for it.
import type { ImportFlow } from './import.svelte';
import type { ReviewStep } from './client/imports';
import { stepNumberAt } from './importSteps';
export { activeTime } from './timeWords';
import { undoHistory, type UndoEntry } from './undo.svelte';

/** A heading as it reads in a toast: cut at 40 characters, at a word where it can. */
function shorter(text: string): string {
  const one = text.replace(/\s+/g, ' ').trim();
  if (one.length <= 40) return one;
  return `${(one.slice(0, 40).replace(/\s+\S*$/, '') || one.slice(0, 40)).trimEnd()}…`;
}

type Step = { kind: 'step' | 'heading'; text: string; optional?: boolean };

/** Change the text of `step` (the step itself, not its place: the list may have moved while the
 *  box was open). False when the text is empty (an empty step can't be kept: the caller says so
 *  and offers Remove) or the step is no longer in the list. The words are tidied at the ends only. */
export function changeStep(
  flow: ImportFlow,
  step: Step,
  text: string,
  optional?: boolean
): boolean {
  const words = text.trim();
  if (!words || !flow.review?.steps.includes(step)) return false;
  step.text = words;
  if (optional !== undefined && step.kind === 'step') step.optional = optional;
  flow.previewStep = null; // the split preview was of the old words
  return true;
}

/** Take the step or heading at `at` out, with an Undo (toast and Ctrl+Z) that puts it back where
 *  it was. It is found again by its neighbours, not by number: other steps may have moved since.
 *  When neither neighbour is there any more (Put the steps back as they were), nothing is put
 *  back: the Undo says so rather than guess a place. */
export function removeStep(flow: ImportFlow, at: number): void {
  const review = flow.review;
  const gone = review?.steps[at];
  if (!review || !gone) return;
  const number = stepNumberAt(review.steps, at);
  const label = number === null ? `Removed “${shorter(gone.text)}”` : `Removed step ${number}`;
  const before = review.steps[at - 1];
  const after = review.steps[at + 1];
  review.steps.splice(at, 1);
  flow.previewStep = null; // its number was an index into the steps that were
  reworkMinutes(flow); // a wait on it no longer comes off the page's total
  const entry: UndoEntry = {
    label,
    undo: () => {
      const now = flow.review?.steps;
      if (flow.review !== review || !now) return false; // another recipe is on the screen now
      const behind = before ? now.indexOf(before) : -1;
      const ahead = after ? now.indexOf(after) : -1;
      let place: number;
      if (behind >= 0) place = behind + 1;
      else if (!before)
        place = 0; // it was first
      else if (ahead >= 0) place = ahead;
      else if (!after)
        place = now.length; // it was last
      else return CANT_PUT_BACK;
      now.splice(place, 0, gone);
      flow.previewStep = null;
      reworkMinutes(flow);
    }
  };
  flow.keepStepUndo(entry);
  undoHistory.record(entry);
}

/** Said when an Undo finds neither of the step's neighbours (proposed, for cabledrawer). */
export const CANT_PUT_BACK = 'Couldn’t put it back: the steps have changed.';

/** Work the Minutes box out again from the page's own total and the waits the steps have now
 *  (M1 fix: "No wait" gives the minutes back). Leaves it alone once it was typed in, or when the
 *  page gave no total. */
export function reworkMinutes(flow: ImportFlow): void {
  flow.reworkMinutes();
}

/** "Yes, it waits": the suggested wait on `step` is kept as it is (M1). */
export function confirmWait(flow: ImportFlow, step: ReviewStep): void {
  step.wait_confirmed = true;
  reworkMinutes(flow);
}

/** "No wait": take the wait off `step`, with an Undo (toast and Ctrl+Z) that puts it back as it
 *  was, confirmed or not (M1; the words are proposed, for cabledrawer). */
export function takeOffWait(flow: ImportFlow, step: ReviewStep): void {
  const was = step.wait;
  const confirmed = step.wait_confirmed;
  if (!was) return;
  step.wait = null;
  step.wait_confirmed = false;
  reworkMinutes(flow);
  const entry: UndoEntry = {
    label: 'Took off the wait',
    undo: () => {
      if (!flow.review?.steps.includes(step)) return CANT_PUT_BACK;
      step.wait = was;
      step.wait_confirmed = confirmed;
      reworkMinutes(flow); // the minutes it gave back are taken again
    }
  };
  undoHistory.record(entry);
}
