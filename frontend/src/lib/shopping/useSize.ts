// "Use this" on a Shopping line's size (F183 + F204, cabledrawer 9 Nov): the line becomes that many
// of that size. A common size from the table is made first; with the switch on it also becomes
// the ingredient's usual size. Shared by the suggestion under a row and the sizes sheet.

import { newChangeId } from '#lib/changeId.js';
import { addCommonSize, patchSize, type PackChoice } from '#lib/client/foods.js';
import { kitchen } from '#lib/freshness.svelte.js';
import type { ShoppingModel } from './store.svelte.js';
import type { ListItem } from './types.js';

/** Make the size if needed, then change the line. Throws when the size could not be made. */
export async function useSize(
  model: ShoppingModel,
  item: ListItem,
  foodId: number,
  choice: PackChoice,
  makeUsual: boolean
): Promise<void> {
  let sizeId = choice.size_id;
  if (sizeId === null) {
    const made = await addCommonSize(
      foodId,
      { name: choice.name, amount: choice.amount },
      makeUsual,
      newChangeId()
    );
    sizeId =
      made.food.sizes.find((s) => s.amount === choice.amount && s.name === choice.name)?.id ?? null;
  } else if (makeUsual && !choice.usual) {
    await patchSize(foodId, sizeId, { usual: true }, newChangeId());
  }
  if (sizeId === null) throw new Error('size');
  kitchen.changed({ elsewhere: true });
  if (!choice.chosen || choice.size_id === null) {
    // The line is now that many of that size: a hand change, with its own Undo.
    void model.setAmount(item, choice.packs * choice.amount, sizeId);
  }
}
