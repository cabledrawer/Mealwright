import { describe, expect, it } from 'vitest';
import { RecipeList, filterFromSearch } from './recipes.svelte';

describe('where All recipes starts', () => {
  it('on All, or on Use soon when Pantry’s “Recipes for these” sent it there', () => {
    expect(filterFromSearch(new URLSearchParams(''))).toBe('all');
    expect(filterFromSearch(new URLSearchParams('filter=use-soon'))).toBe('soon');
    expect(filterFromSearch(new URLSearchParams('filter=staples'))).toBe('all');
    expect(new RecipeList('soon').filter).toBe('soon');
    expect(new RecipeList().filter).toBe('all');
  });
});
