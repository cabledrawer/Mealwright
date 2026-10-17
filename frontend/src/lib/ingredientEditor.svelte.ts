// The one ingredient editor, opened from anywhere (spec: "Tap any ingredient anywhere
// ... to open the same editor"): a recipe's ingredient list, a pantry item, a
// shopping-list item, Import review. Call ingredientEditor.open(foodId); the app
// layout shows it as a sheet on phones and a side panel on desktop.

class IngredientEditorState {
  /** The food being edited, or null when the editor is closed. */
  foodId = $state<number | null>(null);

  open(foodId: number): void {
    this.foodId = foodId;
  }

  close(): void {
    this.foodId = null;
  }
}

export const ingredientEditor = new IngredientEditorState();
