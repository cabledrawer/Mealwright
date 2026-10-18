import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BACK_ONLINE, OFFLINE_AFTER_MS, network, offlineText } from './network.svelte';
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

  it('shows after 3 seconds of failing, then "Back online" when it works again', () => {
    network.failed();
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    expect(network.offline).toBe(true);
    network.succeeded();
    expect(network.offline).toBe(false);
    expect(toasts.current?.message).toBe(BACK_ONLINE);
    expect(BACK_ONLINE).toBe('Back online'); // PR 6 adds " — all saved" when it is true
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
      detail: "3 changes waiting. They'll save when you're back."
    });
    expect(offlineText('desktop', 1).detail).toBe(
      "1 change waiting. They'll save when you're back."
    );
  });

  it('nothing in PR 5 sets the waiting count above 0', () => {
    expect(network.waiting).toBe(0);
  });
});
