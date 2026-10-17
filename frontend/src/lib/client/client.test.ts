import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { kitchen } from '$lib/freshness.svelte';
import { lastOwnChange, serverUndo } from './changes';
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

  it("shows the server's message when only some could be put back", async () => {
    const message = 'Put back 150 g of the 500 g — the rest has been used since.';
    fakeServer([200, { result: 'partly', message, change }]);
    expect(await serverUndo(812)()).toBe(message);
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
});

describe('first run: time zone and cup size', () => {
  const device = { timeZone: 'Europe/London', language: 'en-GB' };
  const admin = { id: 1, role: 'admin' as const };

  beforeEach(() => sessionStorage.clear());

  it('an admin offers the device time zone and cup size, once per sign-in', async () => {
    const calls = fakeServer([200, {}]);
    expect(await settleHousehold(admin, device)).toBe(true);
    expect(calls[0]).toMatchObject({
      url: '/api/v1/household/from-browser',
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
