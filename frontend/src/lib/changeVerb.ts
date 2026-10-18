// Which first word of a Recent changes row is a verb to show in bold ("Added Tahini",
// "Renamed Rice to Basmati rice"). Decided by the kind of change and the server's own
// wording of its summary (api/v1/foods.py), never by the ingredient's name: a change to an
// ingredient called "Added sugar" ("Added sugar is now a staple") has no verb to bold.

import type { Change } from './client/types';

/** Kinds whose summary always starts with a verb. */
const VERB_KINDS = new Set(['food_created', 'food_removed', 'merged', 'split', 'undo']);

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
  if (VERB_KINDS.has(change.kind)) return true;
  // The edits worded verb first. An edit of an ingredient that happens to be called "Renamed
  // rice" starts with its name instead, which the ending gives away.
  return (
    change.kind === 'food_edited' &&
    !EDIT_TAIL.test(change.summary) &&
    VERB_FIRST_EDIT.some((re) => re.test(change.summary))
  );
}
