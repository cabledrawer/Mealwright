// The undo window, for every sentence that names it (0.9.5-beta.3, D4, CL9). Fixed, not a
// setting (cabledrawer 11 Nov: "it is not a setting in 0.9"). The server's one number is
// `UNDO_DAYS` in backend/src/mealwright/household.py, sent as the household's `undo_days`;
// keep the two the same.

/** How many days a change can be undone. */
export const UNDO_DAYS = 7;

/** "7 days". */
export const UNDO_SPAN = `${UNDO_DAYS} days`;
