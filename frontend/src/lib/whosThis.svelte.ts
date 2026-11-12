// "Who's this?" on a shared login (0.9 A1, mockup Dark-WhosThis09-Phone): a kitchen tablet the
// household shares asks who is using it, so Recent changes says who did what. Only while the
// household has the switch on (Settings → Household), and only on a shared login.
//
// Asked when the app opens with nobody picked, and again after 30 minutes without use (the pick
// is cleared first, so nothing is recorded for the last person meanwhile). "Just looking" picks
// nobody and doesn't ask again for an hour on this device. Both times are accepted (cabledrawer 12 Nov).

import { cantReach } from './api';
import { getWhosThis, pickWho, type Pickable } from './client/people';
import { nothingChanged } from './downWords';
import { network } from './network.svelte';
import { session } from './session.svelte';

export const IDLE_MS = 30 * 60 * 1000;
export const LOOKING_MS = 60 * 60 * 1000;
const LOOKING_KEY = 'mealwright.whosThis.lookingUntil';

function readLooking(): number {
  try {
    return Number(localStorage.getItem(LOOKING_KEY)) || 0;
  } catch {
    return 0;
  }
}

function writeLooking(until: number) {
  try {
    if (until) localStorage.setItem(LOOKING_KEY, String(until));
    else localStorage.removeItem(LOOKING_KEY);
  } catch {
    // Storage blocked: remembered for this tab only.
  }
}

class WhosThis_ {
  /** The sheet is showing. */
  open = $state(false);
  people = $state<Pickable[]>([]);
  picked = $state<number | null>(null);
  /** The pick couldn't be sent: the sheet says so and stays. */
  problem = $state<string | null>(null);
  busy = $state(false);
  #lookingUntil = readLooking();
  #lastUse = Date.now();
  #now: () => number = () => Date.now();

  /** For tests: a clock to use instead of the real one. */
  useClock(now: () => number) {
    this.#now = now;
    this.#lastUse = now();
    this.#lookingUntil = readLooking();
  }

  get #shared(): boolean {
    return !!session.me?.shared;
  }

  /** Ask the server whether to ask, and open the sheet if nobody is picked. */
  async check(): Promise<void> {
    if (!this.#shared) return;
    try {
      const found = await getWhosThis();
      this.people = found.people;
      this.picked = found.picked;
      if (!found.ask) {
        this.open = false;
        return;
      }
      if (found.picked === null && this.#now() >= this.#lookingUntil) this.open = true;
    } catch (error) {
      if (!cantReach(error)) throw error;
      // No answer: ask next time the app is used.
    }
  }

  /** Someone touched or typed: after 30 minutes without use, clear the pick and ask again. */
  used(): void {
    if (!this.#shared) return;
    const now = this.#now();
    const idle = now - this.#lastUse;
    this.#lastUse = now;
    if (idle < IDLE_MS || this.open) return;
    void this.#askAgain();
  }

  async #askAgain() {
    try {
      if (this.picked !== null) {
        const found = await pickWho(null);
        this.picked = found.picked;
      }
    } catch (error) {
      if (!cantReach(error)) throw error;
    }
    this.#lookingUntil = 0;
    writeLooking(0);
    await this.check();
  }

  async pick(memberId: number | null): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    this.problem = null;
    try {
      const found = await pickWho(memberId);
      this.picked = found.picked;
      this.people = found.people;
      this.#lastUse = this.#now();
      this.#lookingUntil = memberId === null ? this.#now() + LOOKING_MS : 0;
      writeLooking(this.#lookingUntil);
      this.open = false;
    } catch (error) {
      this.problem = cantReach(error)
        ? nothingChanged(network.deviceOffline)
        : 'Something went wrong. Try again.';
    } finally {
      this.busy = false;
    }
  }

  forget() {
    this.open = false;
    this.people = [];
    this.picked = null;
    this.problem = null;
  }
}

export const whosThis = new WhosThis_();
