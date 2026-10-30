import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { flushSync } from 'svelte';
import { OFFLINE_AFTER_MS, network } from './network.svelte';

// The layout starts the network watch inside an $effect ((app)/+layout.svelte). start() must
// not read any state, or each offline event would run that effect again: the watch stops and
// starts, the bar's timer is lost, and the bar never shows (found by live.spec.ts in B3).

beforeEach(() => {
  vi.useFakeTimers();
  network.reset();
});

afterEach(() => {
  network.reset();
  vi.useRealTimers();
});

it('started in an $effect, the browser going offline shows the bar after 3 seconds, once', () => {
  let starts = 0;
  const stopRoot = $effect.root(() => {
    $effect(() => {
      starts++;
      return network.start(() => {});
    });
  });
  flushSync();
  window.dispatchEvent(new Event('offline'));
  flushSync();
  vi.advanceTimersByTime(OFFLINE_AFTER_MS);
  flushSync();
  expect(starts).toBe(1);
  expect(network.deviceOffline).toBe(true);
  expect(network.offline).toBe(true);
  stopRoot();
});
