import { afterEach, beforeEach, describe, expect, it } from 'vitest';
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
