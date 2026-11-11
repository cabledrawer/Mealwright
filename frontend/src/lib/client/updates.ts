// Settings → About (backend api/v1/updates.py, spec section 7 "Updates"): the running version,
// the day it was released and, for an admin, Check now and the last answer. Reading it never
// connects anywhere; only Check now does, through the server's outbound gate.

import { api } from '#lib/api.js';

/** up_to_date: nothing newer. newer: `latest` is out. failed: couldn't check. off: the Privacy
 *  switch is off, so nothing was asked. */
export type CheckOutcome = 'up_to_date' | 'newer' | 'failed' | 'off';

export interface LastCheck {
  outcome: CheckOutcome;
  /** The newer version's tag ("v0.9.1"); only with "newer". */
  latest: string | null;
  /** When the answer came ("2026-11-11T09:00:00Z"). */
  checked_at: string;
}

export interface Updates {
  /** The server's version, as Python writes it ("0.9.0"). */
  version: string;
  /** The day it was released ("2026-11-11"), written into the code with the release. */
  released: string;
  /** Where new versions are listed (the person's own click). */
  releases_page: string;
  /** An admin: may use Check now, and sees `daily` and `last`. */
  can_check: boolean;
  /** Whether the daily check's switch is on (null for a member). */
  daily: boolean | null;
  last: LastCheck | null;
}

export const getUpdates = () => api<Updates>('GET', '/updates');

export const checkNow = () => api<Updates>('POST', '/updates/check');
