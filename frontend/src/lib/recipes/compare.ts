// "Wren's version" (cabledrawer 19 Oct): the recipe as someone else saved it, set beside what was
// opened, so the sheet can highlight what they changed. Nothing here is editable.

import type { LineOut, RecipeOut } from '#lib/client/recipes.js';
import { linkedWords } from './linkedWords';

export interface ShownLine {
  /** "300 g" (empty for a line with no amount). */
  quantity: string;
  words: string;
  note: string;
  heading: boolean;
  /** same · changed · added · removed. */
  status: 'same' | 'changed' | 'added' | 'removed';
  /** What it was, for a changed line: "200 g". */
  was: string | null;
}

const NBSP = ' ';

/** "1½ tbsp", "2 packets", "10", or nothing. */
export function quantityOf(line: LineOut): string {
  if (!line.amount_text) return '';
  const unit = line.size
    ? line.amount && line.amount > 1
      ? line.size.plural
      : line.size.name
    : line.unit;
  return unit ? `${line.amount_text}${NBSP}${unit}` : line.amount_text;
}

const shown = (
  line: LineOut,
  status: ShownLine['status'],
  was: string | null = null
): ShownLine => ({
  quantity: quantityOf(line),
  words: linkedWords(line.words, line.food),
  note: line.note ?? '',
  heading: line.kind === 'heading',
  status,
  was
});

/** Their lines, in their order, with the ones you opened that they took out added after. */
export function compareLines(opened: LineOut[], theirs: LineOut[]): ShownLine[] {
  const before = new Map(opened.map((l) => [l.id, l]));
  const out = theirs.map((line) => {
    const old = before.get(line.id);
    if (!old) return shown(line, 'added');
    const same =
      quantityOf(old) === quantityOf(line) && old.words === line.words && old.note === line.note;
    if (same) return shown(line, 'same');
    return shown(
      line,
      'changed',
      quantityOf(old) !== quantityOf(line) ? quantityOf(old) || 'no amount' : `“${old.words}”`
    );
  });
  const kept = new Set(theirs.map((l) => l.id));
  for (const old of opened) if (!kept.has(old.id)) out.push(shown(old, 'removed'));
  return out;
}

export interface ShownStep {
  /** The step's number; headings have none. */
  n: number | null;
  text: string;
  heading: boolean;
  changed: boolean;
}

/** Their steps; a step is "changed" when it is not what you opened at the same place. */
export function compareSteps(opened: RecipeOut['steps'], theirs: RecipeOut['steps']): ShownStep[] {
  let n = 0;
  return theirs.map((step, i) => ({
    n: step.kind === 'heading' ? null : ++n,
    text: step.text,
    heading: step.kind === 'heading',
    changed:
      opened[i]?.text !== step.text ||
      opened[i]?.kind !== step.kind ||
      // A wait added, taken off or changed counts (M1).
      JSON.stringify(opened[i]?.wait ?? null) !== JSON.stringify(step.wait ?? null) ||
      // Batch cook's timing changed by hand (a changed guess comes with changed words).
      JSON.stringify(opened[i]?.timing ?? null) !== JSON.stringify(step.timing ?? null)
  }));
}

/** The names of the other boxes they changed, for "Also changed: time, tags". */
export function otherChanges(opened: RecipeOut, theirs: RecipeOut): string[] {
  const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
  const changed: string[] = [];
  if (opened.name !== theirs.name) changed.push('name');
  if (!same(opened.description, theirs.description)) changed.push('description');
  if (
    opened.time_minutes !== theirs.time_minutes ||
    !same(opened.wait ?? null, theirs.wait ?? null)
  )
    changed.push('time');
  if (opened.serves !== theirs.serves) changed.push('serves');
  if (!same(opened.makes, theirs.makes)) changed.push('makes');
  if (opened.made_ahead !== theirs.made_ahead) changed.push('made ahead');
  if (!same(opened.tags, theirs.tags)) changed.push('tags');
  if (!same(opened.nutrition, theirs.nutrition)) changed.push('nutrition');
  if (opened.source_note !== theirs.source_note) changed.push('source');
  if (opened.photo?.id !== theirs.photo?.id) changed.push('photo');
  return changed;
}
