// Cook mode's per-step ingredients (Experimental): off by default. Proposed, for cabledrawer: the
// switch is remembered on this device (local storage), not for the household, until cabledrawer
// decides on a household setting (that needs a database change). Every read and write is
// guarded: where storage is blocked the switch starts off and lasts while the app is open.

export const PER_STEP_KEY = 'mealwright.cook.perStep';

function read(): boolean {
  try {
    return localStorage.getItem(PER_STEP_KEY) === '1';
  } catch {
    return false;
  }
}

export class CookPrefs {
  /** Whether each step shows the ingredients guessed for it. */
  perStep = $state(read());

  setPerStep(on: boolean): void {
    this.perStep = on;
    try {
      if (on) localStorage.setItem(PER_STEP_KEY, '1');
      else localStorage.removeItem(PER_STEP_KEY);
    } catch {
      // Storage blocked: the choice lasts while the app is open.
    }
  }
}

export const cookPrefs = new CookPrefs();
