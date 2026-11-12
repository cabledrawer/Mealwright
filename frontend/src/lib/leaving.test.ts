import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isLeaving, watchLeaving, whenStaying } from './leaving';

// A stand-in window, so the test's own page is never left.
let win: EventTarget;
let stop: () => void;

beforeEach(() => {
  win = new EventTarget();
  stop = watchLeaving(win as unknown as Window);
});
afterEach(() => stop());

const fire = (type: string, init: EventInit = {}) => {
  const event = new Event(type, { cancelable: true, ...init });
  win.dispatchEvent(event);
  return event;
};

/** Whether the promise has settled after the queued work has run. */
async function settled(promise: Promise<unknown>) {
  let done = false;
  void promise.then(() => (done = true));
  await new Promise((resolve) => setTimeout(resolve, 0));
  return done;
}

describe('watchLeaving', () => {
  it('is not leaving at first, and whenStaying answers at once', async () => {
    expect(isLeaving()).toBe(false);
    expect(await settled(whenStaying())).toBe(true);
  });

  it('starts leaving at beforeunload, and holds whenStaying until the page stays', async () => {
    fire('beforeunload');
    expect(isLeaving()).toBe(true);
    const waiting = whenStaying();
    expect(await settled(waiting)).toBe(false);
    // Brought back from the back-forward cache.
    fire('pageshow');
    expect(isLeaving()).toBe(false);
    expect(await settled(waiting)).toBe(true);
  });

  it('doesn’t count a leave the page asked the browser to confirm, until the page is hidden', () => {
    const asked = new Event('beforeunload', { cancelable: true });
    asked.preventDefault();
    win.dispatchEvent(asked);
    expect(isLeaving()).toBe(false);
    fire('pagehide');
    expect(isLeaving()).toBe(true);
  });

  it('a tap or a key on the page means it is staying', () => {
    fire('beforeunload');
    fire('pointerdown');
    expect(isLeaving()).toBe(false);
    fire('beforeunload');
    fire('keydown');
    expect(isLeaving()).toBe(false);
  });

  it('lets go of code cut off by the leave, but not of other errors or of code failing while staying', () => {
    const rejected = (reason: unknown) => {
      const event = new Event('unhandledrejection', { cancelable: true }) as Event & {
        reason: unknown;
      };
      event.reason = reason;
      win.dispatchEvent(event);
      return event.defaultPrevented;
    };
    const preloadError = (payload: Error) => {
      const event = new Event('vite:preloadError', { cancelable: true }) as Event & {
        payload: Error;
      };
      event.payload = payload;
      win.dispatchEvent(event);
      return event;
    };
    // While staying: a failed preload is a real error and stays one.
    const whileStaying = new Error('Unable to preload CSS for /a.css');
    expect(preloadError(whileStaying).defaultPrevented).toBe(false);
    expect(rejected(whileStaying)).toBe(false);
    // While leaving: the cut-off preload is let go (not prevented, so the import still fails).
    fire('beforeunload');
    const cut = new Error('Unable to preload CSS for /b.css');
    expect(preloadError(cut).defaultPrevented).toBe(false);
    expect(rejected(cut)).toBe(true);
    // Any other error while leaving is still reported.
    expect(rejected(new Error('a real bug'))).toBe(false);
  });

  it('lets go of a main import() cut off by the leave, in any browser’s words, only while leaving', () => {
    const rejected = (reason: unknown) => {
      const event = new Event('unhandledrejection', { cancelable: true }) as Event & {
        reason: unknown;
      };
      event.reason = reason;
      win.dispatchEvent(event);
      return event.defaultPrevented;
    };
    const failed = () => new TypeError('Failed to fetch dynamically imported module: /a.js');
    expect(rejected(failed())).toBe(false);
    fire('beforeunload');
    expect(rejected(failed())).toBe(true);
    expect(rejected(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(rejected(new TypeError('x is not a function'))).toBe(false);
  });

  describe('a leave that never happens', () => {
    beforeEach(() => vi.useFakeTimers());
    afterEach(() => vi.useRealTimers());

    it('the page showing again means it is staying', () => {
      fire('beforeunload');
      expect(isLeaving()).toBe(true);
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      fire('visibilitychange');
      expect(isLeaving()).toBe(false);
    });

    it('stays on while the page is hidden', () => {
      fire('beforeunload');
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      fire('visibilitychange');
      expect(isLeaving()).toBe(true);
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
    });

    it('is off after 3 s with no pagehide, and holds requests until then', async () => {
      fire('beforeunload');
      const waiting = whenStaying();
      vi.advanceTimersByTime(2900);
      expect(isLeaving()).toBe(true);
      vi.advanceTimersByTime(200);
      expect(isLeaving()).toBe(false);
      await expect(waiting).resolves.toBeUndefined();
    });

    it('once pagehide has come it stays on until pageshow', () => {
      fire('beforeunload');
      fire('pagehide');
      vi.advanceTimersByTime(10_000);
      expect(isLeaving()).toBe(true);
      fire('pageshow');
      expect(isLeaving()).toBe(false);
    });
  });

  it('stops watching, and is no longer leaving, once stopped', async () => {
    fire('beforeunload');
    const waiting = whenStaying();
    stop();
    expect(isLeaving()).toBe(false);
    expect(await settled(waiting)).toBe(true);
    fire('beforeunload');
    expect(isLeaving()).toBe(false);
    stop = () => {};
  });
});
