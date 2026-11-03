import { afterEach, describe, expect, it, vi } from 'vitest';
import { eatLeftover, type Placed } from './eatLeftover';
import { fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';

const TUB = {
  id: 41,
  recipe_name: 'Banana bread',
  cooked_on: '2026-11-02',
  use_by: '2026-11-05'
};

describe('"Eat it on…" refused after Cooked it was saved (F128)', () => {
  afterEach(() => {
    toasts.dismiss();
    vi.unstubAllGlobals();
  });

  it('says plainly that the cooking is saved and the tub stays in Tubs left, with the server’s reason', async () => {
    fakeApi({
      'GET /plan/tubs-left': [200, { tubs: [TUB], more: false }],
      'POST /plan/tubs/41/place': [
        409,
        { code: 'after_use_by', detail: 'That is after the use-by date of this batch.' }
      ]
    });
    const placed: Placed = { undo: null };
    await eatLeftover(placed, 'Banana bread', '2026-11-02', 1, {
      day: '2026-11-07',
      slotId: 3
    });
    expect(placed.undo).toBeNull();
    expect(toasts.current?.tone).toBe('problem');
    expect(toasts.current?.message).toBe(
      'Cooked it is saved, but the tub isn’t planned. That is after the use-by date of this batch. It stays in Tubs left.'
    );
  });
});
