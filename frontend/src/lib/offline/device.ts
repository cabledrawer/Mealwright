// This device's ID (docs/dev/sync-protocol.md section 11.8): random, made the first time the
// app runs after a sign-in, kept in the phone database's `meta`, and sent only to our own
// server, on every batch of changes.
//
// Before 0.3 it was kept in localStorage. The first time this version runs it moves into
// `meta` with the same value (so the server still sees the same device), and the old
// localStorage key is cleared (cabledrawer 18 Oct).

import { newChangeId } from '$lib/changeId';
import { getMeta, phoneExists, setMeta, unsealPhone } from './phone';
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

/** On starting the app signed in: load the device ID and note who is signed in. */
export async function startDevice(me: SignedIn): Promise<void> {
  // Signed in here: if another tab had wiped this browser, the database may be made again.
  unsealPhone();
  await loadDeviceId();
  try {
    await setMeta({
      login_id: me.id,
      login_name: me.name,
      username: me.username,
      role: me.role,
      protocol: 1
    });
  } catch {
    // No IndexedDB here: the app still works while connected.
  }
}

/**
 * The login this device's copy and device ID belong to (`meta`), or null when there is none
 * (never signed in here, or wiped). Looking doesn't make a new, empty database.
 */
export async function storedLoginId(): Promise<number | null> {
  try {
    if (!(await phoneExists())) return null;
    const id = await getMeta('login_id');
    return typeof id === 'number' ? id : null;
  } catch {
    return null;
  }
}

/**
 * Who was last signed in on this device, for opening the app while the server can't be
 * reached (11.4). Null when nobody has signed in here since the phone database was made.
 */
export async function lastSignedIn(): Promise<SignedIn | null> {
  // Signed out (perhaps offline): nobody. Looking doesn't make a new, empty database.
  if (signOutPending() || !(await phoneExists())) return null;
  try {
    const [id, name, username, role] = await Promise.all([
      getMeta('login_id'),
      getMeta('login_name'),
      getMeta('username'),
      getMeta('role')
    ]);
    if (typeof id !== 'number' || typeof name !== 'string' || typeof username !== 'string') {
      return null;
    }
    await loadDeviceId();
    return { id, name, username, role: typeof role === 'string' ? role : 'member' };
  } catch {
    return null;
  }
}
