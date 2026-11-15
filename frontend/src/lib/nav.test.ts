import { describe, expect, it } from 'vitest';
import {
  INGREDIENTS,
  PAGES,
  RECIPES_PAGES,
  isCurrent,
  isCurrentRecipesPage,
  isIngredients
} from './nav';

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
      ['/recipes/import', 'Import'],
      ['/recipes/drafts', 'Drafts'],
      ['/recipes/drafts/12', 'Drafts']
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
    // Ingredients has its own main-menu item (F251): nothing under Recipes is current there.
    expect(RECIPES_PAGES.some((p) => isCurrentRecipesPage(p, '/recipes/ingredients'))).toBe(false);
    expect(isCurrentRecipesPage(sub('Drafts'), '/recipes/draftsx')).toBe(false);
    expect(isCurrentRecipesPage(sub('Import'), '/recipes/importx')).toBe(false);
  });

  it('lists All recipes · Import · Drafts (Import is its own item, F113; Ingredients moved out, F251)', () => {
    expect(RECIPES_PAGES.map((p) => p.label)).toEqual(['All recipes', 'Import', 'Drafts']);
  });
});

describe('Ingredients in the main menu (F251)', () => {
  it('is its own item, kept at /recipes/ingredients', () => {
    expect(INGREDIENTS.href).toBe('/recipes/ingredients');
    expect(INGREDIENTS.label).toBe('Ingredients');
  });

  it('is current on its page and below it, nowhere else', () => {
    expect(isIngredients('/recipes/ingredients')).toBe(true);
    expect(isIngredients('/recipes/ingredients/3')).toBe(true);
    expect(isIngredients('/recipes/ingredientsx')).toBe(false);
    expect(isIngredients('/recipes')).toBe(false);
    expect(isIngredients('/pantry')).toBe(false);
  });

  it('leaves the phone’s five tabs as they were', () => {
    expect(PAGES.map((p) => p.label)).not.toContain('Ingredients');
  });
});
