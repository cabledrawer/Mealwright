// The household's settings (contract 6.3).

import { api } from '$lib/api';
import type { Household } from './types';

export const getHousehold = () => api<Household>('GET', '/household');

export const patchHousehold = (patch: { time_zone?: string; cup_ml?: 240 | 250 }) =>
  api<Household>('PATCH', '/household', patch);

/**
 * The cup size to start with (spec "Decided for 0.2"): 240 ml for US English, 250 ml
 * everywhere else.
 */
export function defaultCupMl(language: string): 240 | 250 {
  return language.toLowerCase() === 'en-us' ? 240 : 250;
}

/**
 * First run: an admin's browser tells the server the household's time zone and cup
 * size, once (contract 6.3). The time zone is the device's setting, never its
 * location. Members never send it. Returns whether anything was sent.
 */
export async function settleHousehold(
  role: 'admin' | 'member',
  device: { timeZone: string | undefined; language: string } = {
    timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    language: navigator.language
  }
): Promise<boolean> {
  if (role !== 'admin' || !device.timeZone) return false;
  const household = await getHousehold();
  if (household.time_zone !== null) return false;
  const patch: { time_zone: string; cup_ml?: 240 | 250 } = { time_zone: device.timeZone };
  if (household.cup_ml === null) patch.cup_ml = defaultCupMl(device.language);
  await patchHousehold(patch);
  return true;
}
