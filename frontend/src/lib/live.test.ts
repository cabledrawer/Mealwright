import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { setUnauthorizedHandler } from './api';
import { live } from './live.svelte';
import { network } from './network.svelte';

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
