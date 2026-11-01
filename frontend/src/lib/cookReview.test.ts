import { afterEach, describe, expect, it, vi } from 'vitest';
import { undoAll } from './cookReview.svelte';

const outcome = (id: number, canUndo = true) =>
  ({
    ok: true as const,
    value: {
      change: { id, can_undo: canUndo, summary: 'Cooked it' },
      cooked: []
    }
  }) as never;

describe('one Undo for what was taken from the pantry', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('undoes every change the review made, and says what the server said about the last one', async () => {
    const asked: string[] = [];
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      asked.push(`${init.method} ${url}`);
      return new Response(
        JSON.stringify({
          result: url.includes('/7/') ? 'partly' : 'done',
          message: url.includes('/7/') ? 'Put back 150 g of the 200 g.' : 'Done',
          change: { id: 99 },
          undone: null,
          groups: [],
          food: null
        }),
        { status: 200, headers: { 'content-type': 'application/json' } }
      );
    });
    const undo = undoAll([outcome(5), outcome(6, false), outcome(7)]);
    expect(await undo()).toBe('Put back 150 g of the 200 g.');
    // The one that cannot be undone is left out.
    expect(asked).toEqual(['POST /api/v1/changes/5/undo', 'POST /api/v1/changes/7/undo']);
  });
});
