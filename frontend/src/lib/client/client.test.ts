import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kitchen } from '#lib/freshness.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import { lastOwnChange, serverUndo, undoToast } from './changes';
import type { UndoResult } from './types';
import { listFoods, patchFood } from './foods';
import { defaultCupMl, settleHousehold } from './household';

type Call = { url: string; method: string; body: unknown; headers: Record<string, string> };

/** Pretend to be the server: answer each call with the next reply. */
function fakeServer(...replies: [number, unknown][]) {
  const calls: Call[] = [];
  vi.stubGlobal('fetch', async (url: string, init: RequestInit = {}) => {
    calls.push({
      url: String(url),
      method: init.method ?? 'GET',
      body: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: (init.headers as Record<string, string>) ?? {}
    });
    const [status, body] = replies.shift() ?? [200, {}];
    return new Response(body === undefined ? null : JSON.stringify(body), { status });
  });
  return calls;
}

afterEach(() => vi.unstubAllGlobals());

describe('foods', () => {
  it('lists with search and filter', async () => {
    const calls = fakeServer([200, { foods: [] }]);
    await listFoods({ q: ' arhar ', filter: 'maybe_same' });
    expect(calls[0]!.url).toBe('/api/v1/foods?q=arhar&filter=maybe_same');
  });

  it('leaves out "all" and empty searches', async () => {
    const calls = fakeServer([200, { foods: [] }]);
    await listFoods({ q: '', filter: 'all' });
    expect(calls[0]!.url).toBe('/api/v1/foods');
  });

  it('saves one field, with the change ID', async () => {
    const calls = fakeServer([200, {}]);
    await patchFood(7, { staple: true }, 'key-1');
    expect(calls[0]).toMatchObject({
      url: '/api/v1/foods/7',
      method: 'PATCH',
      body: { staple: true }
    });
    expect(calls[0]!.headers['idempotency-key']).toBe('key-1');
  });

  it('puts ask-once answers inside an amount, or next to any other field', async () => {
    const answer = {
      kind: 'weight_per_ml' as const,
      food_id: 7,
      grams: 200,
      remember: true
    };
    const calls = fakeServer([200, {}], [200, {}]);
    await patchFood(7, { running_low_at: { amount: 1, unit: 'cup' } }, 'k', [answer]);
    await patchFood(7, { counted_as: 'count' }, 'k2', [answer]);
    expect(calls[0]!.body).toEqual({
      running_low_at: { amount: 1, unit: 'cup', answers: [answer] }
    });
    expect(calls[1]!.body).toEqual({ counted_as: 'count', answers: [answer] });
  });
});

describe('undo on the server', () => {
  const change = { id: 830, summary: 'Undid: Added 1 packet Toor dal' };

  it('says "Undone" when all of it was put back, and tells screens to refresh', async () => {
    const calls = fakeServer([200, { result: 'done', message: 'Undone.', change }]);
    const before = kitchen.version;
    expect(await serverUndo(812)()).toBeUndefined();
    expect(calls[0]).toMatchObject({ url: '/api/v1/changes/812/undo', method: 'POST' });
    expect(kitchen.version).toBe(before + 1);
  });

  it('shows the server’s message when only some could be put back', async () => {
    const message = 'Put back 150 g of the 500 g — the rest has been used since.';
    fakeServer([200, { result: 'partly', message, change }]);
    expect(await serverUndo(812)()).toBe(message);
  });

  it('says so when the Undo brought a removed ingredient back', async () => {
    const message = 'Yogurt is back in Ingredients, with ½ tub in the Fridge.';
    fakeServer([
      200,
      { result: 'done', message, change, brought_back: [{ id: 5, name: 'Yogurt' }] }
    ]);
    expect(await serverUndo(812)()).toBe(message);
    const result = { result: 'done', message, brought_back: [{ id: 5, name: 'Yogurt' }] };
    expect(undoToast('Used about ½ tub Yogurt', result as UndoResult)).toBe(
      'Undone: Used about ½ tub Yogurt. Yogurt is back in Ingredients, with ½ tub in the Fridge.'
    );
  });

  it('the Recent changes toast names the change, or gives the server’s words if partly', () => {
    const done = { result: 'done', message: 'Undone.', brought_back: [] } as unknown as UndoResult;
    expect(undoToast('Used 1 pack Paneer', done)).toBe('Undone: Used 1 pack Paneer');
    const partly = { result: 'partly', message: 'Took back 150 g.', brought_back: [] };
    expect(undoToast('Added Toor dal', partly as unknown as UndoResult)).toBe('Took back 150 g.');
  });

  it('a retry sends the same undo ID, so it never undoes twice', async () => {
    const calls = fakeServer(
      [503, { detail: 'busy' }],
      [200, { result: 'done', message: '', change }]
    );
    const undo = serverUndo(812);
    await expect(undo()).rejects.toThrow();
    await undo();
    expect(calls[1]!.headers['idempotency-key']).toBe(calls[0]!.headers['idempotency-key']);
  });

  it('Ctrl+Z after a reload finds your latest change that can still be undone', async () => {
    const calls = fakeServer([
      200,
      {
        changes: [
          { id: 9, summary: 'Undid: Used milk', can_undo: false, undone: null },
          { id: 8, summary: 'Used 200 g spinach', can_undo: true, undone: null }
        ],
        next: null
      }
    ]);
    const entry = await lastOwnChange();
    expect(calls[0]!.url).toBe('/api/v1/changes?limit=20&mine=true');
    expect(entry?.label).toBe('Used 200 g spinach');
  });

  it('Ctrl+Z after a reload stops at a switch it can’t turn on, and says why (Low 2)', async () => {
    const SAYS = 'Switch it on in Settings › Outside connections.';
    const list = {
      changes: [
        { id: 12, summary: 'Switched recipe import off', can_undo: true, undone: null },
        { id: 8, summary: 'Used 200 g spinach', can_undo: true, undone: null }
      ],
      next: null
    };
    const refused = { code: 'cannot_undo', detail: SAYS };
    const calls = fakeServer([200, list], [409, refused], [200, list], [409, refused]);
    undoHistory.clear();
    undoHistory.fallback = lastOwnChange;
    toasts.dismiss();
    try {
      expect(await undoHistory.undoLast()).toBe(true);
      expect(toasts.current?.message).toBe(SAYS);
      expect(toasts.current?.action).toBeUndefined(); // nothing to try again
      expect(undoHistory.size).toBe(0); // not kept, so the key doesn't go round on it
      // Pressed again: the same answer, one call each time, and never the older change.
      expect(await undoHistory.undoLast()).toBe(true);
      expect(toasts.current?.message).toBe(SAYS);
      const undos = calls.filter((c) => c.method === 'POST').map((c) => c.url);
      expect(undos).toEqual(['/api/v1/changes/12/undo', '/api/v1/changes/12/undo']);
      expect(calls).toHaveLength(4);
    } finally {
      undoHistory.fallback = null;
      toasts.dismiss();
    }
  });
});

describe('first run: time zone and cup size', () => {
  const device = { timeZone: 'Europe/London', language: 'en-GB' };
  const admin = { id: 1, role: 'admin' as const };

  beforeEach(() => sessionStorage.clear());

  it('an admin offers the device time zone and cup size, once per sign-in', async () => {
    const calls = fakeServer([200, {}]);
    expect(await settleHousehold(admin, device)).toBe(true);
    expect(calls[0]).toMatchObject({
      url: '/api/v1/household/fill-from-browser',
      method: 'POST',
      body: { time_zone: 'Europe/London', cup_ml: 250 }
    });
    expect(await settleHousehold(admin, device)).toBe(false);
    expect(calls).toHaveLength(1);
  });

  it('a member never sends it', async () => {
    const calls = fakeServer();
    expect(await settleHousehold({ id: 2, role: 'member' }, device)).toBe(false);
    expect(calls).toHaveLength(0);
  });

  it('US English gets a 240 ml cup; everyone else 250 ml', () => {
    expect(defaultCupMl('en-US')).toBe(240);
    expect(defaultCupMl('en-GB')).toBe(250);
    expect(defaultCupMl('ta-IN')).toBe(250);
  });
});
