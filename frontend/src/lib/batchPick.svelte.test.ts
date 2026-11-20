import { afterEach, describe, expect, it, vi } from 'vitest';
import { BatchPickModel } from './batchPick.svelte';
import type { BatchSuggestions } from './client/batch';
import { fakeApi } from '#lib/testing/fakeApi.js';

const pick = (id: number, name: string) => ({
  recipe_id: id,
  name,
  minutes: 30,
  why: 'Fits your kitchen.',
  use_soon: null
});

const answer = (ids: number[], extra: Partial<BatchSuggestions> = {}): BatchSuggestions => ({
  date: '2026-11-15',
  count: 3,
  picks: ids.map((id) => pick(id, `Recipe ${id}`)),
  together_minutes: 60,
  one_by_one_minutes: 90,
  pool: 6,
  free_days: ['2026-11-15', '2026-11-16', '2026-11-21'],
  kitchen: { hob_rings: 4, pressure_cookers: 1, oven: true, asked: true },
  ...extra
});

describe('Batch cook picks', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('asks for the default day first, then the day the person chose stays', async () => {
    const asked = fakeApi({ 'GET /batch-cook/suggestions': [200, answer([1, 2, 3])] });
    const model = new BatchPickModel();
    await model.load();
    expect(asked[0]!.url).toBe('/batch-cook/suggestions?count=3');
    expect(model.cookDay).toBe('2026-11-15');
    expect(model.chips).toEqual(['2026-11-15', '2026-11-16', '2026-11-21']);
    model.setDay('2026-11-30'); // "Other…"
    expect(model.cookDay).toBe('2026-11-30');
    expect(model.chips[0]).toBe('2026-11-30');
  });

  it('a swap keeps the others and skips the swapped one, and again does not bring it back', async () => {
    const asked = fakeApi({
      'GET /batch-cook/suggestions': (r) =>
        r.url.includes('skip=2') ? [200, answer([1, 4, 3])] : [200, answer([1, 2, 3])]
    });
    const model = new BatchPickModel();
    await model.load();
    await model.swap(2);
    expect(asked.at(-1)!.url).toBe('/batch-cook/suggestions?count=3&keep=1&keep=3&skip=2');
    expect(model.picks.map((p) => p.recipe_id)).toEqual([1, 4, 3]);
    await model.swap(4);
    expect(asked.at(-1)!.url).toContain('skip=2&skip=4');
  });

  it('Show me others skips the whole last set', async () => {
    const asked = fakeApi({ 'GET /batch-cook/suggestions': [200, answer([1, 2, 3])] });
    const model = new BatchPickModel();
    await model.load();
    await model.others();
    expect(asked.at(-1)!.url).toBe('/batch-cook/suggestions?count=3&skip=1&skip=2&skip=3');
  });

  it('a new count keeps the picks that fit', async () => {
    const asked = fakeApi({ 'GET /batch-cook/suggestions': [200, answer([1, 2, 3])] });
    const model = new BatchPickModel();
    await model.load();
    await model.setCount(2);
    expect(asked.at(-1)!.url).toBe('/batch-cook/suggestions?count=2&keep=1&keep=2');
    await model.setCount(4);
    expect(asked.at(-1)!.url).toContain('count=4');
  });

  it('Change starts from the session’s own recipes and day', async () => {
    const asked = fakeApi({ 'GET /batch-cook/suggestions': [200, answer([7, 8])] });
    const model = new BatchPickModel();
    await model.startFrom('2026-11-16', [7, 8]);
    expect(asked[0]!.url).toBe('/batch-cook/suggestions?date=2026-11-16&count=2&keep=7&keep=8');
    expect(model.count).toBe(2);
  });

  it('says so when it can not find recipes, and keeps what it had', async () => {
    fakeApi({ 'GET /batch-cook/suggestions': [500, { detail: 'x' }] });
    const model = new BatchPickModel();
    await model.load();
    expect(model.problem).toBe('Couldn’t find recipes. Try again.');
    expect(model.result).toBeNull();
    expect(model.loading).toBe(false);
  });

  it('shows the server’s words when an admin has hidden Batch cook', async () => {
    fakeApi({
      'GET /batch-cook/suggestions': [
        409,
        { code: 'batch_cook_hidden', detail: 'Batch cook is switched off.' }
      ]
    });
    const model = new BatchPickModel();
    await model.load();
    expect(model.problem).toBe('Batch cook is switched off.');
  });
});
