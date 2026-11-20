// A part whose code fails to load is retried (cabledrawer 15 Nov): the toast says "Couldn’t open
// that. Try again.", the ask ends as if cancelled, and the next open fetches the code again.

import type { Component } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fetchCode, LazyCode } from './lazyCode.svelte';
import { methodAsk } from './methodAsk.svelte';
import { network } from './network.svelte';
import { optionalAsk } from './optionalAsk.svelte';
import { session } from './session.svelte';
import { startAsk } from './startAsk.svelte';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';
import { whosThis } from './whosThis.svelte';

const fake = {} as Component;
const WORDS = 'Couldn’t open that. Try again.';
type Loader = () => Promise<{ default: Component }>;
const failsOnce = () =>
  vi.fn<Loader>().mockRejectedValueOnce(new Error('offline')).mockResolvedValue({ default: fake });

const line = (id: number, optional: boolean) => ({
  id,
  kind: 'ingredient',
  words: 'Thing',
  amount: 1,
  amount_text: '1',
  unit: 'kg',
  size: null,
  food: null,
  recipe: null,
  link: 'none',
  note: null,
  optional
});
const RECIPE = {
  id: 5,
  name: 'Curry',
  serves: 4,
  lines: [line(1, false), line(2, true)],
  steps: [],
  methods: [
    { id: 10, name: 'Stovetop', time_minutes: 45, used_last: false },
    { id: 11, name: 'Instant Pot', time_minutes: 30, used_last: true }
  ],
  second_method: null
};
const STOCK = { lines: [], counted: 0, missing: 0, stock_unchecked: false };
const START = {
  wait: { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false },
  eats_at: '08:00',
  options: [{ day: '2026-11-13', time: '21:00', ready_by: '08:00', ready_by_day: '2026-11-14' }]
};

const originals = {
  method: optionalAsk.methodCode.loader,
  optional: optionalAsk.optionalCode.loader,
  start: optionalAsk.startCode.loader,
  whos: whosThis.code.loader
};

beforeEach(() => {
  network.reset();
  toasts.dismiss();
  for (const lazy of [
    optionalAsk.methodCode,
    optionalAsk.optionalCode,
    optionalAsk.startCode,
    whosThis.code
  ]) {
    lazy.code = null;
  }
});
afterEach(() => {
  methodAsk.dismiss();
  optionalAsk.dismiss();
  startAsk.dismiss();
  whosThis.forget();
  optionalAsk.methodCode.loader = originals.method;
  optionalAsk.optionalCode.loader = originals.optional;
  optionalAsk.startCode.loader = originals.start;
  whosThis.code.loader = originals.whos;
  session.me = null;
  toasts.dismiss();
  vi.unstubAllGlobals();
  network.reset();
});

describe('LazyCode', () => {
  it('forgets a failed fetch, says so, and fetches again next time', async () => {
    const loader = failsOnce();
    const lazy = new LazyCode(loader);
    const failed = vi.fn();
    lazy.load(failed);
    await vi.waitFor(() => expect(failed).toHaveBeenCalledTimes(1));
    expect(lazy.code).toBeNull();
    expect(toasts.current?.message).toBe(WORDS);
    lazy.load(failed);
    expect(await lazy.code).toBe(fake);
    expect(loader).toHaveBeenCalledTimes(2);
  });
});

describe('the plan method sheet', () => {
  it('ends as cancelled with a toast when its code fails, then opens next time', async () => {
    fakeApi({ 'GET /recipes/5': [200, RECIPE] });
    const loader = failsOnce();
    optionalAsk.methodCode.loader = loader;
    expect(await methodAsk.ask({ id: 5 }, 'Sat dinner')).toBeNull();
    expect(methodAsk.current).toBeNull();
    expect(optionalAsk.methodOpen).toBe(false);
    expect(toasts.current?.message).toBe(WORDS);

    const second = methodAsk.ask({ id: 5 }, 'Sat dinner');
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    expect(loader).toHaveBeenCalledTimes(2);
    expect(await optionalAsk.methodCode.code).toBe(fake);
    methodAsk.answer(10);
    expect(await second).toBe(10);
  });
});

describe('the optional ingredients sheet', () => {
  it('ends as cancelled with a toast when its code fails, then opens next time', async () => {
    fakeApi({ 'GET /recipes/5': [200, RECIPE], 'GET /recipes/5/stock': [200, STOCK] });
    const loader = failsOnce();
    optionalAsk.optionalCode.loader = loader;
    expect(await optionalAsk.ask({ id: 5 }, 'Sat dinner')).toBeNull();
    expect(optionalAsk.current).toBeNull();
    expect(toasts.current?.message).toBe(WORDS);

    const second = optionalAsk.ask({ id: 5 }, 'Sat dinner');
    await vi.waitFor(() => expect(optionalAsk.current).not.toBeNull());
    expect(loader).toHaveBeenCalledTimes(2);
    expect(await optionalAsk.optionalCode.code).toBe(fake);
    optionalAsk.answer([2]);
    expect(await second).toEqual([2]);
  });
});

describe('the start time sheet', () => {
  const meal = { day: '2026-11-14', slotId: 1, slotName: 'Breakfast' };
  it('ends as cancelled with a toast when its code fails, then opens next time', async () => {
    fakeApi({ 'GET /plan/start-options': [200, START] });
    const loader = failsOnce();
    optionalAsk.startCode.loader = loader;
    expect(await startAsk.ask({ id: 5, name: 'Dosa' }, meal)).toBeNull();
    expect(startAsk.current).toBeNull();
    expect(optionalAsk.startOpen).toBe(false);
    expect(toasts.current?.message).toBe(WORDS);

    const second = startAsk.ask({ id: 5, name: 'Dosa' }, meal);
    await vi.waitFor(() => expect(startAsk.current).not.toBeNull());
    expect(loader).toHaveBeenCalledTimes(2);
    expect(await optionalAsk.startCode.code).toBe(fake);
    startAsk.answer({ day: '2026-11-13', time: '21:00' });
    expect(await second).toEqual({ day: '2026-11-13', time: '21:00' });
  });
});

describe('Who’s this?', () => {
  it('stays shut with a toast when its code fails, then opens next time', async () => {
    session.me = {
      id: 9,
      name: 'Kitchen tablet',
      username: 'tablet',
      role: 'member',
      theme: 'auto',
      member_id: 9,
      shared: true
    };
    whosThis.forget();
    fakeApi({
      'GET /whos-this': [
        200,
        { ask: true, picked: null, people: [{ id: 1, name: 'Tess', colour: null }] }
      ]
    });
    const loader = failsOnce();
    whosThis.code.loader = loader;
    await whosThis.check();
    await vi.waitFor(() => expect(toasts.current?.message).toBe(WORDS));
    expect(whosThis.open).toBe(false);

    await whosThis.check();
    expect(whosThis.open).toBe(true);
    expect(loader).toHaveBeenCalledTimes(2);
    expect(await whosThis.code.code).toBe(fake);
  });
});

describe('fetchCode', () => {
  it('says so with a real Try again button that fetches again, and forgets the failure', async () => {
    const loader = failsOnce();
    expect(await fetchCode(loader)).toBeNull();
    expect(toasts.current?.message).toBe(WORDS);
    expect(toasts.current?.action?.label).toBe('Try again');
    toasts.act();
    await vi.waitFor(() => expect(loader).toHaveBeenCalledTimes(2));
    expect(await fetchCode(loader)).toEqual({ default: fake });
  });

  it('Try again asks the ask again when the caller gives it', async () => {
    const again = vi.fn();
    expect(await fetchCode(failsOnce(), again)).toBeNull();
    toasts.act();
    expect(again).toHaveBeenCalledTimes(1);
  });
});
