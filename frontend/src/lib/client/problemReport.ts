// Settings → About → Report a problem (backend api/v1/report.py, spec section 7 "Bug reports"):
// the report the server builds, with personal details already removed. Getting it never
// connects anywhere outside, and the server never sends it: the person does.

import { api } from '#lib/api.js';

export interface ProblemReport {
  /** "Mealwright 0.9.0". */
  version: string;
  /** "Safari 18 · iPhone". */
  browser: string;
  /** Recent errors from the server's log, oldest first, personal details removed. */
  errors: string[];
  /** False for a member: only an admin's report has the log's errors. */
  errors_included: boolean;
  /** The project's new-issue page on GitHub (the title and text are added here). */
  new_issue_page: string;
}

export const getProblemReport = () => api<ProblemReport>('GET', '/problem-report');
