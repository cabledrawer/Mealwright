import { afterEach, describe, expect, it, vi } from 'vitest';
import { CookTimers, TICK_MS, type TimerClock } from './cookTimers.svelte';

vi.mock('./chime', () => ({ primeChime: vi.fn(), playChime: vi.fn(() => []) }));

/** A clock the test moves by hand. */
function fakeClock() {
  let now = 1_000_000;
  let run: (() => void) | null = null;
  const clock: TimerClock = {
    now: () => now,
    every: (_ms, fn) => {
      run = fn;
      return () => void (run = null);
    }
  };
  return {
    clock,
    /** Time passes (the interval fires once, as a throttled background tab's would). */
    pass: (seconds: number) => {
      now += seconds * 1000;
      run?.();
    },
    watching: () => run !== null
  };
}

afterEach(() => vi.clearAllMocks());

describe('Cook mode timers', () => {
  it('counts down on the screen from the time it should end', () => {
    const t = fakeClock();
    const timers = new CookTimers(t.clock, () => {});
    timers.start('1:0', '10 minutes', 600);
    expect(timers.get('1:0')).toMatchObject({ left: 600, state: 'running' });
    expect(timers.running).toBe(true);
    t.pass(1);
    expect(timers.get('1:0')?.left).toBe(599);
    t.pass(59);
    expect(timers.get('1:0')?.left).toBe(540);
  });

  it('sounds the chime once when it ends, and then is ended, not running', () => {
    const t = fakeClock();
    const sound = vi.fn();
    const timers = new CookTimers(t.clock, sound);
    timers.start('1:0', '1 minute', 60);
    t.pass(59);
    expect(sound).not.toHaveBeenCalled();
    t.pass(1);
    expect(sound).toHaveBeenCalledTimes(1);
    expect(timers.get('1:0')).toMatchObject({ left: 0, state: 'ended' });
    expect(timers.running).toBe(false);
    // Nothing keeps ticking once nothing runs.
    expect(t.watching()).toBe(false);
    t.pass(10);
    expect(sound).toHaveBeenCalledTimes(1);
  });

  it('shows the right time when the screen wakes after a long sleep', () => {
    const t = fakeClock();
    const sound = vi.fn();
    const timers = new CookTimers(t.clock, sound);
    timers.start('1:0', '10 minutes', 600);
    timers.start('2:0', '30 minutes', 1800);
    t.pass(700); // no tick came for 700 seconds
    expect(timers.get('1:0')?.state).toBe('ended');
    expect(timers.get('2:0')).toMatchObject({ state: 'running', left: 1100 });
    expect(sound).toHaveBeenCalledTimes(1);
  });

  it('runs several timers side by side, and one chime for those that end together', () => {
    const t = fakeClock();
    const sound = vi.fn();
    const timers = new CookTimers(t.clock, sound);
    timers.start('1:0', 'a', 10);
    timers.start('1:1', 'b', 10);
    t.pass(10);
    expect(sound).toHaveBeenCalledTimes(1);
    expect(timers.timers.map((x) => x.state)).toEqual(['ended', 'ended']);
  });

  it('stops one timer without a chime, and stops all of them on leaving', () => {
    const t = fakeClock();
    const sound = vi.fn();
    const timers = new CookTimers(t.clock, sound);
    timers.start('1:0', 'a', 60);
    timers.start('2:0', 'b', 60);
    timers.clear('1:0');
    expect(timers.get('1:0')).toBeUndefined();
    expect(timers.running).toBe(true);
    timers.stopAll();
    expect(timers.timers).toEqual([]);
    expect(timers.running).toBe(false);
    expect(t.watching()).toBe(false);
    t.pass(100);
    expect(sound).not.toHaveBeenCalled();
  });

  it('starts again from the full time when started a second time', () => {
    const t = fakeClock();
    const timers = new CookTimers(t.clock, () => {});
    timers.start('1:0', 'a', 60);
    t.pass(30);
    timers.start('1:0', 'a', 60);
    expect(timers.get('1:0')?.left).toBe(60);
    expect(timers.timers).toHaveLength(1);
  });

  it('looks at the clock four times a second', () => {
    expect(TICK_MS).toBe(250);
  });
});
