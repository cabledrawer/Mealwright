// The fixed sentences for "couldn't load" and "couldn't add" (FE5, FE6): one pattern, so the
// same failure reads the same on every screen. The connection words never live here: they come
// from `cantReachWords()` / `wordsFor()` in api.ts. Wording proposed, for cabledrawer.

/** "Couldn’t load the plan. Try again." The button beside it carries the retry. */
export const couldntLoad = (what: string): string => `Couldn’t load ${what}. Try again.`;

/** "Couldn’t add that shop. Try again." */
export const couldntAdd = (what: string): string => `Couldn’t add ${what}. Try again.`;
