// This device's ID (docs/dev/sync-protocol.md section 11.8): random, made the first time the
// app runs after a sign-in, kept in the phone database's `meta`, and sent only to our own
// server, on every batch of changes.
//
// Before 0.3 it was kept in localStorage. The first time this version runs it moves into
// `meta` with the same value (so the server still sees the same device), and the old
// localStorage key is cleared (cabledrawer 18 Oct).

import { newChangeId } from '#lib/changeId.js';
import {
  getMeta,
  phoneExists,
  readPhone,
  setMeta,
  UNREADABLE,
  unsealPhone,
  type Unreadable
} from './phone';
import { signOutPending } from './signOutPending';

/** Where 0.2 kept the device ID. Empty from 0.3 on. */
export const OLD_DEVICE_KEY = 'mealwright.device-id';

const UUID = /^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;
const isId = (value: unknown): value is string => typeof value === 'string' && UUID.test(value);

let current: string | null = null;

function oldId(): string | null {
  try {
    return localStorage.getItem(OLD_DEVICE_KEY);
  } catch {
    return null;
  }
}

function clearOld(): void {
  try {
    localStorage.removeItem(OLD_DEVICE_KEY);
  } catch {
    // Nothing kept there to clear.
  }
}

/**
 * Read the device ID from `meta`, making it (or moving 0.2's into it) when there is none.
 * The app runs this before it sends anything.
 */
export async function loadDeviceId(): Promise<string> {
  let id: string | undefined;
  try {
    id = await getMeta('device_id');
    if (!isId(id)) {
      const old = oldId();
      id = isId(old) ? old : isId(current) ? current : newChangeId();
      await setMeta({ device_id: id });
    }
    clearOld();
  } catch {
    // No IndexedDB here (a locked-down private window): keep it for this visit only.
    id = current ?? newChangeId();
  }
  current = id;
  return id;
}

/** The device ID, once loadDeviceId() has run (a new one for this visit before that). */
export function deviceId(): string {
  return (current ??= newChangeId());
}

/** Forget the device ID (the database it lived in has been wiped). */
export function forgetDeviceId(): void {
  current = null;
}

/** Who is signed in on this device, kept so the app can open offline as them (11.1). */
export interface SignedIn {
  id: number;
  name: string;
  username: string;
  role: string;
}

/**
 * Whose the phone database is, kept OUTSIDE it as well (localStorage): when it can't be read,
 * the same login can still carry on, since it never wipes anything (cabledrawer 18 Oct, sync
 * protocol 11.5). Only the login's number and username, and only on this device; a wipe
 * removes it with everything else.
 */
export const LOGIN_KEY = 'mealwright.login';

export interface Remembered {
  id: number;
  username: string;
}

/** The login the phone database was last written for, or null when none is known. */
export function rememberedLogin(): Remembered | null {
  try {
    const found: unknown = JSON.parse(localStorage.getItem(LOGIN_KEY) ?? 'null');
    if (typeof found !== 'object' || found === null) return null;
    const { id, username } = found as Record<string, unknown>;
    return typeof id === 'number' && typeof username === 'string' ? { id, username } : null;
  } catch {
    return null;
  }
}

function remember(me: Remembered | null): void {
  try {
    if (me) localStorage.setItem(LOGIN_KEY, JSON.stringify({ id: me.id, username: me.username }));
    else localStorage.removeItem(LOGIN_KEY);
  } catch {
    // Storage blocked: not known, so an unreadable phone database warns as for anyone.
  }
}

/**
 * On starting the app signed in: load the device ID and note who is signed in.
 *
 * Never over another login's device (11.8): the callers wipe that first, or turn this login
 * away. If, all the same, `meta` names someone else by now (another tab), or can't be read,
 * nothing here is written: the device ID is kept for this visit only.
 */
export async function startDevice(me: SignedIn): Promise<void> {
  // Signed in here: if another tab had wiped this browser, the database may be made again.
  unsealPhone();
  const stored = await storedLoginId();
  if (stored === UNREADABLE || (stored !== null && stored !== me.id)) return;
  await loadDeviceId();
  // Forgotten while `meta` is written, so the two never name different logins.
  remember(null);
  try {
    await setMeta({
      login_id: me.id,
      login_name: me.name,
      username: me.username,
      role: me.role,
      protocol: 1
    });
    remember(me);
  } catch {
    // No IndexedDB here: the app still works while connected.
  }
}

/**
 * The login this device's copy and device ID belong to (`meta`), or null when there is none
 * (never signed in here, or wiped). UNREADABLE when the phone database couldn't be read: not
 * the same as none. Looking doesn't make a new, empty database.
 */
export async function storedLoginId(): Promise<number | null | Unreadable> {
  try {
    if (!(await phoneExists())) return null;
    const id = await readPhone((db) => db.get('meta', 'login_id'));
    return typeof id === 'number' ? id : null;
  } catch {
    return UNREADABLE;
  }
}

/**
 * Who `meta` says was last signed in here, or null when nobody is. Rejects when the phone
 * database can't be read. Call it only once phoneExists() has said the database is there.
 */
export async function readSignedIn(): Promise<SignedIn | null> {
  const [id, name, username, role] = await readPhone((db) =>
    Promise.all([
      db.get('meta', 'login_id'),
      db.get('meta', 'login_name'),
      db.get('meta', 'username'),
      db.get('meta', 'role')
    ])
  );
  if (typeof id !== 'number' || typeof name !== 'string' || typeof username !== 'string') {
    return null;
  }
  return { id, name, username, role: typeof role === 'string' ? role : 'member' };
}

/**
 * Who was last signed in on this device, for opening the app while the server can't be
 * reached (11.4). Null when nobody has signed in here since the phone database was made, or
 * when it can't be read (then the app can't open offline, and shows the sign-in page).
 */
export async function lastSignedIn(): Promise<SignedIn | null> {
  try {
    // Signed out (perhaps offline): nobody. Looking doesn't make a new, empty database.
    if (signOutPending() || !(await phoneExists())) return null;
    const who = await readSignedIn();
    if (who) await loadDeviceId();
    return who;
  } catch {
    return null;
  }
}
