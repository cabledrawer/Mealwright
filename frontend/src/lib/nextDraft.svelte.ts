// "Next draft" after a Save (F212, cabledrawer 10 Nov): Save recipe on Check opens the new recipe's
// page, and when more drafts are waiting that page offers the next one. This remembers which
// recipe was just saved from a draft's Check screen, so only that visit shows the button (not
// every visit to a recipe while drafts are waiting). Kept for the visit only; nothing is stored.
//
// The next draft is the oldest of the others still waiting (the order the household started
// them in), so a batch of links is checked from the first link to the last.

import { forgetWhenSessionEnds } from './api';
import type { DraftBrief } from './client/drafts';

class NextDraft {
  /** The recipe that was just saved from Check (or from a draft's own Save recipe). */
  savedId = $state<number | null>(null);

  /** The draft that was just saved, so it is never the one offered next (it can still be in the
   *  Drafts list for a moment). */
  fromDraftId = $state<number | null>(null);

  mark(recipeId: number, draftId: number | null = null): void {
    this.savedId = recipeId;
    this.fromDraftId = draftId;
  }

  /** The page was left: the next visit to that recipe shows nothing extra. */
  clear(recipeId: number): void {
    if (this.savedId === recipeId) {
      this.savedId = null;
      this.fromDraftId = null;
    }
  }
}

export const nextDraft = new NextDraft();
forgetWhenSessionEnds(() => (nextDraft.savedId = null));

/** The oldest waiting draft other than `except` (the one just saved), or null. */
export function oldestDraft(
  waiting: readonly DraftBrief[],
  except: number | null = null
): DraftBrief | null {
  let first: DraftBrief | null = null;
  for (const draft of waiting) {
    if (draft.id === except) continue;
    if (
      first === null ||
      draft.started_at < first.started_at ||
      (draft.started_at === first.started_at && draft.id < first.id)
    ) {
      first = draft;
    }
  }
  return first;
}
