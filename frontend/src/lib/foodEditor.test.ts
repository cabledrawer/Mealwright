import { describe, expect, it, vi } from 'vitest';
import { FoodModel } from './foodEditor.svelte';
import type { Food } from './client/types';

const food = (id: number, name: string) => ({ id, name }) as Food;

/** Answers for each GET /foods/{id} that the test finishes by hand, in any order. */
function slowFoods() {
  const waiting: { resolve: (r: Response) => void }[] = [];
  vi.stubGlobal('fetch', () => new Promise<Response>((resolve) => waiting.push({ resolve })));
  const answer = (index: number, status: number, body: unknown) =>
    waiting[index]!.resolve(new Response(JSON.stringify(body), { status }));
  return { answer, asked: () => waiting.length };
}

describe('FoodModel.load', () => {
  it('ignores an older answer that arrives after a newer load began', async () => {
    const { answer, asked } = slowFoods();
    const model = new FoodModel(1);
    const first = model.load();
    const second = model.load();
    await vi.waitFor(() => expect(asked()).toBe(2));
    // The newer answer comes first, the older one after it.
    answer(1, 200, food(1, 'Toor dal (new)'));
    await second;
    answer(0, 200, food(1, 'Toor dal (old)'));
    await first;
    expect(model.food?.name).toBe('Toor dal (new)');
    expect(model.problem).toBeNull();
    vi.unstubAllGlobals();
  });

  it('ignores an older failure after a newer success', async () => {
    const { answer, asked } = slowFoods();
    const model = new FoodModel(1);
    const first = model.load();
    const second = model.load();
    await vi.waitFor(() => expect(asked()).toBe(2));
    answer(1, 200, food(1, 'Toor dal'));
    await second;
    answer(0, 500, { detail: 'Something went wrong.' });
    await first;
    expect(model.food?.name).toBe('Toor dal');
    expect(model.problem).toBeNull();
    vi.unstubAllGlobals();
  });

  it('still takes a lone answer, and says so when the food is gone', async () => {
    const { answer, asked } = slowFoods();
    const model = new FoodModel(1);
    const only = model.load();
    await vi.waitFor(() => expect(asked()).toBe(1));
    answer(0, 404, { detail: 'Not found.' });
    await only;
    expect(model.problem).toBe('This ingredient isn’t here any more.');
    vi.unstubAllGlobals();
  });
});
