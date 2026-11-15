import { describe, expect, it, vi } from 'vitest';
import { IDLE_TIMEOUT_MS, whenIdle, type IdleHost } from './whenIdle';

function host(readyState: string, withIdle = true) {
  const loads: (() => void)[] = [];
  const idles: (() => void)[] = [];
  const timers: (() => void)[] = [];
  const h: IdleHost = {
    readyState,
    addEventListener: (_t, fn) => void loads.push(fn),
    removeEventListener: (_t, fn) => void loads.splice(loads.indexOf(fn), 1),
    setTimeout: (fn) => timers.push(fn),
    clearTimeout: (id) => void timers.splice(id - 1, 1, () => {})
  };
  if (withIdle) {
    h.requestIdleCallback = vi.fn((fn: () => void) => idles.push(fn));
    h.cancelIdleCallback = vi.fn();
  }
  return { h, loads, idles, timers };
}

describe('whenIdle', () => {
  it('waits for the page to load, then for an idle moment', () => {
    const { h, loads, idles } = host('loading');
    const work = vi.fn();
    whenIdle(work, h);
    expect(work).not.toHaveBeenCalled();
    loads[0]!();
    expect(idles).toHaveLength(1);
    expect(work).not.toHaveBeenCalled();
    idles[0]!();
    expect(work).toHaveBeenCalledTimes(1);
    expect(h.requestIdleCallback).toHaveBeenCalledWith(expect.any(Function), {
      timeout: IDLE_TIMEOUT_MS
    });
  });

  it('asks for an idle moment at once when the page has already loaded', () => {
    const { h, idles } = host('complete');
    whenIdle(vi.fn(), h);
    expect(idles).toHaveLength(1);
  });

  it('falls back to a short timer where there is no idle callback', () => {
    const { h, timers } = host('complete', false);
    const work = vi.fn();
    whenIdle(work, h);
    timers[0]!();
    expect(work).toHaveBeenCalledTimes(1);
  });

  it('does nothing when cancelled before the page loaded', () => {
    const { h, loads } = host('loading');
    const work = vi.fn();
    const cancel = whenIdle(work, h);
    cancel();
    expect(loads).toHaveLength(0);
    expect(work).not.toHaveBeenCalled();
  });

  it('cancels the idle request when cancelled after the page loaded', () => {
    const { h } = host('complete');
    whenIdle(vi.fn(), h)();
    expect(h.cancelIdleCallback).toHaveBeenCalledTimes(1);
  });
});
