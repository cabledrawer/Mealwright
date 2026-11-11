// The words on the Drafts screen (spec "Drafts (cabledrawer 21 Oct)", mockups Drafts05-Phone and
// Drafts05-Desktop): where a draft came from, how many days it has left, how far the checking
// has got. One place, so the phone's rows and the computer's table say the same thing.

import type { DraftBrief } from './client/drafts';

/** "bbcgoodfood.com", or "Pasted text". */
export function fromWords(draft: Pick<DraftBrief, 'source'>): string {
  if (draft.source.kind === 'text') return 'Pasted text';
  return draft.source.site ?? 'A link';
}

/** The phone's line under the name: "From bbcgoodfood.com · started by Tess" and
 *  "Pasted text · started by Wren" (the mockup's own words). */
export function phoneSource(draft: DraftBrief): string {
  const from = draft.source.kind === 'text' ? 'Pasted text' : `From ${fromWords(draft)}`;
  return `${from} · started by ${draft.started_by}`;
}

/** "13 days left" (a phone), "13 days" (a computer's column), "1 day left". */
export function daysWords(days: number, left = true): string {
  const count = `${days} ${days === 1 ? 'day' : 'days'}`;
  return left ? `${count} left` : count;
}

/** A draft with 3 days or fewer to go is in the warning colour (mockup: "3 days left"). */
export const RUNNING_OUT = 3;

/** How many ingredient lines still need a choice. */
export function needYou(draft: Pick<DraftBrief, 'lines_total' | 'lines_checked'>): number {
  return Math.max(0, draft.lines_total - draft.lines_checked);
}

/** Nothing is left to check (a draft with no ingredient lines has nothing to save). */
export function allChecked(draft: Pick<DraftBrief, 'lines_total' | 'lines_checked'>): boolean {
  return draft.lines_total > 0 && needYou(draft) === 0;
}

/** "6 of 9 ingredients checked · 3 need you" · "All checked · ready to save". */
export function progressWords(draft: DraftBrief): string {
  if (draft.lines_total === 0) return 'No ingredients found';
  const need = needYou(draft);
  if (need === 0) return 'All checked · ready to save';
  return `${draft.lines_checked} of ${draft.lines_total} ingredients checked · ${need} ${need === 1 ? 'needs' : 'need'} you`;
}

/** The computer's column: "6 of 9 · 3 need you" · "All checked · ready to save". */
export function shortProgress(draft: DraftBrief): string {
  if (draft.lines_total === 0) return 'No ingredients found';
  const need = needYou(draft);
  if (need === 0) return 'All checked · ready to save';
  return `${draft.lines_checked} of ${draft.lines_total} · ${need} ${need === 1 ? 'needs' : 'need'} you`;
}

/** The share of the bar that is filled. */
export function progressShare(draft: DraftBrief): number {
  return draft.lines_total === 0 ? 0 : Math.round((draft.lines_checked / draft.lines_total) * 100);
}
