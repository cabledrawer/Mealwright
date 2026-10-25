// What a line linked to an ingredient says (cabledrawer 25 Oct, 0.5.1): when the words are only the
// start of the ingredient's name, or of one of its other names ("thu", "E", "pan"), the line
// shows the ingredient's full name ("Toor Dal", "Egg", "Paneer"). Words typed in full stay as
// typed ("the podi", "fresh coriander", "thuvaram paruppu"), and typing alone, with no link,
// never changes them (cabledrawer 20 Oct).

const fold = (s: string) => s.trim().toLocaleLowerCase();

/** True when `words` are the start of `name`, but not all of it. */
const startOf = (words: string, name: string) => {
  const w = fold(words);
  const n = fold(name);
  return w !== '' && w.length < n.length && n.startsWith(w);
};

/** The words a line linked to `food` should say. */
export function linkedWords(
  words: string,
  food: { name: string; other_names?: readonly string[] } | null | undefined
): string {
  if (!food) return words;
  const otherNames = food.other_names ?? [];
  if (fold(words) === fold(food.name)) return words;
  // A name typed in full stays, even when it is also the start of another ("Dal" for "Dal makhani").
  if (otherNames.some((other) => fold(other) === fold(words))) return words;
  return startOf(words, food.name) || otherNames.some((other) => startOf(words, other))
    ? food.name
    : words;
}
