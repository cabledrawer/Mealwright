import { afterEach, describe, expect, it, vi } from 'vitest';
import { CookReview } from './cookReview.svelte';

// One Cooked it for a whole Batch cook session (B3): one preview and one confirm for every
// recipe, so one change and one Undo.

const proposal = (name: string) => ({
  recipe: { id: 1, name },
  portions: 4,
  servings: 4,
  rows: []
});

const target = {
  title: 'Cooked it · Sun 15 Nov',
  subtitle: 'Sambar and Chicken chettinad',
  mealId: null,
  sessionId: 9,
  parts: [
    { itemId: null, batchId: 11, name: 'Sambar' },
    { itemId: null, batchId: 12, name: 'Chicken chettinad' }
  ]
};

describe('the one Cooked it review for a session', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('asks once for every recipe and keeps each one’s tubs', async () => {
    const asked: { url: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      asked.push({ url, body: JSON.parse(String(init.body)) });
      return new Response(
        JSON.stringify({
          session_id: 9,
          cook_day: '2026-11-15',
          items: [
            {
              batch_id: 11,
              recipe_name: 'Sambar',
              tub_count: 3,
              tubs: [{ place: 'Fridge', count: 3 }],
              proposal: proposal('Sambar')
            },
            {
              batch_id: 12,
              recipe_name: 'Chicken chettinad',
              tub_count: 4,
              tubs: [
                { place: 'Freezer', count: 2 },
                { place: 'Fridge', count: 2 }
              ],
              proposal: proposal('Chicken chettinad')
            }
          ]
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    });
    const review = new CookReview();
    await review.open(target);
    expect(asked.map((a) => a.url)).toEqual(['/api/v1/batch-cook/sessions/9/cook/preview']);
    expect(review.tabs[0]!.proposal?.recipe.name).toBe('Sambar');
    expect(review.tabs[1]!.tubs).toEqual([
      { place: 'Freezer', count: 2 },
      { place: 'Fridge', count: 2 }
    ]);
  });

  it('confirms with one call, one change', async () => {
    const asked: string[] = [];
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      asked.push(`${init.method} ${url}`);
      if (url.endsWith('/preview'))
        return new Response(JSON.stringify({ session_id: 9, cook_day: '2026-11-15', items: [] }), {
          status: 200,
          headers: { 'content-type': 'application/json' }
        });
      return new Response(
        JSON.stringify({ change: { id: 70, can_undo: true, summary: 'Cooked it' }, cooked: [] }),
        { status: 201, headers: { 'content-type': 'application/json' } }
      );
    });
    const review = new CookReview();
    await review.open(target);
    const { ok } = await review.confirm();
    expect(ok).toBe(true);
    expect(asked.filter((a) => a.endsWith('/cook'))).toEqual([
      'POST /api/v1/batch-cook/sessions/9/cook'
    ]);
    expect(asked.some((a) => a.includes('/plan/'))).toBe(false);
  });
});
