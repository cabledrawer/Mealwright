// How many chips a Month day can show (F47). A day shows up to three things, the cooking first,
// then "+N more"; when the whole month has to fit one screen and the day is short (six weeks on a
// small screen), it shows fewer, never more, so nothing is cut off. The sizes are the CSS's
// (PlanMonth.svelte), in pixels at the usual text size; `scale` is the page's text size over 16 px.

/** The most things a day shows before "+N more" (cabledrawer 28 Oct). */
export const MOST_CHIPS = 3;

const PAD = 4; // the day's padding, top and bottom each
const TOP = 18 + 2; // the number row and the gap under it
const CHIP = 18; // one chip
const GAP = 2; // between chips
const MORE = 15; // the "+N more" row

/**
 * How many of `count` things fit in a day `height` px tall (0 when it has not been measured:
 * then the most is shown). The rest become "+N more", which takes a row of its own.
 */
export function chipsThatFit(height: number, count: number, scale = 1, most = MOST_CHIPS): number {
  const wanted = Math.min(count, most);
  if (height <= 0 || count <= 0) return wanted;
  const room = height - (2 * PAD + TOP) * scale;
  const rows = (n: number) => (n * CHIP + Math.max(0, n - 1) * GAP) * scale;
  // Nothing left over: no "+N more" row is needed.
  if (count <= most && rows(count) <= room) return count;
  const more = (GAP + MORE) * scale;
  let shown = wanted;
  while (shown > 0 && rows(shown) + more > room) shown--;
  return shown;
}
