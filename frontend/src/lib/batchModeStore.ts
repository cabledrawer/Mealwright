// What the phone keeps of a Batch cook session (batch cook mode's last schedule and the marks that
// wait to be sent), so a reload while offline carries on. Small on its own, so the Plan can remove
// a session's copy without loading batch cook mode.

export const batchModeKey = (id: number) => `mealwright.batchmode.${id}`;

/** The phone's copy of a session is removed when the session ends (cooked, or taken off the
 * plan), not kept until sign-out (RF3, S5). */
export function forgetBatchMode(id: number): void {
  try {
    localStorage.removeItem(batchModeKey(id));
  } catch {
    // Storage blocked: nothing was kept.
  }
}
