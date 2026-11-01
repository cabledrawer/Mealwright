// "Keep screen awake" in Cook mode (cabledrawer 19 Oct, question 32, moved from the recipe page by
// the spec's "Cook mode timers"): the switch starts off, and Cook mode turns it on when it opens;
// it turns itself off when the person leaves, and where the browser can't do it the switch is
// greyed with the reason. It uses the browser's own Screen Wake Lock: nothing is sent anywhere
// and nothing is remembered.

interface Sentinel {
  release(): Promise<void>;
  addEventListener(type: 'release', listener: () => void): void;
}

interface WakeLockApi {
  request(type: 'screen'): Promise<Sentinel>;
}

/** The browser's Wake Lock, or null where it has none. Looked at each time, never cached. */
const wakeLock = (): WakeLockApi | null =>
  typeof navigator !== 'undefined' && 'wakeLock' in navigator
    ? ((navigator as unknown as { wakeLock: WakeLockApi }).wakeLock ?? null)
    : null;

export class ScreenAwake {
  /** Whether this browser can keep the screen awake: the switch is greyed when it can't. */
  readonly supported = wakeLock() !== null;
  /** The switch. */
  on = $state(false);
  /** The browser said no (low battery, a setting): shown calmly beside the switch. */
  refused = $state(false);

  #sentinel: Sentinel | null = null;
  /** Bumped by every change, so a request that answers late can tell it is out of date. */
  #turn = 0;

  /** The switch was flipped to `on`. */
  async set(on: boolean): Promise<void> {
    const turn = ++this.#turn;
    this.on = on;
    this.refused = false;
    if (!on) return this.#release();
    await this.#hold(turn);
  }

  async #hold(turn: number): Promise<void> {
    try {
      const sentinel = await wakeLock()?.request('screen');
      if (!sentinel) throw new Error('No wake lock');
      if (turn !== this.#turn) {
        // Switched off (or left) while the browser was thinking.
        await sentinel.release().catch(() => undefined);
        return;
      }
      this.#sentinel = sentinel;
      // The browser lets go by itself when the tab is hidden; see `comeBack`.
      sentinel.addEventListener('release', () => {
        if (this.#sentinel === sentinel) this.#sentinel = null;
      });
    } catch {
      if (turn === this.#turn) {
        this.on = false;
        this.refused = true;
      }
    }
  }

  async #release(): Promise<void> {
    const sentinel = this.#sentinel;
    this.#sentinel = null;
    await sentinel?.release().catch(() => undefined);
  }

  /** The page was hidden and is back: the browser dropped the lock, so ask again if it's on. */
  async comeBack(): Promise<void> {
    if (this.on && this.#sentinel === null) await this.#hold(this.#turn);
  }

  /** Leaving the page: off, and let go. */
  leave(): Promise<void> {
    this.#turn++;
    this.on = false;
    return this.#release();
  }
}
