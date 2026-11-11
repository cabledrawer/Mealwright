// "Edit the name read" on a Check row (F214, cabledrawer 10 Nov: Change on every row is one sheet to
// pick an existing ingredient, edit the name read, or make a new one). The name the reader found
// ("your favorite seasoning blend") is the person's to correct ("BBQ rub"). The line is matched
// again with the one lookup the pick-list uses: an ingredient with exactly that name, or another
// name for it, is the line's ingredient ("ok"); anything else is a line that needs the person,
// whose New ingredient starts as the corrected name. Nothing fuzzy is guessed here: the server's
// own reading is not run again, so a close match is found with Pick an ingredient.

import type { ReviewLine } from './client/imports';
import type { FoodRow } from './client/types';
import { fold } from './recipes/search';

const norm = (text: string): string => fold(text).split(/\s+/).filter(Boolean).join(' ');

/** The line as it reads once its name is `name`: the pieces of the line that follow the name. */
export async function renamedLine(
  line: ReviewLine,
  name: string,
  find: (query: string) => Promise<FoodRow[]>
): Promise<Partial<ReviewLine>> {
  const words = name.trim().replace(/\s+/g, ' ');
  const key = norm(words);
  let foods: FoodRow[] = [];
  try {
    foods = await find(words);
  } catch {
    // No answer (offline, or the server busy): the line needs the person, who can still Pick.
  }
  const found = foods.find(
    (food) => norm(food.name) === key || food.other_names.some((other) => norm(other) === key)
  );
  const guess = {
    name: words[0]!.toUpperCase() + words.slice(1),
    counted_as: line.new_ingredient?.counted_as ?? 'weight',
    place: line.new_ingredient?.place ?? null
  };
  if (found) {
    return {
      words,
      label: found.staple ? 'staple' : 'matched',
      food: { id: found.id, name: found.name },
      place: found.place?.name ?? null,
      matched_by: norm(found.name) === key ? null : words,
      counts: !found.staple,
      new_ingredient: guess,
      learn_name: null
    };
  }
  return {
    words,
    label: 'needs_you',
    food: null,
    place: null,
    matched_by: null,
    counts: true,
    new_ingredient: guess,
    learn_name: null
  };
}
