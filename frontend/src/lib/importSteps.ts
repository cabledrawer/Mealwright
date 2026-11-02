// "Split into shorter steps" on Check (spec F13, cabledrawer 28 Oct): a long step is shown split
// into shorter ones before anything is kept. Never automatic. Pure text work: no server.

/** A step with at least this many sentences is "a long step" and can be split. */
export const LONG_STEP = 4;
/** The most sentences one piece holds after a split. */
const PER_PIECE = 2;
/** The server takes up to 100 steps. */
export const MOST_STEPS = 100;

/** Words that end in a full stop without ending the sentence ("tsp.", "approx."). */
const ABBREVIATIONS = new Set(['tsp', 'tbsp', 'approx', 'oz', 'lb', 'lbs', 'vs']);

/** The sentences of a step: split after . ! or ? followed by a space and a capital or a digit,
 *  not after an abbreviation, and not inside a number. */
export function sentences(text: string): string[] {
  const parts: string[] = [];
  let start = 0;
  const pattern = /[.!?]+["')\]]*\s+(?=[A-Z0-9“"(])/g;
  for (const match of text.matchAll(pattern)) {
    const end = match.index + match[0].length;
    const before = text.slice(start, match.index);
    const word = /([A-Za-z.]+)$/.exec(before)?.[1]?.toLowerCase().replace(/\.$/, '');
    if (match[0].startsWith('.') && word && (ABBREVIATIONS.has(word) || word.includes('.'))) {
      continue;
    }
    parts.push(text.slice(start, end).trim());
    start = end;
  }
  const rest = text.slice(start).trim();
  if (rest) parts.push(rest);
  return parts;
}

/** The step as shorter steps (two sentences each at most), or null when it isn't a long step. */
export function splitStep(text: string): string[] | null {
  const all = sentences(text);
  if (all.length < LONG_STEP) return null;
  const pieces: string[] = [];
  for (let i = 0; i < all.length; i += PER_PIECE)
    pieces.push(all.slice(i, i + PER_PIECE).join(' '));
  return pieces.length > 1 ? pieces : null;
}

/** How many sentences a step has, for "A long step (5 sentences)". */
export function sentenceCount(text: string): number {
  return sentences(text).length;
}

/** The method in runs, as the recipe page shows it: a heading, then the steps under it. `start` is
 *  the number of the run's first step, counted through the whole method, so a heading takes no
 *  number (F112). `at` is the item's place in the full list, which the split buttons refer to. */
export type StepRun = {
  heading: { text: string; at: number } | null;
  start: number;
  steps: { text: string; at: number }[];
};

export function stepRuns(steps: { kind: 'step' | 'heading'; text: string }[]): StepRun[] {
  const runs: StepRun[] = [];
  let counted = 0;
  steps.forEach((step, at) => {
    if (step.kind === 'heading') {
      runs.push({ heading: { text: step.text, at }, start: counted + 1, steps: [] });
      return;
    }
    let run = runs.at(-1);
    if (!run) {
      run = { heading: null, start: counted + 1, steps: [] };
      runs.push(run);
    }
    run.steps.push({ text: step.text, at });
    counted++;
  });
  return runs;
}

/** The number the step at `at` shows (counted through the whole method, headings taking none),
 *  or null when `at` is a heading or isn't there. */
export function stepNumberAt(
  steps: { kind: 'step' | 'heading'; text: string }[],
  at: number
): number | null {
  if (steps[at]?.kind !== 'step') return null;
  return steps.slice(0, at + 1).filter((s) => s.kind === 'step').length;
}
