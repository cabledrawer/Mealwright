// "Wipe pending" (docs/dev/sync-protocol.md section 12): a wipe has started and the phone
// database hasn't been deleted yet, perhaps because deleting it failed. Until it has been,
// nothing here may see or use the old login's data: the phone database isn't opened, nobody
// is found "last signed in" or "waiting", and nobody can sign in on this browser. The
// sign-in page says so, with "Try again" (cabledrawer 18 Oct).
//
// Like the sign-out pending flag, it lives in localStorage, OUTSIDE the phone database it is
// about, so it outlasts a reload. It says nothing about the household: only "1".

export const WIPE_PENDING_KEY = 'mealwright.wipe-pending';

/** This tab's own record, for the sign-in page (and for when localStorage is blocked). */
export const wipeState = $state({ failed: false });

/** A wipe hasn't finished deleting the phone database (in this tab or another). */
export function wipePending(): boolean {
  if (wipeState.failed) return true;
  try {
    return localStorage.getItem(WIPE_PENDING_KEY) === '1';
  } catch {
    return false;
  }
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
  if (!deleted) return;
  try {
    localStorage.removeItem(WIPE_PENDING_KEY);
  } catch {
    // Nothing kept there.
  }
}
