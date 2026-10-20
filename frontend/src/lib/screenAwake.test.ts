import { afterEach, describe, expect, it, vi } from 'vitest';
import { ScreenAwake } from './screenAwake.svelte';

function fakeWakeLock(options: { refuse?: boolean } = {}) {
  const released: number[] = [];
  /** What the browser does when the page is hidden: it lets go by itself. */
  const drops: (() => void)[] = [];
  let count = 0;
  const lock = {
    request: vi.fn(async () => {
      if (options.refuse) throw new DOMException('Low battery', 'NotAllowedError');
      const id = ++count;
      return {
        release: async () => void released.push(id),
        addEventListener: (_type: string, listener: () => void) => void drops.push(listener)
      };
    })
  };
  Object.defineProperty(navigator, 'wakeLock', { value: lock, configurable: true });
  return { lock, released, drops };
}

afterEach(() => {
  // Remove our own stand-in; the browser's own (on the prototype) shows through again.
  delete (navigator as unknown as Record<string, unknown>).wakeLock;
});

describe('Keep screen awake', () => {
  it('is hidden where the browser can’t do it', () => {
    Object.defineProperty(navigator, 'wakeLock', { value: undefined, configurable: true });
    expect(new ScreenAwake().supported).toBe(false);
  });

  it('is there where the browser can', () => {
    fakeWakeLock();
    expect(new ScreenAwake().supported).toBe(true);
  });

  it('starts off, asks the browser when switched on, and lets go when switched off', async () => {
    const { lock, released } = fakeWakeLock();
    const awake = new ScreenAwake();
    expect(awake.on).toBe(false);
    expect(lock.request).not.toHaveBeenCalled();
    await awake.set(true);
    expect(awake.on).toBe(true);
    expect(lock.request).toHaveBeenCalledWith('screen');
    await awake.set(false);
    expect(awake.on).toBe(false);
    expect(released).toEqual([1]);
  });

  it('turns itself off, and lets go, on leaving the page', async () => {
    const { released } = fakeWakeLock();
    const awake = new ScreenAwake();
    await awake.set(true);
    await awake.leave();
    expect(awake.on).toBe(false);
    expect(released).toEqual([1]);
    // A page opened next time starts off again.
    expect(new ScreenAwake().on).toBe(false);
  });

  it('lets go of a lock that arrives after the person has already left', async () => {
    const { released } = fakeWakeLock();
    const awake = new ScreenAwake();
    const pending = awake.set(true);
    await awake.leave();
    await pending;
    expect(awake.on).toBe(false);
    expect(released).toEqual([1]);
  });

  it('switches itself back off, and says so, when the browser says no', async () => {
    fakeWakeLock({ refuse: true });
    const awake = new ScreenAwake();
    await awake.set(true);
    expect(awake.on).toBe(false);
    expect(awake.refused).toBe(true);
    await awake.set(false);
    expect(awake.refused).toBe(false);
  });

  it('asks again when the page comes back to the front while the switch is on', async () => {
    const { lock, drops } = fakeWakeLock();
    const awake = new ScreenAwake();
    await awake.set(true);
    await awake.comeBack(); // nothing was dropped: nothing to ask again
    expect(lock.request).toHaveBeenCalledTimes(1);
    for (const drop of drops) drop(); // the page was hidden: the browser let go
    await awake.comeBack();
    expect(lock.request).toHaveBeenCalledTimes(2);
    expect(awake.on).toBe(true);
    // Off, it stays off.
    await awake.set(false);
    await awake.comeBack();
    expect(lock.request).toHaveBeenCalledTimes(2);
  });
});
