// The one list of Settings' items (cabledrawer 15 Nov, F252, beta2-brief row B8; mockups
// Dark-Settings2-Desktop and -Phone): four groups, each item its own page. The computer's list
// beside the page and the phone's grouped list both follow this array. The whole Household group
// is for admins only (hidden from members; the server still refuses their changes).

/** The groups of the list (the mockup: You, Kitchen, Household, Mealwright). */
export type GroupName = 'You' | 'Kitchen' | 'Household' | 'Mealwright';

export type IconKey =
  | 'appearance'
  | 'amounts'
  | 'sign-in'
  | 'meal-slots'
  | 'shops-places'
  | 'your-kitchen'
  | 'household'
  | 'sign-in-everyone'
  | 'api-tokens'
  | 'privacy'
  | 'your-data'
  | 'recent-changes'
  | 'about'
  | 'report';

type Route =
  | '/(app)/settings/appearance'
  | '/(app)/settings/amounts'
  | '/(app)/settings/sign-in'
  | '/(app)/settings/meal-slots'
  | '/(app)/settings/shops-places'
  | '/(app)/settings/your-kitchen'
  | '/(app)/settings/people'
  | '/(app)/settings/sign-in-everyone'
  | '/(app)/settings/api-tokens'
  | '/(app)/settings/outside-connections'
  | '/(app)/settings/your-data'
  | '/(app)/settings/recent-changes'
  | '/(app)/settings/about';

/** Each item's name on screen: its page's title, and the name its offline note says (FE1). */
export type ItemLabel =
  | 'Appearance'
  | 'Amounts'
  | 'Your sign-in'
  | 'Meal slots'
  | 'Shops & places'
  | 'Your kitchen'
  | 'People'
  | 'Sign-in for everyone'
  | 'API tokens'
  | 'Outside connections'
  | 'Backups & your data'
  | 'Recent changes'
  | 'About';

export type Item = {
  /** The page's address after /settings/: a slug of its label (FE25, 0.9.5-beta.3). */
  id: string;
  label: ItemLabel;
  group: GroupName;
  /** The page's route (resolve() turns it into an address). */
  route: Route;
  /** The address the page lives at; the page and everything under it mark this item. */
  path: string;
  /** Other addresses that belong under this item. */
  also?: string[];
  icon: IconKey;
  /** For admins only even though its group isn't (Meal slots, as before the redesign). */
  admin?: boolean;
};

export const ITEMS: Item[] = [
  {
    id: 'appearance',
    label: 'Appearance',
    group: 'You',
    route: '/(app)/settings/appearance',
    path: '/settings/appearance',
    icon: 'appearance'
  },
  {
    id: 'amounts',
    label: 'Amounts',
    group: 'You',
    route: '/(app)/settings/amounts',
    path: '/settings/amounts',
    icon: 'amounts'
  },
  {
    id: 'sign-in',
    label: 'Your sign-in',
    group: 'You',
    route: '/(app)/settings/sign-in',
    path: '/settings/sign-in',
    also: ['/settings/password'],
    icon: 'sign-in'
  },
  {
    id: 'meal-slots',
    label: 'Meal slots',
    group: 'Kitchen',
    route: '/(app)/settings/meal-slots',
    path: '/settings/meal-slots',
    admin: true,
    icon: 'meal-slots'
  },
  {
    id: 'shops-places',
    label: 'Shops & places',
    group: 'Kitchen',
    route: '/(app)/settings/shops-places',
    path: '/settings/shops-places',
    icon: 'shops-places'
  },
  {
    id: 'your-kitchen',
    label: 'Your kitchen',
    group: 'Kitchen',
    route: '/(app)/settings/your-kitchen',
    path: '/settings/your-kitchen',
    // The old address, until its page has sent the person on (FE25).
    also: ['/settings/kitchen'],
    icon: 'your-kitchen'
  },
  {
    id: 'people',
    label: 'People',
    group: 'Household',
    route: '/(app)/settings/people',
    path: '/settings/people',
    // The old address, until its page has sent the person on (FE25).
    also: ['/settings/household'],
    icon: 'household'
  },
  {
    id: 'sign-in-everyone',
    label: 'Sign-in for everyone',
    group: 'Household',
    route: '/(app)/settings/sign-in-everyone',
    path: '/settings/sign-in-everyone',
    also: ['/settings/sso'],
    icon: 'sign-in-everyone'
  },
  {
    id: 'api-tokens',
    label: 'API tokens',
    group: 'Household',
    route: '/(app)/settings/api-tokens',
    path: '/settings/api-tokens',
    icon: 'api-tokens'
  },
  {
    id: 'outside-connections',
    label: 'Outside connections',
    group: 'Household',
    route: '/(app)/settings/outside-connections',
    path: '/settings/outside-connections',
    // The old address, until its page has sent the person on (FE25).
    also: ['/settings/privacy'],
    icon: 'privacy'
  },
  {
    id: 'your-data',
    label: 'Backups & your data',
    group: 'Household',
    route: '/(app)/settings/your-data',
    path: '/settings/your-data',
    icon: 'your-data'
  },
  {
    id: 'recent-changes',
    label: 'Recent changes',
    group: 'Mealwright',
    route: '/(app)/settings/recent-changes',
    path: '/settings/recent-changes',
    icon: 'recent-changes'
  },
  {
    id: 'about',
    label: 'About',
    group: 'Mealwright',
    route: '/(app)/settings/about',
    path: '/settings/about',
    icon: 'about'
  }
];

/** The groups in the order they are drawn, with each one's accessible name. */
export const GROUPS: { name: GroupName; label: string; adminOnly: boolean }[] = [
  { name: 'You', label: 'Your settings', adminOnly: false },
  { name: 'Kitchen', label: 'Kitchen settings', adminOnly: false },
  { name: 'Household', label: 'Household settings', adminOnly: true },
  { name: 'Mealwright', label: 'Mealwright', adminOnly: false }
];

/** Whether an item is for admins only (its whole group is, or it says so itself). */
export const adminOnly = (item: Item): boolean =>
  item.admin === true || (GROUPS.find((group) => group.name === item.group)?.adminOnly ?? false);

/** The items this person sees, in the groups' order. */
export function itemsFor(admin: boolean): Item[] {
  return ITEMS.filter((item) => admin || !adminOnly(item));
}

const under = (pathname: string, base: string) =>
  pathname === base || pathname.startsWith(`${base}/`);

/** The item an address belongs to (its own page, or one under it), or none. */
export function itemAt(pathname: string): Item | undefined {
  const path = pathname.replace(/\/+$/, '');
  return ITEMS.find((item) => [item.path, ...(item.also ?? [])].some((p) => under(path, p)));
}

/**
 * The item a page belongs to, by the page's route (`page.route.id`, such as
 * "/(app)/settings/people/[id]"), not by the address typed: the address may be spelt with
 * percent-codes ("/settings/%68ousehold") that name the same page.
 */
export function itemAtRoute(routeId: string | null | undefined): Item | undefined {
  if (!routeId) return undefined;
  return itemAt(routeId.replace(/\/\([^/)]*\)/g, ''));
}

/** Old names of items, as section names ("?section=household") and addresses
 *  ("/settings/privacy"), and the item each one is now (FE25). */
const OLD_IDS: Record<string, string> = {
  household: 'people',
  privacy: 'outside-connections',
  kitchen: 'your-kitchen'
};

/** The old section names ("#about", "?section=sign-in") and the item each one is now. */
export function itemForOldSection(id: string): Item | undefined {
  const asked = Object.hasOwn(OLD_IDS, id) ? OLD_IDS[id] : id;
  return ITEMS.find((item) => item.id === asked);
}

/** An item's name on screen, by its id: the one name its page and its notes use (FE1). */
export function labelOf(id: string): ItemLabel {
  const item = ITEMS.find((it) => it.id === id);
  if (!item) throw new Error(`No Settings item ${id}`);
  return item.label;
}
