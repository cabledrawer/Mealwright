// Cook mode's per-step ingredients (Experimental): a household setting, off by default (cabledrawer
// 1 Nov: "Once on, it stays on for the household"). It is read from and saved to the household
// (GET and PATCH /household). Another phone sees a change the next time it opens Cook mode.
// Proposed, for cabledrawer: any signed-in person of the household may change it.
//
// The switch changes at once; if the server can't take it, it goes back to what it was and the
// usual words for "nothing was changed" say so.

import { cantReach } from './api';
import { changeCookPerStep, getHousehold } from './client/household';
import { nothingChanged } from './downWords';
import { network } from './network.svelte';
import { COULDNT_SAVE } from './save';

/** The old per-device key (before the household setting). It is no longer read: a device that
 *  had it on does not switch the household on silently. */
export const OLD_PER_STEP_KEY = 'mealwright.cook.perStep';

export class CookPrefs {
  /** Whether each step shows the ingredients guessed for it. */
  perStep = $state(false);

  /** The one line when the switch went back; cleared by the next flip that works. */
  problem = $state<string | null>(null);

  /** Counts the flips, so a read that started before one can be told from a fresh one. */
  #flips = 0;

  /** Read the household's setting (each time Cook mode opens). A failure leaves what it was. */
  async load(): Promise<void> {
    const flips = this.#flips;
    try {
      const on = (await getHousehold()).cook_per_step;
      if (flips === this.#flips) this.perStep = on; // a flip since then is newer than this reply
    } catch {
      // Cook mode still works; the switch keeps what it had.
    }
    try {
      localStorage.removeItem(OLD_PER_STEP_KEY); // no longer used
    } catch {
      // Storage blocked: nothing to tidy.
    }
  }

  /** Switch it for the household. Returns the one short line to show if it went back, else null. */
  async setPerStep(on: boolean): Promise<string | null> {
    const before = this.perStep;
    this.#flips++;
    this.perStep = on;
    try {
      this.perStep = (await changeCookPerStep(on)).cook_per_step;
      this.problem = null;
      return null;
    } catch (error) {
      this.perStep = before;
      this.problem = cantReach(error) ? nothingChanged(network.deviceOffline) : COULDNT_SAVE;
      return this.problem;
    }
  }
}

export const cookPrefs = new CookPrefs();
