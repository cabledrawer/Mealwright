import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BACK_ONLINE,
  CHECK_EVERY_MS,
  CHECK_TIMEOUT_MS,
  OFFLINE_AFTER_MS,
  network,
  offlineText
} from './network.svelte';
import { toasts } from './toast.svelte';

beforeEach(() => {
  vi.useFakeTimers();
  network.reset();
  toasts.dismiss();
});

afterEach(() => {
  network.reset();
  vi.useRealTimers();
});

describe('the offline bar', () => {
  it('shows nothing for a blip under 3 seconds, and no toast after it', () => {
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS - 1);
    expect(network.offline).toBe(false);
    network.succeeded();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS * 2);
    expect(network.offline).toBe(false);
    expect(toasts.current).toBeNull();
  });

  it('shows after 3 seconds of failing, then "Back online — all saved" when it works again', () => {
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    expect(network.offline).toBe(true);
    network.succeeded();
    expect(network.offline).toBe(false);
    expect(toasts.current?.message).toBe(BACK_ONLINE);
    expect(BACK_ONLINE).toBe('Back online — all saved');
  });

  it('says "all saved" only once the waiting changes have gone', () => {
    network.waiting = 3;
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    network.succeeded();
    expect(network.offline).toBe(false);
    expect(toasts.current).toBeNull();
    network.waiting = 1;
    expect(toasts.current).toBeNull();
    network.waiting = 0;
    expect(toasts.current?.message).toBe(BACK_ONLINE);
    // Once only.
    toasts.dismiss();
    network.waiting = 2;
    network.waiting = 0;
    expect(toasts.current).toBeNull();
  });

  it('no toast if the connection goes again before the changes are sent', () => {
    network.waiting = 2;
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    network.succeeded();
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    network.waiting = 0;
    expect(network.offline).toBe(true);
    expect(toasts.current).toBeNull();
  });

  it('counts a run of failures as one', () => {
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS - 1000);
    network.failed(); // another failed request does not restart the 3 seconds
    vi.advanceTimersByTime(1000);
    expect(network.offline).toBe(true);
  });

  it('says nothing when something that never failed succeeds', () => {
    network.succeeded();
    expect(toasts.current).toBeNull();
  });
});

describe('when the connection comes back', () => {
  it('counts each time it comes back, so a failed photo can try again', () => {
    expect(network.backAgain).toBe(0);
    network.failed();
    network.succeeded(); // even a blip too short for the bar
    expect(network.backAgain).toBe(1);
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    network.succeeded();
    expect(network.backAgain).toBe(2);
  });

  it('doesn’t count answers while nothing was failing', () => {
    network.succeeded();
    network.succeeded();
    expect(network.backAgain).toBe(0);
  });

  it('counts the browser coming back once, after an ordinary failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}'))
    );
    const stop = network.start(() => {});
    try {
      network.failed(); // gone offline
      window.dispatchEvent(new Event('online'));
      await vi.waitFor(() => expect(network.backAgain).toBe(1));
      await vi.advanceTimersByTimeAsync(100);
      expect(network.backAgain).toBe(1);
    } finally {
      stop();
      vi.unstubAllGlobals();
    }
  });

  it('counts the browser coming back, even when an answer while offline already cleared the failure', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('{}'))
    );
    const stop = network.start(() => {});
    try {
      network.failed(); // gone offline
      network.succeeded(); // a late answer, still offline: a failed photo tries now and fails again
      expect(network.backAgain).toBe(1);
      window.dispatchEvent(new Event('online'));
      await vi.waitFor(() => expect(network.backAgain).toBe(2));
    } finally {
      stop();
      vi.unstubAllGlobals();
    }
  });
});

describe('the words in the bar', () => {
  it('says just "Offline" when nothing is waiting', () => {
    expect(offlineText('phone', 0)).toEqual({ title: 'Offline', detail: null });
    expect(offlineText('desktop', 0)).toEqual({ title: 'Offline', detail: null });
  });

  it('phone: "Offline — N changes waiting"', () => {
    expect(offlineText('phone', 3).title).toBe('Offline — 3 changes waiting');
    expect(offlineText('phone', 1).title).toBe('Offline — 1 change waiting');
  });

  it('desktop: a second line, as in the mockups', () => {
    expect(offlineText('desktop', 3)).toEqual({
      title: 'Offline',
      detail: '3 changes waiting. They’ll save when you’re back.'
    });
    expect(offlineText('desktop', 1).detail).toBe(
      '1 change waiting. They’ll save when you’re back.'
    );
  });
});

describe('the server is down behind a reverse proxy (F67)', () => {
  // Caddy answers 502 when Mealwright is stopped; 503 and 504 mean the same.
  for (const status of [502, 503, 504]) {
    it(`a ${status} from the online check keeps it offline, with no "Back online — all saved"`, async () => {
      let up = false;
      const check = vi.fn(async () => (up ? new Response('{}') : new Response('', { status })));
      vi.stubGlobal('fetch', check);
      const stop = network.start(() => {});
      try {
        network.failed();
        await vi.advanceTimersByTimeAsync(OFFLINE_AFTER_MS);
        expect(network.offline).toBe(true);
        // A minute of checks, every one answered by the proxy.
        await vi.advanceTimersByTimeAsync(60_000);
        expect(check.mock.calls.length).toBeGreaterThan(5);
        expect(network.offline).toBe(true);
        expect(network.backAgain).toBe(0);
        expect(toasts.current).toBeNull();
        // The server is really back: the next check says so.
        up = true;
        await vi.advanceTimersByTimeAsync(CHECK_EVERY_MS);
        expect(network.offline).toBe(false);
        expect(toasts.current?.message).toBe(BACK_ONLINE);
      } finally {
        stop();
        vi.unstubAllGlobals();
      }
    });
  }

  it('"Try now" with the proxy answering 502 stays offline', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 502 }))
    );
    const reconnect = vi.fn();
    const stop = network.start(reconnect);
    try {
      network.failed();
      await vi.advanceTimersByTimeAsync(OFFLINE_AFTER_MS);
      await network.tryNow();
      expect(network.offline).toBe(true);
      expect(reconnect).not.toHaveBeenCalled();
      expect(toasts.current).toBeNull();
    } finally {
      stop();
      vi.unstubAllGlobals();
    }
  });
});

describe('the online check is gentle (F67)', () => {
  const lookAt = (state: 'visible' | 'hidden') => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: state });
    document.dispatchEvent(new Event('visibilitychange'));
  };

  afterEach(() => {
    delete (document as { visibilityState?: unknown }).visibilityState;
    vi.unstubAllGlobals();
  });

  /** A server that never answers: each check gives up after its time limit. (The browser's
   *  own time limit runs on real time, so the pretend one stands in for it.) */
  const hanging = () => {
    const check = vi.fn(
      () =>
        new Promise<Response>((_, reject) =>
          setTimeout(() => reject(new DOMException('', 'TimeoutError')), CHECK_TIMEOUT_MS)
        )
    );
    vi.stubGlobal('fetch', check);
    return check;
  };

  it('never overlaps itself: a slow check is waited for, not joined by another', async () => {
    const check = hanging();
    const stop = network.start(() => {});
    try {
      network.failed();
      // Checks start every 5 s, and each may take up to 8 s.
      await vi.advanceTimersByTimeAsync(CHECK_EVERY_MS * 2 + 100);
      expect(check).toHaveBeenCalledTimes(1);
      // "Try now" meanwhile joins the check under way.
      void network.tryNow();
      await vi.advanceTimersByTimeAsync(0);
      expect(check).toHaveBeenCalledTimes(1);
      // Once it has given up, the next one may start.
      await vi.advanceTimersByTimeAsync(CHECK_TIMEOUT_MS);
      await vi.advanceTimersByTimeAsync(CHECK_EVERY_MS);
      expect(check.mock.calls.length).toBeGreaterThan(1);
      let running = 0;
      let most = 0;
      check.mockImplementation(async () => {
        running++;
        most = Math.max(most, running);
        await new Promise((done) => setTimeout(done, CHECK_TIMEOUT_MS - 1));
        running--;
        return new Response('', { status: 502 });
      });
      await vi.advanceTimersByTimeAsync(60_000);
      expect(most).toBe(1);
    } finally {
      stop();
    }
  });

  it('doesn’t check while the tab is in the background, and checks at once when it’s back', async () => {
    const check = vi.fn(async () => new Response('', { status: 502 }));
    vi.stubGlobal('fetch', check);
    const stop = network.start(() => {});
    try {
      network.failed();
      lookAt('hidden');
      await vi.advanceTimersByTimeAsync(60_000);
      expect(check).not.toHaveBeenCalled();
      expect(network.offline).toBe(true);
      check.mockImplementation(async () => new Response('{}'));
      lookAt('visible');
      await vi.advanceTimersByTimeAsync(0);
      expect(check).toHaveBeenCalledTimes(1);
      expect(network.offline).toBe(false);
    } finally {
      stop();
    }
  });

  it('a tab that comes back while all is well asks nothing', async () => {
    const check = vi.fn(async () => new Response('{}'));
    vi.stubGlobal('fetch', check);
    const stop = network.start(() => {});
    try {
      lookAt('hidden');
      lookAt('visible');
      await vi.advanceTimersByTimeAsync(CHECK_EVERY_MS * 3);
      expect(check).not.toHaveBeenCalled();
    } finally {
      stop();
    }
  });
});

describe('one steady message, chosen by the cause (cabledrawer 30 Oct)', () => {
  it('is down from the first failure, before the bar, and stays down until an answer', () => {
    expect(network.down).toBe(false);
    network.failed();
    expect(network.failing).toBe(true);
    expect(network.down).toBe(true);
    expect(network.offline).toBe(false);
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    expect(network.down).toBe(true);
    network.succeeded();
    expect(network.down).toBe(false);
    expect(network.failing).toBe(false);
  });

  it('an answer to a request sent before the failures began doesn’t end it (follow-up 10)', () => {
    const before = Date.now();
    vi.advanceTimersByTime(10);
    network.failed();
    network.succeeded(before);
    expect(network.down).toBe(true);
  });

  it('knows whether the device itself has no network, from the browser', () => {
    const stop = network.start(() => {});
    expect(network.deviceOffline).toBe(false);
    window.dispatchEvent(new Event('offline'));
    expect(network.deviceOffline).toBe(true);
    expect(network.down).toBe(true);
    window.dispatchEvent(new Event('online'));
    expect(network.deviceOffline).toBe(false);
    stop();
  });

  it('a device already offline when the app starts says so at once', () => {
    vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
    const stop = network.start(() => {});
    expect(network.deviceOffline).toBe(true);
    expect(network.down).toBe(true);
    stop();
    vi.restoreAllMocks();
  });
});
