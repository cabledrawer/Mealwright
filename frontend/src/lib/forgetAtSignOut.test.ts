import { describe, expect, it } from 'vitest';
import { sessionEnded } from './api';
import { askOnce } from './askOnce.svelte';
import { cookNow } from './cookNow.svelte';
import { cookPrefs } from './cookPrefs.svelte';
import { forgetAll } from './forgetAll';
import { methodAsk } from './methodAsk.svelte';
import { newIngredient } from './newIngredient.svelte';
import { runWipeHooks } from './offline/wipeHooks';
import { optionalAsk } from './optionalAsk.svelte';
import { RecipeDraft } from './recipes/draft.svelte';
import { editorKey, keep, reopen, takeKept } from './recipes/stash';
import { startAsk } from './startAsk.svelte';

describe('another person signing in (the browser is wiped)', () => {
  it('Cook now forgets the meal, the plan item and the words', () => {
    cookNow.mealId = 5;
    cookNow.itemId = 6;
    cookNow.recipeId = 7;
    cookNow.text = 'Planned for Sam’s dinner';
    cookNow.canUndo = true;
    runWipeHooks();
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
    runWipeHooks();
    expect(cookPrefs.perStep).toBe(false);
    expect(cookPrefs.problem).toBeNull();
  });

  it('a cancelled recipe editor is not kept for the next person', () => {
    keep(editorKey(123), new RecipeDraft());
    runWipeHooks();
    expect(reopen(editorKey(123))).toBe(false);
    expect(takeKept(editorKey(123))).toBeNull();
  });
});

describe('the same person signing in again after a session ended mid-cook', () => {
  it('keeps Cook now (Cooked it, the notice and its Undo), the cook switch and the editor', () => {
    cookNow.mealId = 5;
    cookNow.itemId = 6;
    cookNow.recipeId = 7;
    cookNow.text = 'Planned for tonight';
    cookNow.canUndo = true;
    cookPrefs.perStep = true;
    const draft = new RecipeDraft();
    keep(editorKey(9), draft);
    sessionEnded(); // a 401: nothing is wiped, the same login comes back
    expect([cookNow.mealId, cookNow.itemId, cookNow.recipeId]).toEqual([5, 6, 7]);
    expect(cookNow.text).toBe('Planned for tonight');
    expect(cookNow.canUndo).toBe(true);
    expect(cookPrefs.perStep).toBe(true);
    expect(reopen(editorKey(9))).toBe(true);
    expect(takeKept(editorKey(9))).toBe(draft);
    runWipeHooks(); // another person: gone
    expect(cookNow.mealId).toBeNull();
  });
});

describe('a question waiting in a dialog', () => {
  it('is answered "no" and dropped when a session ends, so it does not show after the next sign-in', async () => {
    const asked = askOnce.ask({
      food_id: 1,
      food_name: 'Sam’s secret ingredient',
      kind: 'item_weight',
      question: 'How much does one weigh?',
      unit: 'g',
      per: 'item',
      cup_ml: 250,
      suggested: null,
      name: null
    } as never);
    expect(askOnce.current).not.toBeNull();
    sessionEnded();
    expect(askOnce.current).toBeNull();
    expect(await asked).toBeNull();
  });

  it('all five dialogs are dropped by the wipe and by the session end (forgetAll runs both)', () => {
    const stores = [askOnce, methodAsk, startAsk, optionalAsk, newIngredient] as const;
    for (const end of [runWipeHooks, sessionEnded, forgetAll]) {
      for (const store of stores) store.current = { resolve: () => {} } as never;
      end();
      for (const store of stores) expect(store.current, String(end)).toBeNull();
    }
  });
});
