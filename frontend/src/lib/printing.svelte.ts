// Is the page being printed? The print layouts (docs/spec.md "Print", cabledrawer 13 Nov) have a
// few lines that only exist on paper (a heading with the date, a footer). They are drawn only
// while printing, so a screen never holds a second copy of the list's words.
import { flushSync } from 'svelte';
import { dayMonthOf } from './dates.js';

class Printing {
  on = $state(false);
}

export const printing = new Printing();

/**
 * Start following the browser's print state; returns the way to stop. The browser asks for
 * a print with `beforeprint` (drawn at once, before it takes the page) and tells the
 * print media with a change on `matchMedia('print')` (the print preview, and a test).
 */
export function watchPrinting(): () => void {
  const media = matchMedia('print');
  const set = (on: boolean) => {
    printing.on = on;
    flushSync();
  };
  const before = () => set(true);
  const after = () => set(media.matches);
  const change = () => set(media.matches);
  printing.on = media.matches;
  window.addEventListener('beforeprint', before);
  window.addEventListener('afterprint', after);
  media.addEventListener('change', change);
  return () => {
    window.removeEventListener('beforeprint', before);
    window.removeEventListener('afterprint', after);
    media.removeEventListener('change', change);
    printing.on = false;
  };
}

/** "13 Nov": the day of printing, in the words of the print layouts. */
export function printedOn(now: number = Date.now()): string {
  return dayMonthOf(now);
}
