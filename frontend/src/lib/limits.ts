// The limits the server and the screens share, one copy in this layer (CL22). Each must say
// the same as the server's (backend/tests/test_frontend_limits.py compares them), so a screen
// never lets someone type what the server will refuse. Names start MAX_ (or MIN_).

/** Ingredient lines and headings together in a recipe. */
export const MAX_LINES = 200;
/** Steps and headings together in a recipe. */
export const MAX_STEPS = 100;
/** The most tags on a recipe, and the most characters in one. */
export const MAX_TAGS = 20;
export const MAX_TAG_CHARS = 40;
/** The longest time a step or a recipe takes: ten days, in minutes. */
export const MAX_MINUTES = 14_400;
/** The most a recipe serves. */
export const MAX_SERVES = 99;
/** The fewest characters in a password. */
export const MIN_PASSWORD = 12;
