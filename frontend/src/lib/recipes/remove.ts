// Delete a recipe, from the editor and from the recipe page's ⋯ menu: one place, so both do the
// same thing. No "Are you sure?" (Undo, kept for 7 days): the toast says "Deleted Sambar" with
// Undo, and the caller then goes to Recipes. Throws the server's ApiError if it can't.

import { newChangeId } from '../changeId';
import { serverUndo } from '../client/changes';
import { deleteRecipe } from '../client/recipes';
import { kitchen } from '../freshness.svelte';
import { undoHistory } from '../undo.svelte';

export async function removeRecipe(id: number, name: string): Promise<void> {
  const { change } = await deleteRecipe(id, newChangeId());
  kitchen.changed();
  undoHistory.record({ label: `Deleted ${name}`, undo: serverUndo(change.id) });
}
