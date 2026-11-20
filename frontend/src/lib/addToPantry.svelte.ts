// "+ Add to pantry" (spec "Decided for 0.2"): one sheet, opened from the Pantry (and
// later from anywhere), optionally with the food already chosen.

class AddToPantryState {
  open = $state(false);
  foodId = $state<number | null>(null);
  /** Opened at least once: the sheet's code is fetched then, and kept (size limit). */
  wanted = $state(false);

  show(foodId: number | null = null): void {
    this.foodId = foodId;
    this.wanted = true;
    this.open = true;
  }

  /** The sheet's code could not be fetched: as if cancelled, and the next ask fetches again. */
  fail(): void {
    this.wanted = false;
    this.close();
  }

  close(): void {
    this.open = false;
    this.foodId = null;
  }
}

export const addToPantry = new AddToPantryState();
