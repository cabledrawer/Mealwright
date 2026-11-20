// Today's saved copy (see today.svelte.ts): kept apart so the app shell, which only has to forget
// it at sign-out, does not carry the whole Today model (the size limit).

import { forgetWhenSessionEnds } from './api';
import type { TodayData } from './client/today';
import { rememberedLogin } from './offline/device';
import { wipePending } from './offline/wipePending.svelte';
import { session } from './session.svelte';

export const COPY_KEY = 'mealwright.today-copy';

/** Counts the wipes: a read that began before one must not write its copy after it. */
let wipes = 0;

/** How many wipes there have been. */
export function wipeCount(): number {
  return wipes;
}

/** Who the copy belongs to: the signed-in login, else (opening offline) the one this browser last knew. */
function owner(): number | null {
  return session.me?.id ?? rememberedLogin()?.id ?? null;
}

/**
 * What was saved last time Today was read, but only the signed-in login's own (the copy is
 * saved with its owner). Another login's copy, or one in the old format (v 3 since the Use soon tubs became one row per batch and place, F203), is refused and removed.
 * Null when there is none.
 */
export function readCopy(): TodayData | null {
  try {
    const text = localStorage.getItem(COPY_KEY);
    if (!text) return null;
    const me = owner();
    if (me === null) return null; // can't tell whose it is: shown to nobody
    const copy = JSON.parse(text) as { v?: number; login_id?: number; data?: TodayData };
    if (copy.v === 3 && copy.login_id === me && copy.data && Array.isArray(copy.data.waiting)) {
      return copy.data;
    }
    localStorage.removeItem(COPY_KEY);
    return null;
  } catch {
    return null;
  }
}

/**
 * Keep an answer as the copy, for the login that asked, unless that login has signed out or the
 * browser has been wiped since the request began (`began` is `wipes` then).
 */
export function writeCopy(data: TodayData, login: number, began: number): void {
  if (began !== wipes || session.me?.id !== login || wipePending()) return;
  try {
    localStorage.setItem(COPY_KEY, JSON.stringify({ v: 3, login_id: login, data }));
  } catch {
    // Storage blocked or full: Today just won't open offline.
  }
}

/** Forget the copy (sign-out, a wipe in any tab): another login may be next. */
export function forgetToday(): void {
  wipes += 1;
  try {
    localStorage.removeItem(COPY_KEY);
  } catch {
    // Storage blocked: nothing kept there.
  }
}

forgetWhenSessionEnds(forgetToday);
