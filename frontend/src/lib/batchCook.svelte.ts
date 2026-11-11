// Batch cook (Experimental; 0.8 wave 6, B2): whether it is shown (an admin can hide it in
// Settings), and the first-time note.
//
// **Shown:** the household's setting, read once when the app needs it (the sidebar, the Plan's
// tabs) and again when the connection comes back or Settings changes it. Until the server has
// said, it is shown (it is visible from the start, cabledrawer 6 Nov); offline it keeps the last
// answer it had.
//
// **The first-time note** ("The picks and timings are guesses…", with Got it) is remembered for
// each person on this device, in the browser's own storage, keyed by the person. That is the
// safest place without another database change (B2 is the one that makes Batch cook's second
// change); a cleared browser or another device asks again, which is harmless.

import { changeBatchCook, getHousehold } from './client/household';

const NOTE_KEY = 'mealwright.batch-cook-note';

export class BatchCookSwitch {
  /** Whether Batch cook is shown. */
  shown = $state(true);
  /** The server has answered at least once. */
  known = $state(false);
  #asking = false;

  async load(): Promise<void> {
    if (this.#asking) return;
    this.#asking = true;
    try {
      this.shown = (await getHousehold()).batch_cook !== false;
      this.known = true;
    } catch {
      // Offline or unreachable: it keeps what it had.
    } finally {
      this.#asking = false;
    }
  }

  /** Switch it for the household (admins only; the server refuses anyone else). */
  async set(on: boolean): Promise<void> {
    this.shown = (await changeBatchCook(on)).batch_cook;
    this.known = true;
  }
}

export const batchCook = new BatchCookSwitch();

/** Whether this person has said "Got it" to the first-time note. */
export function noteSeen(personId: number | null | undefined): boolean {
  if (personId == null) return false;
  try {
    return localStorage.getItem(`${NOTE_KEY}.${personId}`) === 'seen';
  } catch {
    return false;
  }
}

export function markNoteSeen(personId: number | null | undefined): void {
  if (personId == null) return;
  try {
    localStorage.setItem(`${NOTE_KEY}.${personId}`, 'seen');
  } catch {
    // Storage blocked: the note shows again next time.
  }
}
