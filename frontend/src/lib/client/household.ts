// The household's settings (contract 6.3).

import { api } from '#lib/api.js';
import type { AmountsShown, Household, Pints } from './types';

/** The household's settings. Screens that open together ask at the same moment (the sidebar, the
 * plan, the cooking switches); they share one question, so the server is asked once (0.9.5 speed
 * work; proposed, for cabledrawer). Each later read asks again, and a change drops a question still
 * on its way, so nobody is given an answer older than their own change. */
let reading: Promise<Household> | null = null;
export const getHousehold = (): Promise<Household> => {
  if (reading) return reading;
  const asked = api<Household>('GET', '/household');
  reading = asked;
  const done = () => {
    if (reading === asked) reading = null;
  };
  asked.then(done, done);
  return asked;
};
/** A change to the household: a read still on its way is dropped (also used by people.svelte.ts). */
export const changed = <T>(answer: Promise<T>): Promise<T> => {
  reading = null;
  const clear = () => {
    reading = null;
  };
  answer.then(clear, clear);
  return answer;
};

/** Settings: which pint a recipe's "pint" is (an admin only; the server refuses a member). */
export const changePints = (pints: Pints) =>
  changed(api<Household>('PATCH', '/household', { pints }));

/** Settings → Amounts and Onboarding: how amounts are shown (an admin only). */
export const changeAmountsShown = (amounts_shown: AmountsShown) =>
  changed(api<Household>('PATCH', '/household', { amounts_shown }));

/** Cook mode's per-step ingredients, for the household (any person of it may change it). */
export const changeCookPerStep = (on: boolean) =>
  changed(api<Household>('PATCH', '/household', { cook_per_step: on }));

/** Batch cook (Experimental): show it (true) or hide it for everyone (admins only). */
export const changeBatchCook = (on: boolean) =>
  changed(api<Household>('PATCH', '/household', { batch_cook: on }));

/** Onboarding finished or skipped, for the whole household (admins only; never opens again). */
export const finishOnboarding = () =>
  changed(api<Household>('PATCH', '/household', { onboarding_done: true }));

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

/** The household's kitchen, for Batch cook (Experimental; 0.8 wave 6, B1). */
export interface Kitchen {
  hob_rings: number;
  pressure_cookers: number;
  oven: boolean;
  /** False until the household has saved it once. */
  asked: boolean;
}

export const getKitchen = () => api<Kitchen>('GET', '/household/kitchen');

/** Saves the kitchen's equipment; any save counts as asking. */
export const saveKitchen = (kitchen: Pick<Kitchen, 'hob_rings' | 'pressure_cookers' | 'oven'>) =>
  api<Kitchen>('PATCH', '/household/kitchen', kitchen);

/** The most a kitchen is asked for (the server's own limits). */
export const MOST_HOB_RINGS = 12;
export const MOST_PRESSURE_COOKERS = 6;
