// The words of "By ingredient" on Drafts (cabledrawer 15 Nov, 0.9.5-beta.2; mockups
// Dark-MealieByIngredient2-Desktop and -Phone, not yet formally approved). Every line is
// proposed, for cabledrawer, except where it is the mockup's own text. Listed in
// docs/dev/words.md, section 82. One place, so the phone and the computer say the same thing.

import { count } from './mealieWords';
import { plural } from './words.js';
import { couldntLoad } from './errorWords.js';

export const SWITCH_LABEL = 'Show';
export const BY_RECIPE = 'By recipe';
export const BY_INGREDIENT = 'By ingredient';
export const TITLE = 'Drafts · From Mealie';

/** "1 ingredient", "46 ingredients". */
const ingredients = (n: number) => `${count(n)} ${plural(n, 'ingredient', 'ingredients')}`;
/** "1 draft", "46 drafts". */
export const draftsWords = (n: number) => `${count(n)} ${plural(n, 'draft', 'drafts')}`;
/** "1 recipe", "3 recipes". */
const recipes = (n: number) => `${count(n)} ${plural(n, 'recipe', 'recipes')}`;

/** The progress line on a computer: "47 ingredients still to answer". */
export const leftWords = (n: number): string => `${ingredients(n)} still to answer`;
/** The progress line on a phone: "47 ingredients to answer · 12 recipes ready". */
export const leftPhoneWords = (left: number, ready: number): string =>
  `${ingredients(left)} to answer · ${recipes(ready)} ready`;
/** After the computer's line: "· 12 recipes ready so far". */
export const readyWords = (ready: number): string => `· ${recipes(ready)} ready so far`;

export const LEAD =
  'Answer an ingredient once and every draft that uses it is fixed. Most-used first. Nothing is saved until you answer; a recipe whose lines are all answered moves to Recipes.';
export const LEAD_PHONE = 'Answer one once and every draft using it is fixed. Most-used first.';

/** A row's count: "in 46 drafts" on a computer, "46 drafts" on a phone. */
export const inDraftsWords = (n: number, wide: boolean): string =>
  wide ? `in ${draftsWords(n)}` : draftsWords(n);

/** The foot of the list when it is cut short. */
export const SHOWING_FIRST = 'Showing the most-used first';
export const SHOW_ALL = 'Show all';

/** The answer panel. */
export const usedIn = (n: number): string => `Used in ${draftsWords(n)}, written as`;
export const WRITTEN_AS = 'Written as';
export const MORE_LINES = '+ more';
/** "+ more" pressed (F259, proposed, for cabledrawer): every way the lines are written. */
export const FEWER_LINES = 'Show fewer';
export const timesWords = (n: number): string => `${n} times`;
export const moreWaysWords = (n: number): string => `and ${n} more ${n === 1 ? 'way' : 'ways'}`;
export const OPTION_HAVE = 'It’s an ingredient I already have';
export const OPTION_HAVE_PHONE = 'An ingredient I already have';
export const OPTION_NEW = 'A new ingredient';
export const OPTION_TEXT = 'Keep it as plain text';
export const TEXT_HINT = 'Shown in the recipe, never on the shopping list or taken from the pantry';
export const TEXT_HINT_PHONE = 'Never on the list or taken from the pantry';
export const WHICH_ONE = 'Which one';
export const CHANGE_IT = 'Change';
export const SUGGESTED = 'Suggested from your Ingredients. Its pantry place comes with it.';
export const NO_SUGGESTION = 'Type any of its names to find it in your Ingredients.';
export const NAME = 'Name';
export const KEPT = 'Where it’s kept';

export const useForAll = (n: number, phone = false): string =>
  phone ? `Use for all ${count(n)}` : `Use for all ${draftsWords(n)}`;
export const SKIP = 'Skip for now';
export const SKIP_PHONE = 'Skip';
export const BACK_TO_LIST = 'Back to the list';
export const WORKING = 'Saving…';

/** Everything is answered. */
export const ALL_DONE_TITLE = 'Every ingredient is answered';
export const ALL_DONE =
  'No Mealie draft is waiting on an ingredient. Recipes whose lines are all answered are in Recipes.';
export const NONE_LEFT_BY_INGREDIENT = 'No ingredients to answer';

export const COULDNT_LOAD = couldntLoad('the ingredients');
export const COULDNT_ANSWER = 'Couldn’t save that answer. Try again.';
/** The group had nothing left: another person answered it first. */
export const ALREADY_ANSWERED = 'That ingredient was already answered. The list is up to date.';
