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

/** Batch cook (Experimental, B2): its own entry in the sidebar, after Plan; on the phone it is
 * the Plan's third tab (Week | Month | Batch cook), so the five bottom tabs stay. */
export const BATCH_COOK = { href: '/batch-cook', label: 'Batch cook', icon: 'batch' } as const;

export function isBatchCook(pathname: string): boolean {
  return pathname === BATCH_COOK.href || pathname.startsWith(BATCH_COOK.href + '/');
}

/** Whether `page` is the current page (Recipes stays current on its sub-pages). */
export function isCurrent(page: Page, pathname: string): boolean {
  if (page.href === '/') return pathname === '/';
  return pathname === page.href || pathname.startsWith(page.href + '/');
}

/** Ingredients (cabledrawer 15 Nov, F251): its own main-menu item right after Pantry on the
 * computer sidebar and rail. The page stays at /recipes/ingredients. The phone's five tabs
 * don't change (Pantry's switch reaches it there). */
export const INGREDIENTS = {
  href: '/recipes/ingredients',
  label: 'Ingredients',
  icon: 'ingredients'
} as const;

export function isIngredients(pathname: string): boolean {
  return pathname === INGREDIENTS.href || pathname.startsWith(INGREDIENTS.href + '/');
}

/** The pages under Recipes: a tree in the sidebar, buttons on the phone's Recipes page. */
export interface RecipesPage {
  href: '/recipes' | '/recipes/import' | '/recipes/drafts';
  label: string;
}

// Drafts (/recipes/drafts) was left out of the menu in 0.4, when there was nothing to put in it;
// it is back with 0.5's import (spec "Recipes navigation": All recipes · Drafts).
// Import is its own item between All recipes and Drafts (cabledrawer 31 Oct, F113).
// Ingredients moved out to the main menu (F251).
export const RECIPES_PAGES: readonly RecipesPage[] = [
  { href: '/recipes', label: 'All recipes' },
  { href: '/recipes/import', label: 'Import' },
  { href: '/recipes/drafts', label: 'Drafts' }
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
    !isIngredients(pathname) &&
    !RECIPES_PAGES.some((other) => other.href !== '/recipes' && under(other.href))
  );
}

/** A page's address (`/recipes`) as SvelteKit's route id (`/(app)/recipes`) for resolve(). */
export type AppRoute<H extends string> = H extends '/' ? '/(app)' : `/(app)${H}`;

export function appRoute<H extends Page['href'] | RecipesPage['href'] | typeof INGREDIENTS.href>(
  href: H
): AppRoute<H> {
  return (href === '/' ? '/(app)' : `/(app)${href}`) as AppRoute<H>;
}
