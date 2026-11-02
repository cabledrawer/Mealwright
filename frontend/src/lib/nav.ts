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
  href: '/recipes' | '/recipes/import' | '/recipes/drafts' | '/recipes/ingredients';
  label: string;
}

// Drafts (/recipes/drafts) was left out of the menu in 0.4, when there was nothing to put in it;
// it is back with 0.5's import (spec "Recipes navigation": All recipes · Drafts · Ingredients).
// Import is its own item between All recipes and Drafts (cabledrawer 31 Oct, F113).
export const RECIPES_PAGES: readonly RecipesPage[] = [
  { href: '/recipes', label: 'All recipes' },
  { href: '/recipes/import', label: 'Import' },
  { href: '/recipes/drafts', label: 'Drafts' },
  { href: '/recipes/ingredients', label: 'Ingredients' }
];

/**
 * Whether `sub` is the current page under Recipes. Anything under /recipes that isn't
 * Import, Drafts or Ingredients (a recipe's own page, the editor) belongs to All recipes.
 */
export function isCurrentRecipesPage(sub: RecipesPage, pathname: string): boolean {
  const under = (href: string) => pathname === href || pathname.startsWith(href + '/');
  if (sub.href !== '/recipes') return under(sub.href);
  return (
    under('/recipes') &&
    !RECIPES_PAGES.some((other) => other.href !== '/recipes' && under(other.href))
  );
}

/** A page's address (`/recipes`) as SvelteKit's route id (`/(app)/recipes`) for resolve(). */
export type AppRoute<H extends string> = H extends '/' ? '/(app)' : `/(app)${H}`;

export function appRoute<H extends Page['href'] | RecipesPage['href']>(href: H): AppRoute<H> {
  return (href === '/' ? '/(app)' : `/(app)${href}`) as AppRoute<H>;
}
