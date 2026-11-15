import { describe, expect, it, vi } from 'vitest';
import { AFTER_LOAD_MS, whenIdle, type IdleHost } from './whenIdle';

function host(readyState: string) {
  const loads: (() => void)[] = [];
  const timers = new Map<number, { fn: () => void; ms: number }>();
  let next = 1;
  const h: IdleHost = {
    readyState,
    addEventListener: (_t, fn) => void loads.push(fn),
    removeEventListener: (_t, fn) => void loads.splice(loads.indexOf(fn), 1),
    setTimeout: (fn, ms) => {
      timers.set(next, { fn, ms });
      return next++;
    },
    clearTimeout: (id) => void timers.delete(id)
  };
  return { h, loads, timers };
}

describe('whenIdle', () => {
  it('waits for the page to load, then a moment', () => {
    const { h, loads, timers } = host('loading');
    const work = vi.fn();
    whenIdle(work, h);
    expect(timers.size).toBe(0);
    loads[0]!();
    expect([...timers.values()].map((t) => t.ms)).toEqual([AFTER_LOAD_MS]);
    expect(work).not.toHaveBeenCalled();
    [...timers.values()][0]!.fn();
    expect(work).toHaveBeenCalledTimes(1);
  });

  it('starts the wait at once when the page has already loaded', () => {
    const { h, timers } = host('complete');
    whenIdle(vi.fn(), h);
    expect(timers.size).toBe(1);
  });

  it('does nothing when cancelled before the page loaded', () => {
    const { h, loads, timers } = host('loading');
    whenIdle(vi.fn(), h)();
    expect(loads).toHaveLength(0);
    expect(timers.size).toBe(0);
  });

  it('does nothing when cancelled during the wait', () => {
    const { h, timers } = host('complete');
    whenIdle(vi.fn(), h)();
    expect(timers.size).toBe(0);
  });
});
