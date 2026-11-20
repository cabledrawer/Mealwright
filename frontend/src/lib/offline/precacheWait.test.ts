import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  MAX_WAIT_MS,
  PAGE_GIVES_UP_MS,
  PAGE_IS_QUIET,
  QUIET_MS,
  afterQuiet,
  tellWorkerPageIsQuiet
} from './precacheWait';

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('waiting for the page to be quiet', () => {
  it('finishes once nothing has been asked for for the quiet time', async () => {
    let note = () => {};
    let stopped = false;
    const done = vi.fn();
    void afterQuiet(
      (n) => {
        note = n;
        return () => (stopped = true);
      },
      1000,
      10_000
    ).then(done);
    await vi.advanceTimersByTimeAsync(900);
    note(); // another request: the wait starts again
    await vi.advanceTimersByTimeAsync(900);
    expect(done).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(200);
    expect(done).toHaveBeenCalledOnce();
    expect(stopped).toBe(true);
  });

  it('finishes at the longest wait even when requests never stop', async () => {
    let note = () => {};
    const done = vi.fn();
    void afterQuiet(
      (n) => {
        note = n;
        return () => {};
      },
      1000,
      5000
    ).then(done);
    for (let t = 0; t < 4000; t += 500) {
      await vi.advanceTimersByTimeAsync(500);
      note();
    }
    expect(done).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1100);
    expect(done).toHaveBeenCalledOnce();
  });
});

describe('telling the installing worker', () => {
  const quickly = () => () => () => {};
  function container(registration: Partial<ServiceWorkerRegistration> | undefined) {
    return { getRegistration: () => Promise.resolve(registration) } as ServiceWorkerContainer;
  }

  it('posts the message to a worker that is installing for the first time', async () => {
    const postMessage = vi.fn();
    const sent = tellWorkerPageIsQuiet(
      container({ active: null, installing: { postMessage } as unknown as ServiceWorker }),
      (note) => {
        void note;
        return () => {};
      }
    );
    await vi.advanceTimersByTimeAsync(QUIET_MS + 10);
    await sent;
    expect(postMessage).toHaveBeenCalledWith({ type: PAGE_IS_QUIET });
  });

  it('says so when the worker starts installing after the page went quiet, once', async () => {
    const postMessage = vi.fn();
    const listeners: { type: string; run: () => void; once?: boolean }[] = [];
    const registration = {
      active: null,
      installing: null as unknown as ServiceWorker | null,
      waiting: null,
      addEventListener: (type: string, run: () => void, options?: { once?: boolean }) =>
        listeners.push({ type, run, once: options?.once })
    };
    const sent = tellWorkerPageIsQuiet(container(registration as never), () => () => () => {});
    await vi.advanceTimersByTimeAsync(QUIET_MS + 10);
    await sent;
    expect(postMessage).not.toHaveBeenCalled();
    expect(listeners).toHaveLength(1);
    expect(listeners[0]).toMatchObject({ type: 'updatefound', once: true });
    registration.installing = { postMessage } as unknown as ServiceWorker;
    listeners[0]!.run();
    expect(postMessage).toHaveBeenCalledOnce();
    expect(postMessage).toHaveBeenCalledWith({ type: PAGE_IS_QUIET });
  });

  it('says nothing when a worker is already running (an update or a later visit)', async () => {
    const postMessage = vi.fn();
    const sent = tellWorkerPageIsQuiet(
      container({
        active: {} as ServiceWorker,
        installing: { postMessage } as unknown as ServiceWorker
      }),
      quickly()
    );
    await vi.advanceTimersByTimeAsync(QUIET_MS + 10);
    await sent;
    expect(postMessage).not.toHaveBeenCalled();
  });

  it('does nothing where there is no worker or no registration', async () => {
    await tellWorkerPageIsQuiet(null);
    const sent = tellWorkerPageIsQuiet(container(undefined), quickly());
    await vi.advanceTimersByTimeAsync(QUIET_MS + 10);
    await sent;
  });

  it('keeps its waits shorter than the worker’s', () => {
    expect(PAGE_GIVES_UP_MS).toBeLessThan(MAX_WAIT_MS);
  });
});
