// "+ Add to pantry" (spec "Decided for 0.2"): one sheet, opened from the Pantry (and
// later from anywhere), optionally with the food already chosen.

class AddToPantryState {
  open = $state(false);
  foodId = $state<number | null>(null);

  show(foodId: number | null = null): void {
    this.foodId = foodId;
    this.open = true;
  }

  close(): void {
    this.open = false;
    this.foodId = null;
  }
}

export const addToPantry = new AddToPantryState();
