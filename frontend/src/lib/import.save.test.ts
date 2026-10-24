import { afterEach, describe, expect, it } from 'vitest';
import { drafts } from './drafts.svelte';
import { changesToast } from './import.save';
import { changeOf, fakeApi } from './testing/fakeApi';
import { undoHistory } from './undo.svelte';

const SAVED = {
  recipe: { id: 55, name: 'Aloo paratha' },
  change: changeOf(60, 'Imported Aloo paratha'),
  new_ingredients: [],
  learned: 0
};

describe('the Undo after a Save', () => {
  afterEach(() => {
    undoHistory.clear();
    drafts.forget();
  });

  it('asks for the Drafts list again, because a draft the Save used comes back with it', async () => {
    drafts.loaded = true;
    const requests = fakeApi({
      'POST /changes/60/undo': [200, { result: 'done', message: 'Undone.' }],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    changesToast(SAVED);
    await undoHistory.undoLast();
    await Promise.resolve();
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual([
      'POST /changes/60/undo',
      'GET /recipes/drafts'
    ]);
  });

  it('does not fetch the list when no list has been looked at', async () => {
    const requests = fakeApi({
      'POST /changes/60/undo': [200, { result: 'done', message: 'Undone.' }]
    });
    changesToast(SAVED);
    await undoHistory.undoLast();
    expect(requests.map((r) => r.path)).toEqual(['/changes/60/undo']);
  });
});
