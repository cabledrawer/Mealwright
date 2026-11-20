import { afterEach, describe, expect, it } from 'vitest';
import { undoFromList } from './client/changes';
import type { Change } from './client/types';
import { kitchen } from './freshness.svelte';
import { changeOf, fakeApi } from './testing/fakeApi';
import { toasts } from './toast.svelte';

// F125 (cabledrawer 3 Nov): "Undo of "Cooked it" from Recent changes must also undo the
// meal's "Cooked" (one change, one Undo, as the toast does)." The server takes the meal's
// Cooked back with the pantry's; the list asks once and the screens fetch again.
const COOKED = { ...changeOf(70, 'Cooked Dal curry'), kind: 'cooked' } as Change;
const paths = (requests: { method: string; path: string }[]) =>
  requests.map((r) => `${r.method} ${r.path}`);

describe('Undo of Cooked it in Settings › Recent changes', () => {
  afterEach(() => toasts.dismiss());

  it('is one Undo: one request, the row loses its Undo, and Today and the Plan fetch again', async () => {
    const requests = fakeApi({
      'POST /changes/70/undo': [
        200,
        { result: 'done', message: 'Undone.', brought_back: [], undone: COOKED }
      ]
    });
    const list = { changes: [COOKED] };
    const before = kitchen.version;
    await undoFromList(COOKED, list);
    expect(paths(requests)).toEqual(['POST /changes/70/undo']);
    expect(list.changes[0]?.can_undo).toBe(false);
    expect(kitchen.version).toBeGreaterThan(before);
    expect(toasts.current?.message).toBe('Undone: Cooked Dal curry');
  });

  it('says so when the pantry could only be partly put back', async () => {
    fakeApi({
      'POST /changes/70/undo': [
        200,
        {
          result: 'partly',
          message: 'Put back 150 g of the 200 g.',
          brought_back: [],
          undone: COOKED
        }
      ]
    });
    await undoFromList(COOKED, { changes: [COOKED] });
    expect(toasts.current?.message).toBe('Put back 150 g of the 200 g.');
  });
});
