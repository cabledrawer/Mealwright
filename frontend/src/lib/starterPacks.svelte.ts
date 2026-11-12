// "Add a starter pack" (0.8 R4; spec section 2): Ingredients opens the dialog; the 0.9.0
// onboarding step will open the same one.

class StarterPackDialog {
  open = $state(false);
  /** Opened at least once: the dialog's code is fetched then, and kept (size limit). */
  wanted = $state(false);

  show(): void {
    this.wanted = true;
    this.open = true;
  }

  close(): void {
    this.open = false;
  }
}

export const starterPacks = new StarterPackDialog();
