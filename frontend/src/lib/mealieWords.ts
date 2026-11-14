// The words of Import from Mealie (0.9.5, cabledrawer 13 Nov; mockups Dark-Mealie*095-Phone and
// Dark-MealieImport095-Desktop; docs/dev/words.md section 81). One place, so the phone's
// screens and the computer's say the same thing. Lines the mockups don't show are proposed,
// for cabledrawer (section 81).

import type { MealieImport, MealiePreview, MealieResult, MealieUndone } from './client/mealie';
import { sizeWords, whenWords } from './yourDataWords';

export { sizeWords };

export const LEAD =
  'Bring your recipes and foods across from Mealie in one go. Your Mealwright recipes stay as they are.';
/** The computer's lead says the preview too (the mockup's own words). */
export const LEAD_WIDE =
  'Bring your recipes and foods across from Mealie in one go. Your Mealwright recipes stay as they are, and nothing is added until you’ve looked it over.';
/** Mealie's own menu path (proposed, for cabledrawer: Mealie's current menus). */
export const MENU_PATH = 'In Mealie: Settings › Admin Settings › Backups › Create Backup.';
export const READS_ONLY =
  'Mealwright only reads the file you choose. It never connects to Mealie or to the internet.';
export const RUNS_ON_SERVER =
  'You can leave this screen or close the app. The import carries on on your server, and Today shows a note when it’s done.';
export const RUNS_ON_SERVER_WIDE =
  'It runs on your server, so you can close this tab or carry on elsewhere. Today shows a note when it’s done.';
export const UNREAD_LEAD =
  'Mealwright couldn’t read some ingredient lines. Check opens the usual import check. Save all keeps those lines as plain text; they don’t go on the shopping list.';
export const DRAFTS_LEAD =
  'Open one to check its lines, the same check as any import. Or save them all now: lines Mealwright couldn’t read stay as plain text, and nothing is added to the shopping list for them.';
export const STEPS = ['1 Choose the file', '2 Look it over', '3 Bring in', '4 Done'] as const;

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "202 recipes", "1 recipe". */
export const recipesWords = (n: number): string => plural(n, 'recipe');

/** "2 lines", "1 line". */
export const linesWords = (n: number): string => plural(n, 'line');

/** The button on the preview: "Bring in 202 recipes". */
export const bringInWords = (n: number): string => `Bring in ${recipesWords(n)}`;

/** "Save all 31 as they are" (Drafts); the computer's Done says "Save all as they are". */
export const saveAllWords = (n: number | null = null): string =>
  n === null ? 'Save all as they are' : `Save all ${n} as they are`;

const LEFT_OUT: [key: string, one: string, many: string][] = [
  ['meal_plans', 'meal plan', 'meal plans'],
  ['shopping_lists', 'shopping list', 'shopping lists'],
  ['users', 'user', 'users'],
  ['cookbooks', 'cookbook', 'cookbooks']
];

/** "Not brought in: 6 meal plans, 2 shopping lists, 3 users, 4 cookbooks.", or null when the
 *  file has none of them. */
export function notBroughtIn(leftOut: Record<string, number>): string | null {
  const parts = LEFT_OUT.filter(([key]) => (leftOut[key] ?? 0) > 0).map(([key, one, many]) =>
    plural(leftOut[key] ?? 0, one, many)
  );
  return parts.length ? `Not brought in: ${parts.join(', ')}.` : null;
}

/** The photos switch's line: "About 41 MB more on your server". */
export const photosWords = (preview: Pick<MealiePreview, 'photo_bytes'>): string =>
  `About ${sizeWords(Math.max(preview.photo_bytes, 1_000_000))} more on your server`;

/** The file line: "48 MB · read just now" (the size once the server has it). */
export function fileWords(job: Pick<MealieImport, 'file_bytes'>): string {
  return job.file_bytes === null ? 'Read just now' : `${sizeWords(job.file_bytes)} · read just now`;
}

/** The new recipes the preview will bring in, after the ones left out by hand. */
export function chosenCount(preview: MealiePreview, leaveOut: ReadonlySet<string>): number {
  if (!preview.recipes.length) return preview.new;
  return preview.recipes.filter((r) => !r.already && !leaveOut.has(r.key)).length;
}

/** All the recipes the import brought in, ready or waiting in Drafts. */
export const broughtIn = (job: Pick<MealieImport, 'counts'>): number =>
  job.counts.saved + job.counts.drafts;

/** "202 recipes brought in". */
export const broughtInWords = (job: Pick<MealieImport, 'counts'>): string =>
  `${recipesWords(broughtIn(job))} brought in`;

/** "From mealie_2026.11.10.zip, today 21:40". */
export function fromFileWords(
  job: Pick<MealieImport, 'file_name' | 'finished_at'>,
  now: Date = new Date()
): string {
  if (!job.finished_at) return `From ${job.file_name}`;
  const when = whenWords(job.finished_at, now);
  return `From ${job.file_name}, ${when.charAt(0).toLowerCase()}${when.slice(1)}`;
}

/** The Undo row: "Takes out the 202 recipes and the 85 new ingredients. Works for 7 days;
 *  recipes you've changed or cooked since are kept." */
export function undoWords(job: Pick<MealieImport, 'counts'>): string {
  const recipes = `the ${recipesWords(broughtIn(job))}`;
  const foods = job.counts.new_foods
    ? ` and the ${job.counts.new_foods} new ${job.counts.new_foods === 1 ? 'ingredient' : 'ingredients'}`
    : '';
  return `Takes out ${recipes}${foods}. Works for 7 days; recipes you’ve changed or cooked since are kept.`;
}

/** After Undo (proposed, for cabledrawer): "Took out 171 recipes and 85 ingredients; kept 3 you'd
 *  changed or cooked." */
export function undoneWords(done: MealieUndone): string {
  let words = `Took out ${recipesWords(done.recipes + done.drafts)}`;
  if (done.foods) words += ` and ${plural(done.foods, 'ingredient')}`;
  if (done.kept) words += `; kept ${done.kept} you’d changed or cooked`;
  return `${words}.`;
}

/** A recipe's line while it runs: "Ready", "2 lines to check", "Left out" (already here). */
export function resultWords(result: Pick<MealieResult, 'state' | 'unread_count'>): string {
  switch (result.state) {
    case 'draft':
      return `${linesWords(result.unread_count)} to check`;
    case 'already':
      return 'You already have it';
    case 'skipped':
      return 'Couldn’t be brought in';
    default:
      return 'Ready';
  }
}

/** The lines it couldn't read, quoted: '"1 tin coconut milk (optional)", "salt to taste"'.
 *  More than shown: the phone adds ", …", the computer ", and 2 more". */
export function unreadWords(lines: string[], count: number, wide = false, shown = 2): string {
  const quoted = lines.slice(0, shown).map((line) => `“${line}”`);
  const more = count - quoted.length;
  if (more > 0) quoted.push(wide ? `and ${more} more` : '…');
  return quoted.join(', ');
}

/** "25 more", under a list that shows only the first few. */
export const moreWords = (n: number): string => `${n} more`;

/** "Showing 8 of 214. Untick any you don't want." */
export const showingWords = (shown: number, all: number): string =>
  `Showing ${shown} of ${all}. Untick any you don’t want.`;

/** Today's note (proposed, for cabledrawer). */
export const noteWords = (recipes: number): string =>
  `${recipesWords(recipes)} brought in from Mealie`;
export const noteCheckWords = (n: number): string =>
  `${n} ${n === 1 ? 'has' : 'have'} lines to check`;
export const NOTE_FAILED = 'The import from Mealie stopped';
export const NOTE_FAILED_LINE = 'Recipes brought in before it stopped are kept.';
export const UNDONE = 'Import undone';
