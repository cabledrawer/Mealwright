import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The module reads the stored choice once, when it is first used, so each test loads it afresh.
async function fresh() {
  vi.resetModules();
  return import('./pantrySide.svelte.js');
}

describe('the Pantry · Ingredients choice', () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
  });

  it('is Pantry until Ingredients is chosen, then remembers each choice, also after a reload', async () => {
    let side = await fresh();
    expect(side.pantrySide.value).toBe('pantry');
    side.rememberSide('ingredients');
    expect(side.pantrySide.value).toBe('ingredients');
    side = await fresh();
    expect(side.pantrySide.value).toBe('ingredients');
    side.rememberSide('pantry');
    side = await fresh();
    expect(side.pantrySide.value).toBe('pantry');
  });

  it('ignores anything else stored', async () => {
    localStorage.setItem('mealwright.pantry-side', 'recipes');
    expect((await fresh()).pantrySide.value).toBe('pantry');
  });

  it('works without storage: it opens Pantry, and a choice holds until the page is reloaded', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('blocked');
      },
      setItem: () => {
        throw new Error('blocked');
      }
    });
    const side = await fresh();
    expect(side.pantrySide.value).toBe('pantry');
    expect(() => side.rememberSide('ingredients')).not.toThrow();
    expect(side.pantrySide.value).toBe('ingredients');
  });

  it('knows Ingredients reached from the Pantry tab', async () => {
    const { isPantryIngredients } = await fresh();
    expect(isPantryIngredients('/recipes/ingredients', '?from=pantry')).toBe(true);
    expect(isPantryIngredients('/recipes/ingredients', '?filter=staples&from=pantry')).toBe(true);
    expect(isPantryIngredients('/recipes/ingredients', '')).toBe(false);
    expect(isPantryIngredients('/recipes', '?from=pantry')).toBe(false);
  });
});
