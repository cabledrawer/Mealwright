// Cook mode's per-step ingredients (Experimental): off by default, and once switched on they
// stay on for the household (spec "Cook mode (K4)", cabledrawer 31 Oct).
//
// NOT SAVED YET. Keeping it for the household needs a place on the server (a household setting:
// a database column and a field on PATCH /household), which this pull request does not add
// without the lead's and cabledrawer's OK. Until then the choice lasts while the app is open.

class CookPrefs {
  /** Whether each step shows the ingredients guessed for it. */
  perStep = $state(false);

  setPerStep(on: boolean): void {
    this.perStep = on;
  }
}

export const cookPrefs = new CookPrefs();
