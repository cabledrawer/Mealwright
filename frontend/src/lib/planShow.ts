// The Plan's switch Both · Eat · Cook (spec "The Plan redesign, 0.7.0"): Both opens first on the
// computer, Eat first on the phone. The choice is kept on this device (localStorage, in a
// try/catch, like the tray); where nothing is kept, or storage is blocked, the layout decides.

export type PlanShow = 'both' | 'eat' | 'cook';

/** The switch's buttons, in order. */
export const SHOWS: readonly PlanShow[] = ['both', 'eat', 'cook'];

export const SHOW_KEY = 'mealwright.plan-show';

/** What opens first on this layout: Eat on the phone, Both on the computer. */
export const defaultShow = (phone: boolean): PlanShow => (phone ? 'eat' : 'both');

export const isShow = (value: unknown): value is PlanShow =>
  typeof value === 'string' && (SHOWS as readonly string[]).includes(value);

/** The choice kept on this device, else the layout's own. */
export function readShow(phone: boolean): PlanShow {
  try {
    const kept = localStorage.getItem(SHOW_KEY);
    if (isShow(kept)) return kept;
  } catch {
    // Storage blocked or empty: the layout decides.
  }
  return defaultShow(phone);
}

/** Keep the choice on this device. A blocked store still lets it apply until the page closes. */
export function keepShow(show: PlanShow): void {
  try {
    localStorage.setItem(SHOW_KEY, show);
  } catch {
    // Not kept.
  }
}
