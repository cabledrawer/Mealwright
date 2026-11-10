// A section as its own recipe on Check (0.8, F190, cabledrawer 8 Nov): the pure work on the review.
// A heading the person made its own recipe carries `own` (kept in the review, so a draft keeps it);
// at Save the section's lines and steps go out as a new Made ahead recipe, and the main recipe
// gets one line that uses it. Nothing here is automatic: only the heading's own button sets `own`.

import type { ImportReview, OwnRecipe, ReviewLine, SaveStep } from './client/imports';

type Lines = ImportReview['lines'];

const flat = (text: string) => text.toLowerCase().replace(/\s+/g, ' ').trim();

/** What a heading is about: "For the batter" is "batter". */
export function headingCore(heading: string): string {
  return flat(
    heading
      .replace(/[:\s]+$/, '')
      .replace(/^(for|to make|make)\s+(the\s+)?/i, '')
      .replace(/^the\s+/i, '')
  );
}

/** The most sections of one recipe that can be made their own recipes in one save (the server's). */
export const MOST_OWN = 5;

/** The units "It makes" offers: each is a unit a recipe line can use too, so the main recipe's
 *  one line says "Dosa batter · 4 cups". */
export const OWN_UNITS: { unit: string; words: string }[] = [
  { unit: 'cup', words: 'cups' },
  { unit: 'l', words: 'litres' },
  { unit: 'ml', words: 'ml' },
  { unit: 'g', words: 'g' },
  { unit: 'kg', words: 'kg' }
];

/** "Dosa batter · 4 cups": the one line the main recipe gets. */
export function ownLineWords(own: OwnRecipe): string {
  const unit = OWN_UNITS.find((u) => u.unit === own.unit)?.words ?? own.unit;
  return `${own.name} · ${own.amount}\u00a0${unit}`;
}

/** The place of the heading above line `at` (the line may be a heading itself), or null. */
export function headingOf(lines: Lines, at: number): number | null {
  for (let i = at; i >= 0; i--) if (lines[i]?.kind === 'heading') return i;
  return null;
}

export interface Section {
  /** The ingredient lines under the heading, up to the next heading (not ones added and not named). */
  lines: number[];
  /** The method's heading that goes with it ("For the batter" in the steps too), or null. */
  stepHeading: number | null;
  /** The steps under that heading. */
  steps: number[];
  /** The place of a line outside the section that is this recipe by name ("Dosa batter, as
   *  above"): it becomes the main recipe's one line, so no second line is added. */
  use: number | null;
}

/** A line that points back at an earlier section: "Dosa batter, as above". */
const AS_ABOVE = /\b(as above|from above|see above|from the)\b/i;

/** Whether line `at` is in (or is the heading of) a section other than `heading`'s that was made its own recipe. */
function inOtherOwn(lines: Lines, heading: number, at: number): boolean {
  const h = headingOf(lines, at);
  return h !== null && h !== heading && !!lines[h]!.own;
}

const named = (line: ReviewLine) => line.kind === 'ingredient' && line.words.trim() !== '';

/** The section under the heading at `heading`. */
export function sectionOf(
  review: Pick<ImportReview, 'lines' | 'steps'>,
  heading: number,
  name: string = review.lines[heading]?.own?.name ?? ''
): Section {
  const { lines, steps } = review;
  const inside: number[] = [];
  for (let i = heading + 1; i < lines.length && lines[i]!.kind !== 'heading'; i++) {
    if (named(lines[i]!)) inside.push(i);
  }
  const core = headingCore(lines[heading]?.words ?? '');
  const stepHeading = steps.findIndex(
    (s) => s.kind === 'heading' && core !== '' && headingCore(s.text) === core
  );
  const under: number[] = [];
  if (stepHeading >= 0) {
    for (let i = stepHeading + 1; i < steps.length && steps[i]!.kind !== 'heading'; i++) {
      under.push(i);
    }
  }
  const wanted = [flat(name), core].filter(Boolean);
  const names = (line: ReviewLine) => [line.words, line.new_ingredient?.name ?? ''].map(flat);
  const use = lines.findIndex(
    (line, i) =>
      line.kind === 'ingredient' &&
      !inside.includes(i) &&
      // Never a line inside another section made its own recipe: it goes to that recipe, so it
      // can't stand for this one (the heading's place gets a line instead).
      !inOtherOwn(lines, heading, i) &&
      named(line) &&
      (names(line).some((w) => wanted.includes(w)) ||
        // "Dosa batter, as above" is the batter: its name ends with the heading's own words.
        (core !== '' &&
          AS_ABOVE.test(`${line.written} ${line.note ?? ''}`) &&
          names(line).some((w) => w.endsWith(` ${core}`))))
  );
  return {
    lines: inside,
    stepHeading: stepHeading >= 0 ? stepHeading : null,
    steps: under,
    use: use >= 0 ? use : null
  };
}

/** What the sheet starts with: the name of a line that is this recipe by name ("Dosa batter"),
 *  else the heading's own words ("Batter"), and what that line says it takes. */
export function ownDefaults(
  review: Pick<ImportReview, 'lines' | 'steps'>,
  heading: number
): { name: string; amount: string; unit: string } {
  const core = headingCore(review.lines[heading]?.words ?? '');
  const seed = sectionOf(review, heading, core);
  const user = seed.use !== null ? review.lines[seed.use] : null;
  const words = (user?.new_ingredient?.name ?? user?.words ?? core).trim();
  const name = words ? words[0]!.toUpperCase() + words.slice(1) : '';
  const known = OWN_UNITS.some((u) => u.unit === user?.unit);
  return {
    name,
    amount: user?.amount != null ? String(user.amount) : '',
    unit: known ? user!.unit! : 'cup'
  };
}

/** One section made its own recipe, as Save sends it. */
export interface OwnPart {
  heading: number;
  own: OwnRecipe;
  section: Section;
}

/** The headings made their own recipes, in order, with their sections. */
export function ownParts(review: Pick<ImportReview, 'lines' | 'steps'>): OwnPart[] {
  const parts: OwnPart[] = [];
  review.lines.forEach((line, heading) => {
    if (line.kind === 'heading' && line.own) {
      parts.push({ heading, own: line.own, section: sectionOf(review, heading, line.own.name) });
    }
  });
  return parts;
}

/** The place in `parts` of the section the line at `at` is in, or the section that line is the
 *  use of (`use`), or -1. */
export function ownIndexOf(parts: OwnPart[], at: number, use = false): number {
  return parts.findIndex((part) =>
    use ? part.section.use === at : part.heading === at || part.section.lines.includes(at)
  );
}

/** The lines and steps the main recipe leaves out: the sections' own. */
export function leftOut(parts: OwnPart[]): { lines: Set<number>; steps: Set<number> } {
  const lines = new Set<number>();
  const steps = new Set<number>();
  for (const part of parts) {
    lines.add(part.heading);
    part.section.lines.forEach((i) => lines.add(i));
    if (part.section.stepHeading !== null) steps.add(part.section.stepHeading);
    part.section.steps.forEach((i) => steps.add(i));
  }
  return { lines, steps };
}

/** The steps of a section, as Save sends them. */
export const ownSteps = (steps: ImportReview['steps'], part: OwnPart): SaveStep[] =>
  part.section.steps.map((i) => ({
    kind: 'step',
    text: steps[i]!.text,
    optional: steps[i]!.optional,
    wait: steps[i]!.wait
  }));
