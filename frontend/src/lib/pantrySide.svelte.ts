// The phone's Pantry · Ingredients switch (spec F76, N1; cabledrawer 28 Oct). The Pantry tab opens
// whichever of the two was chosen last. The choice is kept in this browser only; if it can't be
// kept (private window, blocked storage) the tab simply opens Pantry.

export type PantrySide = 'pantry' | 'ingredients';

const KEY = 'mealwright.pantry-side';

function readStored(): PantrySide {
  try {
    return localStorage.getItem(KEY) === 'ingredients' ? 'ingredients' : 'pantry';
  } catch {
    return 'pantry';
  }
}

/** What was chosen last ('pantry' if nothing was, or nothing can be read). Reactive, so the tab bar
 * follows a choice at once. */
export const pantrySide = $state<{ value: PantrySide }>({ value: readStored() });

export function rememberSide(side: PantrySide): void {
  pantrySide.value = side;
  try {
    localStorage.setItem(KEY, side);
  } catch {
    // Storage blocked or full: the choice holds until the page is reloaded.
  }
}

/** The mark on Ingredients' address that says it was reached from the Pantry tab (not from Recipes). */
export const FROM_PANTRY = 'from=pantry';

/** Whether this address is Ingredients seen as the Pantry tab's second view. */
export function isPantryIngredients(pathname: string, search: string): boolean {
  return pathname === '/recipes/ingredients' && /[?&]from=pantry(&|$)/.test(search);
}
