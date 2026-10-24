import { afterEach, describe, expect, it } from 'vitest';
import { lastOwnChange, undoFromList } from './client/changes';
import type { Change } from './client/types';
import { drafts } from './drafts.svelte';
import { changesToast } from './import.save';
import { changeOf, fakeApi } from './testing/fakeApi';
import { undoHistory } from './undo.svelte';

const IMPORT = { ...changeOf(60, 'Imported Aloo paratha'), kind: 'recipe_imported' };
const SAVED = {
  recipe: { id: 55, name: 'Aloo paratha' },
  change: IMPORT,
  new_ingredients: [],
  learned: 0
};
const undone = (change: { kind: string }) => ({
  result: 'done',
  message: 'Undone.',
  brought_back: [],
  undone: change
});
const LIST_AGAIN = 'GET /recipes/drafts';
const paths = (requests: { method: string; path: string }[]) =>
  requests.map((r) => `${r.method} ${r.path}`);

describe('the Undo of an import brings a draft back, so the Drafts list is fetched again', () => {
  afterEach(() => {
    undoHistory.clear();
    drafts.forget();
  });

  it('after the Undo in the Save toast (or Ctrl+Z straight after)', async () => {
    drafts.loaded = true;
    const requests = fakeApi({
      'POST /changes/60/undo': [200, undone(IMPORT)],
      [LIST_AGAIN]: [200, { drafts: [], count: 0 }]
    });
    changesToast(SAVED);
    await undoHistory.undoLast();
    await Promise.resolve();
    expect(paths(requests)).toEqual(['POST /changes/60/undo', LIST_AGAIN]);
  });

  it('after the Undo in Recent changes', async () => {
    drafts.loaded = true;
    const requests = fakeApi({
      'POST /changes/60/undo': [200, undone(IMPORT)],
      [LIST_AGAIN]: [200, { drafts: [], count: 0 }]
    });
    await undoFromList(IMPORT as Change, { changes: [IMPORT as Change] });
    await Promise.resolve();
    expect(paths(requests)).toEqual(['POST /changes/60/undo', LIST_AGAIN]);
  });

  it('after Ctrl+Z following a reload', async () => {
    drafts.loaded = true;
    const requests = fakeApi({
      'GET /changes': [200, { changes: [IMPORT], next: null }],
      'POST /changes/60/undo': [200, undone(IMPORT)],
      [LIST_AGAIN]: [200, { drafts: [], count: 0 }]
    });
    const entry = await lastOwnChange();
    await entry!.undo();
    await Promise.resolve();
    expect(paths(requests)).toEqual(['GET /changes', 'POST /changes/60/undo', LIST_AGAIN]);
  });

  it('not when no list has been looked at', async () => {
    const requests = fakeApi({ 'POST /changes/60/undo': [200, undone(IMPORT)] });
    changesToast(SAVED);
    await undoHistory.undoLast();
    expect(paths(requests)).toEqual(['POST /changes/60/undo']);
  });

  it('not after the Undo of something else', async () => {
    drafts.loaded = true;
    const other = changeOf(61, 'Used 200 g spinach');
    const requests = fakeApi({ 'POST /changes/61/undo': [200, undone(other)] });
    await undoFromList(other as Change, { changes: [other as Change] });
    await Promise.resolve();
    expect(paths(requests)).toEqual(['POST /changes/61/undo']);
  });
});
