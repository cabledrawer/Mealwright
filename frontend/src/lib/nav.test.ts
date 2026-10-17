import { describe, expect, it } from 'vitest';
import { PAGES, isCurrent } from './nav';

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
