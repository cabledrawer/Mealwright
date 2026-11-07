// "Too late to freeze" (cabledrawer 7 Nov, 0.8): once a Use by date has passed (from the day after)
// To freezer stays on the packet but can't be pressed. On the Use by day itself it works, and
// Best before food can always be frozen. The server refuses the same case (422
// too_late_to_freeze), so this only saves a press that would fail.

import type { DateKind } from './client/types';

export const TOO_LATE_TO_FREEZE = 'Too late to freeze: the use by date has passed.';

/** `daysLeft` is the server's count from the household's today (negative once it has passed). */
export const tooLateToFreeze = (kind: DateKind, daysLeft: number | null): boolean =>
  kind === 'use_by' && daysLeft !== null && daysLeft < 0;
