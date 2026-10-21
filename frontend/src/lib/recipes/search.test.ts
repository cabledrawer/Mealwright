import { describe, expect, it, vi } from 'vitest';
import type { RecipeBrief } from '$lib/client/recipes';
import { fakeApi } from '$lib/testing/fakeApi';
import { fold, pickRecipes, recipeSearch } from './search';

const brief = (id: number, name: string): RecipeBrief => ({
  id,
  name,
  description: null,
  makes: null,
  photo: null,
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
  it('asks the server with q and keeps only the names that match', async () => {
    // The server also finds Sambar for "powder" (its line uses Sambar powder): not offered.
    const requests = fakeApi({
      'GET /recipes?q=powder&limit=100': [
        200,
        { total: 2, recipes: [brief(1, 'Sambar'), brief(3, 'Sambar powder')], next: null }
      ]
    });
    const search = recipeSearch();
    expect((await search('powder')).map((r) => r.name)).toEqual(['Sambar powder']);
    expect(requests.map((r) => r.url)).toEqual(['/recipes?q=powder&limit=100']);
    vi.unstubAllGlobals();
  });

  it('asks nothing for nothing', async () => {
    const requests = fakeApi({});
    expect(await recipeSearch()('  ')).toEqual([]);
    expect(requests).toHaveLength(0);
    vi.unstubAllGlobals();
  });
});
