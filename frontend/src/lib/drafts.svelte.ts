// The Drafts screen's state (spec "Drafts (cabledrawer 21 Oct)"): the household's drafts, a delete
// that hides at once and can be undone (a toast, or Ctrl+Z), and the count beside the Drafts
// entries. Online only: a draft is on the server, so offline the screen says so and shows
// nothing it can't stand behind.
//
// Kept for the visit (so the sidebar's count is there on every page) and forgotten on every
// way of signing out, so none of it carries over to whoever signs in next.

import { ApiError, cantReach, forgetWhenSessionEnds } from './api';
import { serverUndo } from './client/changes';
import { deleteDraft, listDrafts, type DraftBrief } from './client/drafts';
import { newChangeId } from './changeId';
import { toasts } from './toast.svelte';
import { undoHistory, type UndoEntry } from './undo.svelte';

export const NO_DRAFTS_OFFLINE =
  'Drafts are kept on your Mealwright server. They’ll show again when you’re back online.';
const COULDNT_LOAD = 'Couldn’t load your drafts. Try again.';
const COULDNT_DELETE = 'Couldn’t delete that draft. Try again.';

class Drafts {
  drafts = $state<DraftBrief[]>([]);
  /** A first answer has come in. */
  loaded = $state(false);
  loading = $state(false);
  /** The list couldn't be had: the reason. */
  problem = $state<string | null>(null);
  /** The server can't be reached (so the list may be out of date). */
  offline = $state(false);
  /** A delete or its Undo didn't go through: the reason. */
  deleteProblem = $state<string | null>(null);

  /** How many drafts, once known; null before the server has said. */
  get count(): number | null {
    return this.loaded ? this.drafts.length : null;
  }

  #generation = 0;

  /** Fetch the list (again, if already loaded: what's shown stays until the answer). */
  async load(): Promise<void> {
    const generation = this.#generation;
    this.loading = true;
    this.problem = null;
    try {
      const answer = await listDrafts();
      if (generation !== this.#generation) return;
      this.drafts = answer.drafts;
      this.loaded = true;
      this.offline = false;
    } catch (error) {
      if (generation !== this.#generation) return;
      if (error instanceof ApiError && cantReach(error)) this.offline = true;
      else this.problem = error instanceof ApiError ? error.detail : COULDNT_LOAD;
    } finally {
      if (generation === this.#generation) this.loading = false;
    }
  }

  /** Delete a draft: gone from the list at once, and the toast's Undo (or Ctrl+Z) is there at once
   *  too: it waits for the delete to finish, so it works even if pressed straight away. */
  async remove(draft: DraftBrief): Promise<void> {
    const generation = this.#generation;
    this.deleteProblem = null;
    const before = this.drafts;
    this.drafts = this.drafts.filter((d) => d.id !== draft.id);
    const deleting = deleteDraft(draft.id, newChangeId());
    const entry: UndoEntry = {
      label: `Deleted the ${draft.name} draft`,
      undo: async () => {
        const { change } = await deleting;
        const message = await serverUndo(change.id)();
        await this.load();
        return message;
      }
    };
    const toast = undoHistory.record(entry);
    try {
      await deleting;
    } catch (error) {
      undoHistory.forget(entry);
      if (toast !== undefined) toasts.dismiss(toast);
      if (generation !== this.#generation) return;
      // Someone else deleted it first: it is gone, which is what was wanted.
      if (error instanceof ApiError && error.status === 404) return;
      this.drafts = before;
      this.deleteProblem = error instanceof ApiError ? error.detail : COULDNT_DELETE;
    }
  }

  /** Forget everything (another login's household may be next). */
  forget(): void {
    this.#generation += 1;
    this.drafts = [];
    this.loaded = false;
    this.loading = false;
    this.problem = null;
    this.offline = false;
    this.deleteProblem = null;
  }
}

export const drafts = new Drafts();
forgetWhenSessionEnds(() => drafts.forget());
