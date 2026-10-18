// "Wipe pending" (docs/dev/sync-protocol.md section 12): a wipe has started and the phone
// database hasn't been deleted yet, perhaps because deleting it failed. Until it has been,
// nothing here may see or use the old login's data: the phone database isn't opened, nobody
// is found "last signed in" or "waiting", and nobody can sign in on this browser without the
// wipe being finished first.
//
// Only a delete that has actually failed (or timed out) is "failed": the sign-in page then
// says so, with "Try again" (cabledrawer 18 Oct). A wipe still deleting, in another tab, isn't:
// a tab sent to sign in meanwhile says nothing about it.
//
// Like the sign-out pending flag, it lives in localStorage, OUTSIDE the phone database it is
// about, so it outlasts a reload. It says nothing about the household: "1" while a wipe is
// deleting, "failed" once a delete has failed.

export const WIPE_PENDING_KEY = 'mealwright.wipe-pending';

/** This tab's own record, for the sign-in page (and for when localStorage is blocked). */
export const wipeState = $state({ failed: false });

/** The flag's value: "1" while a wipe is deleting, "failed" once a delete failed. */
function flag(): string | null {
  try {
    return localStorage.getItem(WIPE_PENDING_KEY);
  } catch {
    return null;
  }
}

/** A wipe hasn't finished deleting the phone database (in this tab or another). */
export function wipePending(): boolean {
  return wipeState.failed || flag() !== null;
}

/**
 * Deleting the phone database has actually failed or timed out (in this tab, another, or
 * before a reload), not just "a wipe is still deleting it".
 */
export function wipeFailed(): boolean {
  return wipeState.failed || flag() === 'failed';
}

/** Set as a wipe starts, before anything is deleted. */
export function markWipePending(): void {
  try {
    localStorage.setItem(WIPE_PENDING_KEY, '1');
  } catch {
    // Storage blocked: this tab's own record (wipeState) still holds a failure.
  }
}

/** The wipe has finished (true) or deleting the phone database failed (false). */
export function wipeFinished(deleted: boolean): void {
  wipeState.failed = !deleted;
  try {
    if (deleted) localStorage.removeItem(WIPE_PENDING_KEY);
    else localStorage.setItem(WIPE_PENDING_KEY, 'failed');
  } catch {
    // Storage blocked: this tab's own record (wipeState) holds a failure.
  }
}

/**
 * Another tab's wipe changed the flag (a `storage` event): it failed, or it has deleted the
 * phone database after all. Anything else (a wipe starting) changes nothing here.
 */
export function heardWipe(event: StorageEvent): void {
  if (event.key !== WIPE_PENDING_KEY) return;
  if (event.newValue === 'failed') wipeState.failed = true;
  else if (event.newValue === null) wipeState.failed = false;
}
