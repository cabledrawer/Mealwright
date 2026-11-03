// One at a time on the phone's Check (F141, cabledrawer 3 Nov): "each line that needs me, then every
// method step (not only long ones)". Pure work on the review, so the order is tested apart from
// the screen. The list is worked out from the review as it stands, so a line or step taken out
// (and put back by Undo), or a step split, changes the list and nothing is skipped.

import type { ImportReview } from './client/imports';

export type WalkItem = { kind: 'line' | 'step'; at: number };

/** A line the Check screen marks "To confirm" or "Needs you": the reader's own label, so choosing
 *  an ingredient for it does not take it out of the walk (a choice can be changed on its card). */
export function needsYou(line: ImportReview['lines'][number]): boolean {
  return line.kind === 'ingredient' && (line.label === 'to_confirm' || line.label === 'needs_you');
}

/** The lines that need the person, in order, then every step in order (headings are not steps:
 *  they show above the steps under them). `at` is the place in the review's own list. */
export function walkItems(review: Pick<ImportReview, 'lines' | 'steps'>): WalkItem[] {
  const items: WalkItem[] = [];
  review.lines.forEach((line, at) => {
    if (needsYou(line)) items.push({ kind: 'line', at });
  });
  review.steps.forEach((step, at) => {
    if (step.kind === 'step') items.push({ kind: 'step', at });
  });
  return items;
}

/** The heading a step sits under (the nearest one above it), or null. */
export function headingAbove(steps: ImportReview['steps'], at: number): string | null {
  for (let i = at - 1; i >= 0; i--) {
    if (steps[i]!.kind === 'heading') return steps[i]!.text;
  }
  return null;
}
