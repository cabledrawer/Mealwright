// The five main pages, in the order the mockups show them.

export type IconName = 'today' | 'plan' | 'shopping' | 'pantry' | 'recipes';

export interface Page {
  href: '/' | '/plan' | '/shopping' | '/pantry' | '/recipes';
  /** Name in the sidebar and page title. */
  label: string;
  /** Shorter name under the bottom tab on phones. */
  tabLabel: string;
  icon: IconName;
}

export const PAGES: readonly Page[] = [
  { href: '/', label: 'Today', tabLabel: 'Today', icon: 'today' },
  { href: '/plan', label: 'Plan', tabLabel: 'Plan', icon: 'plan' },
  { href: '/shopping', label: 'Shopping', tabLabel: 'Shop', icon: 'shopping' },
  { href: '/pantry', label: 'Pantry', tabLabel: 'Pantry', icon: 'pantry' },
  { href: '/recipes', label: 'Recipes', tabLabel: 'Recipes', icon: 'recipes' }
];

/** Whether `page` is the current page (Recipes stays current on its sub-pages). */
export function isCurrent(page: Page, pathname: string): boolean {
  if (page.href === '/') return pathname === '/';
  return pathname === page.href || pathname.startsWith(page.href + '/');
}

/** The pages under Recipes: a tree in the sidebar, buttons on the phone's Recipes page. */
export interface RecipesPage {
  href: '/recipes' | '/recipes/drafts' | '/recipes/ingredients';
  label: string;
}

// Drafts (/recipes/drafts) is left out of the menu in 0.4: drafts only come with import (0.5),
// so the entry is hidden, not shown empty. Put it back between the two when import is built.
export const RECIPES_PAGES: readonly RecipesPage[] = [
  { href: '/recipes', label: 'All recipes' },
  { href: '/recipes/ingredients', label: 'Ingredients' }
];

/**
 * Whether `sub` is the current page under Recipes. Anything under /recipes that isn't
 * Ingredients (a recipe's own page, the editor) belongs to All recipes.
 */
export function isCurrentRecipesPage(sub: RecipesPage, pathname: string): boolean {
  const under = (href: string) => pathname === href || pathname.startsWith(href + '/');
  if (sub.href !== '/recipes') return under(sub.href);
  return (
    under('/recipes') &&
    !RECIPES_PAGES.some((other) => other.href !== '/recipes' && under(other.href))
  );
}
