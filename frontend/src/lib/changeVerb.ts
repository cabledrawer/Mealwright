// Which first word of a Recent changes row is a verb to show in bold ("Added Tahini",
// "Renamed Rice to Basmati rice"). Decided by the kind of change and the server's own
// wording of its summary (api/v1/foods.py), never by the ingredient's name: a change to an
// ingredient called "Added sugar" ("Added sugar is now a staple") has no verb to bold.

import type { Change } from './client/types';

/** Kinds whose summary always starts with a verb. */
const VERB_KINDS = new Set(['food_created', 'food_removed', 'merged', 'split', 'undo']);

/** The other ways an edit's summary can end, after the ingredient's name ("{name} is now a staple"). */
const EDIT_TAIL =
  / (is (now|no longer) a staple|is now counted .+|is now in .+|no longer has a running-low level|runs low at .+|is usually bought by the .+)$/;

/** Does the first word of this change's summary name what was done? */
export function startsWithVerb(change: Pick<Change, 'kind' | 'summary'>): boolean {
  if (VERB_KINDS.has(change.kind)) return true;
  // "Renamed Rice to Basmati rice": the one edit worded verb first, "Renamed {name} to {new}".
  return (
    change.kind === 'food_edited' &&
    /^Renamed .+ to .+$/.test(change.summary) &&
    !EDIT_TAIL.test(change.summary)
  );
}
