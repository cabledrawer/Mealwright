import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BACK_ONLINE,
  CHECK_EVERY_MS,
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
