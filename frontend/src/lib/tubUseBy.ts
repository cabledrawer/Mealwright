// A new tub's use-by, worked out the way the server does (`batches.tub_use_by`): the household's
// days in the fridge, or months in the freezer, from the meal's day (cabledrawer 17 Oct). "Eat it
// on…" (F65) offers only meals up to it (F128, cabledrawer 3 Nov: ""Eat it on…" in Today's review
// only offers meals up to the tub's use-by."): the server refuses a later one.

import { addDays } from './dates';

/** How long the household's tubs keep (Settings). */
export interface TubLife {
  fridgeDays: number;
  freezerMonths: number;
}

/** The date `months` after `iso`, kept inside a shorter month (31 Oct + 4 months is 28 Feb). */
export function addMonths(iso: string, months: number): string {
  const [year = 0, month = 1, day = 1] = iso.split('-').map(Number);
  const index = month - 1 + months;
  const y = year + Math.floor(index / 12);
  const m = (index % 12) + 1;
  const last = new Date(Date.UTC(y, m, 0)).getUTCDate();
  return `${y}-${String(m).padStart(2, '0')}-${String(Math.min(day, last)).padStart(2, '0')}`;
}

/** The day a meal's tubs count from: its own day, or today when it is cooked ahead (F159). */
export const cookingDay = (mealDay: string, today: string) => (mealDay < today ? mealDay : today);

export function tubUseBy(kind: 'fridge' | 'freezer', fromDay: string, life: TubLife): string {
  return kind === 'freezer'
    ? addMonths(fromDay, life.freezerMonths)
    : addDays(fromDay, life.fridgeDays);
}

/** Both use-bys for "Any left over?"; each only when the household's tub life for it is known. */
export function leftoverUseBy(
  mealDay: string,
  life: TubLife | null
): { useByFridge?: string; useByFreezer?: string } {
  return {
    ...(life?.fridgeDays ? { useByFridge: tubUseBy('fridge', mealDay, life) } : {}),
    ...(life?.freezerMonths ? { useByFreezer: tubUseBy('freezer', mealDay, life) } : {})
  };
}

/** The last day any "Eat it on…" meal can be: the later use-by (the freezer's). */
export function eatOnUntil(useBy: { useByFridge?: string; useByFreezer?: string }): string | null {
  const days = [useBy.useByFridge, useBy.useByFreezer].filter((d): d is string => !!d);
  return days.length ? days.sort().at(-1)! : null;
}

/**
 * The "Eat it on…" meals a tub with this use-by can go to: up to the use-by day itself. With no
 * use-by known, none: never a meal the server will refuse.
 */
export function eatOnUpTo<T extends { day: string }>(options: T[], useBy: string): T[] {
  return useBy ? options.filter((option) => option.day <= useBy) : [];
}
