// The one breakpoint the whole app switches layout at (FE29). The CSS media queries use the same
// 768 px; the JavaScript checks that need the same answer import these instead of retyping it.

/** The width below which the phone layout is used (bottom tabs, bottom sheets). */
export const PHONE_QUERY = '(max-width: 767px)';
/** The computer layout: the other side of the same line. */
export const DESKTOP_QUERY = '(min-width: 768px)';

/** Whether the screen is a phone's width right now (false when there is no screen to ask). */
export function isPhone(): boolean {
  return typeof matchMedia === 'function' && matchMedia(PHONE_QUERY).matches;
}
