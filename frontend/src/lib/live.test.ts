import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setUnauthorizedHandler } from './api';
import { live } from './live.svelte';
import { network, OFFLINE_AFTER_MS } from './network.svelte';
import { toasts } from './toast.svelte';
import { loadDeviceId } from './offline/device';
import { getMeta } from './offline/phone';
import { addToQueue, readQueue } from './offline/store';
import { dropPhone, freshPhone } from './testing/phone';

// A stand-in for the browser's EventSource, so a test can send the server's lines.
class FakeSource extends EventTarget {
  static all: FakeSource[] = [];
  static readonly CLOSED = 2;
  readyState = 1;
  constructor(readonly url: string) {
    super();
    FakeSource.all.push(this);
  }
  close() {
    this.readyState = 2;
  }
  send(name: string, data: unknown) {
    this.dispatchEvent(new MessageEvent(name, { data: JSON.stringify(data) }));
  }
}

let stop: () => void;

beforeEach(() => {
  FakeSource.all = [];
  vi.stubGlobal('EventSource', FakeSource);
  network.reset();
  live.shopping = 0;
  live.pantry = 0;
  stop = live.start();
});

afterEach(() => {
  stop();
  setUnauthorizedHandler(null);
  vi.unstubAllGlobals();
  network.reset();
});

const stream = () => FakeSource.all.at(-1)!;

describe('the live stream', () => {
  it('opens our own server’s stream, and only that', () => {
    expect(FakeSource.all).toHaveLength(1);
    expect(stream().url).toBe('/api/v1/events');
  });

  it('remembers the highest shopping counter heard', () => {
    stream().send('hello', { cursor: 10 });
    expect(live.shopping).toBe(10);
    stream().send('shopping', { cursor: 12 });
    stream().send('shopping', { cursor: 11 }); // an older one never moves it back
    expect(live.shopping).toBe(12);
  });

  it('says each time the stream (re)connects, so waiting changes are sent', () => {
    stop();
    const hello = vi.fn();
    stop = live.start(hello);
    stream().send('hello', { cursor: 10 });
    live.reconnect();
    stream().send('hello', { cursor: 10 });
    expect(hello).toHaveBeenCalledTimes(2);
  });

  it('counts pantry changes', () => {
    stream().send('pantry', { change_id: 7 });
    stream().send('pantry', { change_id: 8 });
    expect(live.pantry).toBe(2);
  });

  it('goes to the sign-in page, as a 401 does, on signed_out', () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    stream().send('signed_out', {});
    expect(handler).toHaveBeenCalledOnce();
    expect(stream().readyState).toBe(2);
  });

  it('signed_out is not a sign-out: the changes waiting on the phone stay (11.5)', async () => {
    freshPhone();
    try {
      const device = await loadDeviceId();
      await addToQueue(
        { id: 'a', made_at: '2026-10-18T09:00:00Z', seen: 0, kind: 'tick', item_id: 'i' },
        1,
        device
      );
      setUnauthorizedHandler(() => {});
      stream().send('signed_out', {});
      expect(await readQueue()).toHaveLength(1);
      expect(await getMeta('device_id')).toBe(device);
    } finally {
      await dropPhone();
    }
  });

  it('ignores garbled lines', () => {
    stream().dispatchEvent(new MessageEvent('shopping', { data: 'not json' }));
    expect(live.shopping).toBe(0);
  });

  it('opens a new stream on "Try now", closing the old one', () => {
    const first = stream();
    live.reconnect();
    expect(first.readyState).toBe(2);
    expect(FakeSource.all).toHaveLength(2);
  });

  it('closes when the app shell goes away', () => {
    stop();
    expect(stream().readyState).toBe(2);
    stop = live.start();
  });
});

describe('a stream closed for a newer tab (replaced, more than 10 tabs on one sign-in)', () => {
  const lookAt = (state: 'visible' | 'hidden') => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: state });
    document.dispatchEvent(new Event('visibilitychange'));
  };
  // The server sends `replaced`, then closes the connection, which a browser reports as an
  // error if the stream is still open.
  const replaced = () => {
    const source = stream();
    source.send('replaced', {});
    source.readyState = source.readyState === 2 ? 2 : 0;
    source.dispatchEvent(new Event('error'));
  };

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    delete (document as { visibilityState?: unknown }).visibilityState;
  });

  it('closes quietly: no offline bar', () => {
    stream().send('hello', { cursor: 1 });
    replaced();
    vi.advanceTimersByTime(60_000);
    expect(network.offline).toBe(false);
    expect(stream().readyState).toBe(2); // so the browser doesn't reconnect by itself
  });

  it('never opens a new stream by itself, so it can’t close another tab’s in turn', () => {
    replaced();
    vi.advanceTimersByTime(60_000);
    live.reconnect(); // the connection came back: every tab hears it
    lookAt('hidden');
    vi.advanceTimersByTime(60_000);
    expect(FakeSource.all).toHaveLength(1);
  });

  it('opens again when the tab is looked at again', () => {
    replaced();
    lookAt('hidden');
    lookAt('visible');
    expect(FakeSource.all).toHaveLength(2);
    expect(stream().readyState).toBe(1);
    // and it is an ordinary stream again
    live.reconnect();
    expect(FakeSource.all).toHaveLength(3);
  });
});

describe('a dropped stream (F67)', () => {
  // The browser reports a dropped stream as an error and tries again by itself.
  const drop = () => {
    const source = stream();
    source.readyState = 0;
    source.dispatchEvent(new Event('error'));
  };

  beforeEach(() => {
    vi.useFakeTimers();
    toasts.dismiss();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('never shows the offline bar or a toast on its own: the server still answers', async () => {
    const check = vi.fn(async () => new Response('{}'));
    vi.stubGlobal('fetch', check);
    const shown = vi.spyOn(toasts, 'show');
    stream().send('hello', { cursor: 1 });
    for (let i = 0; i < 3; i++) {
      drop();
      // Looked at every second, so a bar that came and went would be seen.
      for (let s = 0; s < 20; s++) {
        await vi.advanceTimersByTimeAsync(1000);
        expect(network.offline).toBe(false);
      }
    }
    expect(shown).not.toHaveBeenCalled();
    // It asked our own server, and nothing else.
    expect(check).toHaveBeenCalled();
    for (const [url] of check.mock.calls as unknown as [string][]) {
      expect(url).toBe('/api/v1/version');
    }
  });

  it('shows the bar when the server really can’t be reached', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 502 }))
    );
    const shown = vi.spyOn(toasts, 'show');
    drop();
    await vi.advanceTimersByTimeAsync(OFFLINE_AFTER_MS + 100);
    expect(network.offline).toBe(true);
    await vi.advanceTimersByTimeAsync(60_000);
    expect(network.offline).toBe(true);
    expect(shown).not.toHaveBeenCalled();
  });
});
