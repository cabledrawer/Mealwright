import { describe, expect, it } from 'vitest';
import { PAGES, RECIPES_PAGES, isCurrent, isCurrentRecipesPage } from './nav';

const byLabel = (label: string) => PAGES.find((p) => p.label === label)!;

describe('isCurrent', () => {
  it('marks Today only on the home page', () => {
    expect(isCurrent(byLabel('Today'), '/')).toBe(true);
    expect(isCurrent(byLabel('Today'), '/plan')).toBe(false);
  });

  it('keeps a page marked on its sub-pages', () => {
    expect(isCurrent(byLabel('Recipes'), '/recipes')).toBe(true);
    expect(isCurrent(byLabel('Recipes'), '/recipes/drafts')).toBe(true);
    expect(isCurrent(byLabel('Recipes'), '/recipesx')).toBe(false);
  });

  it('lists the five pages in the mockups’ order', () => {
    expect(PAGES.map((p) => p.label)).toEqual(['Today', 'Plan', 'Shopping', 'Pantry', 'Recipes']);
  });
});

describe('isCurrentRecipesPage', () => {
  const sub = (label: string) => RECIPES_PAGES.find((p) => p.label === label)!;

  it('marks exactly one page under Recipes', () => {
    for (const [path, label] of [
      ['/recipes', 'All recipes'],
      ['/recipes/12', 'All recipes'],
      ['/recipes/new', 'All recipes'],
      ['/recipes/import', 'All recipes'],
      ['/recipes/drafts', 'Drafts'],
      ['/recipes/drafts/12', 'Drafts'],
      ['/recipes/ingredients', 'Ingredients']
    ] as const) {
      const current = RECIPES_PAGES.filter((p) => isCurrentRecipesPage(p, path));
      expect(
        current.map((p) => p.label),
        path
      ).toEqual([label]);
    }
  });

  it('marks none elsewhere', () => {
    expect(RECIPES_PAGES.some((p) => isCurrentRecipesPage(p, '/pantry'))).toBe(false);
    expect(isCurrentRecipesPage(sub('Ingredients'), '/recipes/ingredientsx')).toBe(false);
    expect(isCurrentRecipesPage(sub('Drafts'), '/recipes/draftsx')).toBe(false);
  });

  it('lists All recipes · Drafts · Ingredients (Drafts came back with import in 0.5)', () => {
    expect(RECIPES_PAGES.map((p) => p.label)).toEqual(['All recipes', 'Drafts', 'Ingredients']);
  });
});
