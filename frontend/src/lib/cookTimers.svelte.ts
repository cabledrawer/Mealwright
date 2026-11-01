// Cook mode's timers (spec section 6, "Cook mode timers"). A timer starts on a tap, counts down
// on the screen, and ends with the chime. It is worked out from the moment it should end, not
// from counting ticks, so a screen that was asleep for a while shows the right time when it wakes
// (and the chime then plays at once). There is no alarm while the phone is locked or the app is
// in the background before 1.0: the screen says so. Nothing is saved; leaving stops every timer.

import { SvelteMap } from 'svelte/reactivity';
import { playChime, primeChime } from './chime';

export interface Timer {
  /** Which words of which step it came from: "3:0". */
  key: string;
  /** "10 minutes". */
  words: string;
  seconds: number;
  /** Whole seconds left; 0 once it has ended. */
  left: number;
  state: 'running' | 'ended';
}

export interface TimerClock {
  now(): number;
  every(ms: number, run: () => void): () => void;
}

const realClock: TimerClock = {
  now: () => Date.now(),
  every: (ms, run) => {
    const id = setInterval(run, ms);
    return () => clearInterval(id);
  }
};

/** How often a running timer looks at the clock. */
export const TICK_MS = 250;

export class CookTimers {
  /** Every timer started and not yet cleared, in the order they were started. */
  timers = $state<Timer[]>([]);

  #ends = new SvelteMap<string, number>();
  #stop: (() => void) | null = null;
  readonly #clock: TimerClock;
  readonly #sound: () => void;

  constructor(clock: TimerClock = realClock, sound: () => void = () => void playChime()) {
    this.#clock = clock;
    this.#sound = sound;
  }

  get running(): boolean {
    return this.timers.some((t) => t.state === 'running');
  }

  get(key: string): Timer | undefined {
    return this.timers.find((t) => t.key === key);
  }

  /** Start (or start again) the timer for these words. */
  start(key: string, words: string, seconds: number): void {
    // From a tap: the only moment a browser lets a page make sound later.
    primeChime();
    this.#ends.set(key, this.#clock.now() + seconds * 1000);
    const timer: Timer = { key, words, seconds, left: seconds, state: 'running' };
    this.timers = [...this.timers.filter((t) => t.key !== key), timer];
    this.#watch();
  }

  /** Stop one timer and take it off the screen (a running one is cancelled; an ended one cleared). */
  clear(key: string): void {
    this.#ends.delete(key);
    this.timers = this.timers.filter((t) => t.key !== key);
    if (!this.running) this.#unwatch();
  }

  /** Leaving Cook mode. */
  stopAll(): void {
    this.#ends.clear();
    this.timers = [];
    this.#unwatch();
  }

  /** Look at the clock now (also called when the page comes back to the front). */
  tick(): void {
    const now = this.#clock.now();
    let ended = false;
    this.timers = this.timers.map((timer) => {
      if (timer.state !== 'running') return timer;
      const end = this.#ends.get(timer.key) ?? now;
      const left = Math.max(0, Math.ceil((end - now) / 1000));
      if (left > 0) return left === timer.left ? timer : { ...timer, left };
      ended = true;
      return { ...timer, left: 0, state: 'ended' as const };
    });
    if (!this.running) this.#unwatch();
    // One chime for however many ended in this look.
    if (ended) this.#sound();
  }

  #watch(): void {
    this.#stop ??= this.#clock.every(TICK_MS, () => this.tick());
  }

  #unwatch(): void {
    this.#stop?.();
    this.#stop = null;
  }
}
