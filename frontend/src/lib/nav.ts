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
