// The cook page's "begun" step and the Batch cook way question, when their code fails to load
// (B4, cabledrawer 15 Nov): the toast says so, nothing is marked or planned, the next try fetches.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanItem } from './client/plan';
import { askBatchMethod, markWaitBegun } from './lazyActions';
import { loaders } from './lazyModules';
import { methodAsk } from './methodAsk.svelte';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';

const WORDS = 'Couldn’t open that. Try again.';
const original = { ...loaders };
const METHODS = [
  { id: 10, name: 'Stovetop', time_minutes: 45, used_last: false },
  { id: 11, name: 'Instant Pot', time_minutes: 30, used_last: true }
];
const CURRY = { id: 5, name: 'Curry', serves: 4, lines: [], steps: [], methods: METHODS };
const item = { id: 77, recipe: { id: 5, name: 'Masala dosa' }, ahead: { step_id: 3 } } as PlanItem;

beforeEach(() => toasts.dismiss());
afterEach(() => {
  Object.assign(loaders, original);
  methodAsk.dismiss();
  toasts.dismiss();
  vi.unstubAllGlobals();
});

describe('markWaitBegun', () => {
  function startNowFailingOnce() {
    const markStarted = vi.fn().mockResolvedValue({ ok: true });
    const load = vi
      .fn<() => Promise<unknown>>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ markStarted });
    (loaders as Record<string, unknown>).startNow = load;
    return { markStarted, load };
  }

  it('marks nothing, does not reload and toasts when its code fails; the next step tries again', async () => {
    const { markStarted, load } = startNowFailingOnce();
    const reload = vi.fn().mockResolvedValue(undefined);
    await markWaitBegun(item, false, reload);
    expect(toasts.current?.message).toBe(WORDS);
    expect(markStarted).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();

    await markWaitBegun(item, false, reload);
    expect(load).toHaveBeenCalledTimes(2);
    expect(markStarted).toHaveBeenCalledWith(77, 'Masala dosa', { withUndo: false });
    expect(reload).toHaveBeenCalledTimes(1);
  });

  it('does nothing, and fetches nothing, offline or for an item with no wait', async () => {
    const { load } = startNowFailingOnce();
    const reload = vi.fn();
    await markWaitBegun(item, true, reload);
    await markWaitBegun({ ...item, ahead: null } as PlanItem, false, reload);
    await markWaitBegun(null, false, reload);
    expect(load).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    expect(toasts.current).toBeNull();
  });
});

describe('askBatchMethod', () => {
  it('answers null (as if cancelled) and toasts when its code fails; the next try asks', async () => {
    fakeApi({ 'GET /recipes/5': [200, CURRY] });
    const spy = vi
      .fn<() => Promise<unknown>>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockImplementation(original.methodAsk);
    (loaders as Record<string, unknown>).methodAsk = spy;
    expect(await askBatchMethod(5, 'Sun 15')).toBeNull();
    expect(toasts.current?.message).toBe(WORDS);

    const again = askBatchMethod(5, 'Sun 15');
    await vi.waitFor(() => expect(methodAsk.current).not.toBeNull());
    expect(spy).toHaveBeenCalledTimes(2);
    methodAsk.answer(10);
    expect(await again).toBe(10);
  });
});
