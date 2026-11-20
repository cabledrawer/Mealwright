// Helpers the spec files used to declare again and again (D9, CL20), next to clock.ts. Only the
// copies that were the same went here; a spec whose own version differs keeps it.
import { expect, test, type Page } from './clock.ts';

/** A new idempotency key for one API write. */
export const key = () => ({ 'idempotency-key': crypto.randomUUID() });

/** An ISO date (2026-10-17) a number of days later (or earlier, when negative). */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** A name that is new in every test and project, so tests that share one app don't meet each
 *  other's rows. */
export const stamp = () => `${test.info().project.name.replace(/\W/g, '')}${Date.now().toString(36)}`;

/** The household's meal slot ids by name (Snack is off in a new household). The four standard names
 *  are known to exist; any other name may be missing. */
export type SlotIds = Record<'Breakfast' | 'Lunch' | 'Dinner' | 'Snack', number> & Record<string, number>;

/** An API call as the signed-in page, which must succeed (any 2xx). */
export async function call(page: Page, method: 'POST' | 'PUT' | 'DELETE' | 'PATCH', path: string, data?: object) {
  const response = await page.request.fetch(`/api/v1${path}`, { method, data, headers: key() });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBe(true);
  return (await response.json()) as Record<string, any>;
}
