// The "Finish setup" row's ring (cabledrawer 13 Nov, option A; mockup Dark-FinishSetup095-Phone): a
// part-filled amber ring and "2 of 5". Amber, not green, so it never reads as done.

/** The steps of set-up, as the phone's onboarding walks them (spec: "phone step 1 of 5"). */
export const SETUP_STEPS = ['account', 'amounts', 'household', 'shops', 'packs'] as const;

/**
 * How many steps are done, from what Settings already knows. The server keeps no record of which
 * step was done, so this counts what can be seen: the admin's own account (they are signed in),
 * a household with more than one person, and at least one shop. Whether Amounts or the starter
 * packs were chosen can't be told, so they aren't counted (proposed, for cabledrawer). `null`
 * (not read yet, or offline) counts as not done.
 */
export function stepsDone(known: { people: number | null; shops: number | null }): number {
  let done = 1;
  if (known.people !== null && known.people > 1) done += 1;
  if (known.shops !== null && known.shops > 0) done += 1;
  return done;
}

/** People who count towards "a household of more than one": not a shared login (a kitchen
 * tablet isn't someone who eats; cabledrawer 13 Nov). */
export const peopleWhoCount = (people: { login?: { shared?: boolean } | null }[]): number =>
  people.filter((person) => person.login?.shared !== true).length;

/** The words after the label, "2 of 5". */
export const ringWords = (done: number, of: number = SETUP_STEPS.length) => `${done} of ${of}`;

const CENTRE = 12;
const RADIUS = 8.5;

/**
 * The filled part of the ring, as an SVG path that starts at the top and runs clockwise, a
 * fraction `done / of` of the way round. `null` when nothing is done (no arc, so no stray dot);
 * a whole ring is two half arcs, as one arc can't start and end on the same point.
 */
export function ringArc(done: number, of: number = SETUP_STEPS.length): string | null {
  const fraction = Math.min(Math.max(done / of, 0), 1);
  if (fraction === 0) return null;
  const top = `M${CENTRE} ${CENTRE - RADIUS}`;
  const half = (to: string) => `A${RADIUS} ${RADIUS} 0 0 1 ${to}`;
  if (fraction === 1)
    return `${top}${half(`${CENTRE} ${CENTRE + RADIUS}`)}${half(`${CENTRE} ${CENTRE - RADIUS}`)}`;
  const angle = fraction * 2 * Math.PI;
  const x = (CENTRE + RADIUS * Math.sin(angle)).toFixed(2);
  const y = (CENTRE - RADIUS * Math.cos(angle)).toFixed(2);
  return `${top}A${RADIUS} ${RADIUS} 0 ${fraction > 0.5 ? 1 : 0} 1 ${x} ${y}`;
}
