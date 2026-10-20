import { describe, expect, it, vi } from 'vitest';
import type { RecipeBrief } from '$lib/client/recipes';
import { fakeApi } from '$lib/testing/fakeApi';
import { fold, pickRecipes, recipeSearch } from './search';

const brief = (id: number, name: string): RecipeBrief => ({
  id,
  name,
  description: null,
  makes: null,
  version: 1
});
const ALL = [
  brief(1, 'Sambar'),
  brief(2, 'Rasam'),
  brief(3, 'Sambar powder'),
  brief(4, 'Veg sambar rice')
];

describe('pickRecipes', () => {
  it('finds names containing what was typed, ignoring case and accents, starts first', () => {
    expect(pickRecipes(ALL, 'SAMBAR').map((r) => r.name)).toEqual([
      'Sambar',
      'Sambar powder',
      'Veg sambar rice'
    ]);
    expect(fold('Pâté')).toBe('pate');
  });

  it('finds nothing for nothing', () => {
    expect(pickRecipes(ALL, '  ')).toEqual([]);
  });
});

describe('recipeSearch', () => {
  it('asks for the A-to-Z list once and answers every search from it', async () => {
    const requests = fakeApi({
      'GET /recipes?limit=500': [200, { total: 4, recipes: ALL, next: null }]
    });
    const search = recipeSearch();
    expect((await search('ras')).map((r) => r.name)).toEqual(['Rasam']);
    expect((await search('powder')).map((r) => r.name)).toEqual(['Sambar powder']);
    expect(requests).toHaveLength(1);
    vi.unstubAllGlobals();
  });
});
