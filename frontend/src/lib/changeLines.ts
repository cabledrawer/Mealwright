// The lines under a change in Recent changes ("Paneer: 0 g → 1 pack · 200 g"). Adding
// 2 packs makes two packets, so two identical lines; those read once, with how many
// times ("…, twice").

import type { ChangeLine } from './client/types';

function dayMonth(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone: 'UTC'
  }).format(new Date(`${iso}T12:00:00Z`));
}

/** One line in plain words: amounts, place and use-by, whatever changed. */
export function lineWords(line: ChangeLine): string {
  const parts: string[] = [];
  if (line.before.display !== line.after.display) {
    parts.push(`${line.before.display} → ${line.after.display}`);
  }
  if (line.place_before && line.place_after && line.place_before.id !== line.place_after.id) {
    parts.push(`${line.place_before.name} → ${line.place_after.name}`);
  }
  if ((line.use_by_before ?? null) !== (line.use_by_after ?? null)) {
    parts.push(line.use_by_after ? `use by ${dayMonth(line.use_by_after)}` : 'no use-by date');
  }
  return `${line.food.name}: ${parts.join(' · ') || 'no change'}`;
}

const TIMES = ['', '', 'twice', 'three times'];

/** The lines to show, identical ones once with how many times. */
export function changeLines(lines: ChangeLine[]): string[] {
  const counts = new Map<string, number>();
  for (const line of lines) {
    const words = lineWords(line);
    counts.set(words, (counts.get(words) ?? 0) + 1);
  }
  return [...counts].map(([words, n]) =>
    n === 1 ? words : `${words}, ${TIMES[n] ?? `${n} times`}`
  );
}
