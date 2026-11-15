import { describe, expect, it } from 'vitest';
import { sessionEnded } from './api';
import { cookNow } from './cookNow.svelte';
import { cookPrefs } from './cookPrefs.svelte';
import { runWipeHooks } from './offline/wipeHooks';
import { RecipeDraft } from './recipes/draft.svelte';
import { editorKey, keep, reopen, takeKept } from './recipes/stash';

const ends = [
  ['the browser is wiped at sign-out', runWipeHooks],
  ['the session ends', sessionEnded]
] as const;

describe.each(ends)('when %s', (_what, end) => {
  it('Cook now forgets the meal, the plan item and the words', () => {
    cookNow.mealId = 5;
    cookNow.itemId = 6;
    cookNow.recipeId = 7;
    cookNow.text = 'Planned for Sam’s dinner';
    cookNow.canUndo = true;
    end();
    expect([cookNow.mealId, cookNow.itemId, cookNow.recipeId, cookNow.text]).toEqual([
      null,
      null,
      null,
      null
    ]);
    expect(cookNow.canUndo).toBe(false);
  });

  it('the cook switches forget the last household’s setting', () => {
    cookPrefs.perStep = true;
    cookPrefs.problem = 'something';
    end();
    expect(cookPrefs.perStep).toBe(false);
    expect(cookPrefs.problem).toBeNull();
  });

  it('a cancelled recipe editor is not kept for the next person', () => {
    keep(editorKey(123), new RecipeDraft());
    end();
    expect(reopen(editorKey(123))).toBe(false);
    expect(takeKept(editorKey(123))).toBeNull();
  });
});
