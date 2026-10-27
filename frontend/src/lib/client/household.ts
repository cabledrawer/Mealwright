// The household's settings (contract 6.3).

import { api } from '#lib/api.js';
import type { Household, Pints } from './types';

export const getHousehold = () => api<Household>('GET', '/household');

/** Settings: which pint a recipe's "pint" is (an admin only; the server refuses a member). */
export const changePints = (pints: Pints) => api<Household>('PATCH', '/household', { pints });

/**
 * The cup size to start with (spec "Decided for 0.2"): 240 ml for US English, 250 ml
 * everywhere else.
 */
export function defaultCupMl(language: string): 240 | 250 {
  return language.toLowerCase() === 'en-us' ? 240 : 250;
}

const SENT_KEY = 'mealwright.household-from-browser';

/**
 * First run: an admin's browser offers the server the household's time zone and cup
 * size (POST /household/from-browser). The server keeps each only while it has none,
 * so this never changes a setting already made. Once per sign-in (remembered for this
 * tab's session), never for members. The time zone is the device's setting, never its
 * location. Returns whether it was sent.
 */
export async function settleHousehold(
  me: { id: number; role: 'admin' | 'member' },
  device: { timeZone: string | undefined; language: string } = {
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    language: navigator.language
  }
): Promise<boolean> {
  if (me.role !== 'admin' || !device.timeZone) return false;
  const key = `${SENT_KEY}.${me.id}`;
  try {
    if (sessionStorage.getItem(key)) return false;
  } catch {
    // Storage blocked: send it; the server ignores values it already has.
  }
  await api<Household>('POST', '/household/from-browser', {
    time_zone: device.timeZone,
    cup_ml: defaultCupMl(device.language)
  });
  try {
    sessionStorage.setItem(key, 'sent');
  } catch {
    // Fine: it's harmless to send again.
  }
  return true;
}
