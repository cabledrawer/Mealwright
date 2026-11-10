import { describe, expect, it, vi } from 'vitest';
import type { RecipeBrief } from '#lib/client/recipes.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import type { FoodRow } from '#lib/client/types.js';
import { arrange, fold, pickRecipes, recipeSearch } from './search';

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

describe('arrange (F189, cabledrawer 8 Nov: a recipe is offered before a plain ingredient of the same name)', () => {
  const food = (id: number, name: string) => ({ id, name }) as unknown as FoodRow;
  const label = (rows: ReturnType<typeof arrange>) =>
    rows.map(
      (r) =>
        `${r.kind === 'recipe' ? 'R' : 'I'}:${r.kind === 'recipe' ? r.recipe.name : r.food.name}${r.paired ? '*' : ''}`
    );

  it('puts the recipe with exactly an ingredient’s name just before it, and marks both', () => {
    const rows = arrange(
      [food(1, 'Dosa batter'), food(2, 'Dosa mix')],
      [brief(10, 'Dosa batter'), brief(11, 'Dosa stuffing')]
    );
    expect(label(rows)).toEqual([
      'R:Dosa batter*',
      'I:Dosa batter*',
      'I:Dosa mix',
      'R:Dosa stuffing'
    ]);
  });

  it('matches names the way the editor does: case and accents ignored', () => {
    expect(label(arrange([food(1, 'Pâté')], [brief(2, 'pate')]))).toEqual(['R:pate*', 'I:Pâté*']);
  });

  it('keeps the old order when no recipe shares a name, and when there is only one kind', () => {
    expect(label(arrange([food(1, 'Toor dal')], [brief(3, 'Sambar')]))).toEqual([
      'I:Toor dal',
      'R:Sambar'
    ]);
    expect(label(arrange([], [brief(3, 'Sambar')]))).toEqual(['R:Sambar']);
    expect(arrange([], [])).toEqual([]);
  });
});
