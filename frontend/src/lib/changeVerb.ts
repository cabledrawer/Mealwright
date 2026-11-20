// Which first word of a Recent changes row is a verb to show in bold ("Added Tahini",
// "Renamed Rice to Basmati rice"). Decided by the kind of change and the server's own
// wording of its summary (api/v1/foods.py), never by the ingredient's name: a change to an
// ingredient called "Added sugar" ("Added sugar is now a staple") has no verb to bold.

import type { Change } from './client/types';

/** Kinds whose summary always starts with a verb. */
const VERB_KINDS = new Set([
  'food_created',
  'food_removed',
  'merged',
  'split',
  'undo',
  'recipe_imported',
  // Mealie drafts answered by ingredient (0.9.5-beta.2): "Answered “soya sauce” in 46 drafts".
  'mealie_drafts_answered',
  // The rest of Settings › Recent changes (F172): stock, plan, cooking, recipes and removals.
  'added',
  'used',
  'binned',
  'set_left',
  'moved',
  'to_freezer',
  'use_by',
  'shopped',
  'found',
  'repacked',
  'cooked',
  'stocktake',
  'recipe_removed',
  'draft_removed',
  'shop_removed',
  'shop_added',
  'shop_renamed',
  'place_removed',
  // Settings (RF5, H8): places added and renamed, shops and places put in order, the kitchen's
  // equipment, the Batch cook switch, the pint and Ingredients for each step.
  'place_added',
  'place_renamed',
  'shops_ordered',
  'places_ordered',
  'kitchen_changed',
  'batch_cook_switch',
  'pints_changed',
  'cook_step_changed',
  // Settings › Amounts and Onboarding (0.9 U2): how amounts are shown.
  'amounts_shown_changed',
  // Settings › People (0.9 A1): people added, changed and removed, sign-in links, the
  // "Who's this?" switch and the household's name.
  'person_added',
  'person_changed',
  'person_removed',
  'person_login',
  'whos_this_switch',
  'household_renamed',
  // Settings › Outside connections (D4, BE5): "Switched recipe import on", "Added wiki.home.example
  // to Your own network", "Removed … from Your own network".
  'connection_changed',
  'own_network_added',
  'own_network_removed'
]);

/** The other ways an edit's summary can end, after the ingredient's name ("{name} is now a staple"). */
const EDIT_TAIL =
  / (is (now|no longer) a staple|is now counted .+|is now in .+|now lives in .+|has no usual (place|shop)|no longer has a running-low level|runs low at .+|is usually bought by the .+)$/;

/** The edits worded verb first: "Renamed {name} to {new}", "Added other name {other} to {name}", ... */
const VERB_FIRST_EDIT = [
  /^Renamed .+ to .+$/,
  /^Added other name .+ to .+$/,
  /^Removed other name .+ from .+$/,
  /^Forgot your weight of (1\u00a0cup of|one) .+$/
];

/** Does the first word of this change's summary name what was done? */
export function startsWithVerb(change: Pick<Change, 'kind' | 'summary'>): boolean {
  if (VERB_KINDS.has(change.kind) || change.kind.startsWith('plan_')) return true;
  // The edits worded verb first. An edit of an ingredient that happens to be called "Renamed
  // rice" starts with its name instead, which the ending gives away.
  return (
    change.kind === 'food_edited' &&
    !EDIT_TAIL.test(change.summary) &&
    VERB_FIRST_EDIT.some((re) => re.test(change.summary))
  );
}
