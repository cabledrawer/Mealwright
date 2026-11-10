import { describe, expect, it } from 'vitest';
import type { RecipeLine } from './client/recipes';
import { clock, cookSteps, findTimers, nameForms, stepLines, type StepIn } from './cookSteps';

const step = (text: string, extra: Partial<StepIn> = {}): StepIn => ({
  kind: 'step',
  text,
  ...extra
});
const heading = (text: string): StepIn => ({ kind: 'heading', text });

describe('the step list', () => {
  it('numbers the steps and counts them', () => {
    const steps = cookSteps([step('Soak.'), step('Boil.'), step('Eat.')]);
    expect(steps.map((s) => [s.number, s.total])).toEqual([
      [1, 3],
      [2, 3],
      [3, 3]
    ]);
    expect(steps.every((s) => s.section === null)).toBe(true);
  });

  it('shows a heading as the title of the steps under it and never counts it', () => {
    const steps = cookSteps([
      heading('The dal'),
      step('Boil the dal.'),
      step('Mash it.'),
      heading('The tadka'),
      step('Fry the seeds.')
    ]);
    expect(steps.map((s) => [s.number, s.total, s.section])).toEqual([
      [1, 3, 'The dal'],
      [2, 3, 'The dal'],
      [3, 3, 'The tadka']
    ]);
  });

  it('keeps every step of a recipe with two method sections, in order, each under its own title', () => {
    const steps = cookSteps([
      heading('Method 1: stove'),
      step('Simmer.'),
      step('Serve.'),
      heading('Method 2: pressure cooker'),
      step('Cook for 3 whistles.'),
      step('Serve.')
    ]);
    expect(steps.map((s) => s.text)).toEqual([
      'Simmer.',
      'Serve.',
      'Cook for 3 whistles.',
      'Serve.'
    ]);
    expect(steps.map((s) => s.section)).toEqual([
      'Method 1: stove',
      'Method 1: stove',
      'Method 2: pressure cooker',
      'Method 2: pressure cooker'
    ]);
    expect(steps.at(-1)?.number).toBe(4);
    expect(steps[0]?.total).toBe(4);
  });

  it('shows nothing for a heading with no step under it, and uses the latest of two in a row', () => {
    expect(cookSteps([heading('Only a heading')])).toEqual([]);
    const steps = cookSteps([
      step('One.'),
      heading('Empty'),
      heading('Real'),
      step('Two.'),
      heading('Last')
    ]);
    expect(steps.map((s) => [s.text, s.section])).toEqual([
      ['One.', null],
      ['Two.', 'Real']
    ]);
  });

  it('has no steps for no method, and skips steps with only spaces', () => {
    expect(cookSteps([])).toEqual([]);
    expect(cookSteps([step('   '), step('Stir.')]).map((s) => s.text)).toEqual(['Stir.']);
  });

  it('gives one step for a one-step recipe, and keeps a very long step whole', () => {
    expect(cookSteps([step('Just stir.')])).toHaveLength(1);
    const long = 'Stir. '.repeat(800).trim();
    expect(cookSteps([step(long)])[0]?.text).toBe(long);
  });

  it('carries the links the server holds', () => {
    const steps = cookSteps([
      step('Stir.', { id: 1, lines: [{ line_id: 9, line: 0, kind: 'by_hand' }] })
    ]);
    expect(steps[0]?.linked).toEqual([9]);
  });
});

describe('timers in a step’s words', () => {
  const found = (text: string) => findTimers(text).map((t) => [t.words, t.seconds]);

  it('finds minutes, hours and seconds', () => {
    expect(found('Simmer for 10 minutes.')).toEqual([['10 minutes', 600]]);
    expect(found('Rest 5 min')).toEqual([['5 min', 300]]);
    expect(found('Bake 1 h.')).toEqual([['1 h', 3600]]);
    expect(found('Cook for 2 hours')).toEqual([['2 hours', 7200]]);
    expect(found('Toast for 30 seconds')).toEqual([['30 seconds', 30]]);
    expect(found('Leave 1 hr')).toEqual([['1 hr', 3600]]);
  });

  it('reads fractions and decimals', () => {
    expect(found('Simmer 1½ hours')).toEqual([['1½ hours', 5400]]);
    expect(found('Simmer 1 1/2 hours')).toEqual([['1 1/2 hours', 5400]]);
    expect(found('Simmer ½ hour')).toEqual([['½ hour', 1800]]);
    expect(found('Simmer 1.5 hours')).toEqual([['1.5 hours', 5400]]);
  });

  it('starts a range at its shorter end', () => {
    expect(found('Bake 10-15 minutes')).toEqual([['10-15 minutes', 600]]);
    expect(found('Bake 10 to 15 minutes')).toEqual([['10 to 15 minutes', 600]]);
    expect(found('Bake 10–15 minutes')).toEqual([['10–15 minutes', 600]]);
  });

  it('makes one timer of an hour and minutes together', () => {
    expect(found('Roast 1 hour 30 minutes.')).toEqual([['1 hour 30 minutes', 5400]]);
    expect(found('Roast 1 hour and 15 minutes.')).toEqual([['1 hour and 15 minutes', 4500]]);
    expect(found('Roast 1 h 30 min')).toEqual([['1 h 30 min', 5400]]);
  });

  it('finds several timers in one step, in order', () => {
    expect(found('Fry 2 minutes, then simmer 20 minutes.')).toEqual([
      ['2 minutes', 120],
      ['20 minutes', 1200]
    ]);
  });

  it('does not mistake other numbers for times', () => {
    expect(found('Add 2 tbsp of oil and 300 g of dal at 180 degrees.')).toEqual([]);
    expect(found('Add 3 hot peppers and 2 shallots.')).toEqual([]);
    expect(found('Make 4 servings. Use a 20 cm pan.')).toEqual([]);
    expect(found('Use 5 matches')).toEqual([]);
    expect(found('Cook for 0 minutes')).toEqual([]);
  });

  it('ignores a time longer than a day', () => {
    expect(found('Wait 48 hours')).toEqual([]);
    expect(found('Wait 24 hours')).toEqual([['24 hours', 86400]]);
  });

  it('shows the time as a clock', () => {
    expect(clock(600)).toBe('10:00');
    expect(clock(65)).toBe('01:05');
    expect(clock(5400)).toBe('1:30:00');
    expect(clock(0.2)).toBe('00:01');
    expect(clock(-3)).toBe('00:00');
  });
});

const line = (
  id: number,
  name: string,
  other: string[] = [],
  extra: Partial<RecipeLine> = {}
): RecipeLine => ({
  id,
  kind: 'ingredient',
  words: name,
  amount: null,
  amount_text: null,
  unit: null,
  size: null,
  food: { id: id + 100, name, other_names: other },
  recipe: null,
  link: 'ingredient',
  note: null,
  ...extra
});

describe('the ingredients a step seems to use', () => {
  const lines = [
    line(1, 'Onion'),
    line(2, 'Toor dal', ['thuvaram paruppu']),
    line(3, 'Tamarind'),
    line(4, 'Chickpeas'),
    { ...line(5, 'x'), kind: 'heading' as const, food: null, link: null, words: 'For the tadka' }
  ];
  const guess = (text: string) =>
    stepLines({ number: 1, total: 1, section: null, text, linked: [] }, lines).map((l) => l.id);

  it('guesses from the name, its plural and its other names', () => {
    expect(guess('Chop the onions finely.')).toEqual([1]);
    expect(guess('Chop one onion.')).toEqual([1]);
    expect(guess('Boil the thuvaram paruppu until soft.')).toEqual([2]);
    expect(guess('Soak the tamarind, then drain the chickpeas.')).toEqual([3, 4]);
    expect(guess('Boil the chickpea.')).toEqual([4]);
  });

  it('matches whole words only, in any case', () => {
    expect(guess('Add the ONION.')).toEqual([1]);
    expect(guess('Add a onionskin.')).toEqual([]);
    expect(guess('Stir well.')).toEqual([]);
  });

  it('never offers a heading', () => {
    expect(guess('For the tadka, fry.')).toEqual([]);
  });

  it('uses the server’s links when there are some', () => {
    const linked = stepLines(
      { number: 1, total: 1, section: null, text: 'Stir.', linked: [3] },
      lines
    );
    expect(linked.map((l) => l.id)).toEqual([3]);
  });

  it('knows the plural of a name', () => {
    expect(nameForms('Onion')).toEqual(['onion', 'onions']);
    expect(nameForms('Berry')).toContain('berries');
    expect(nameForms('Tomato')).toContain('tomatoes');
    expect(nameForms('')).toEqual([]);
  });
});

describe('the wait on a step, for the NEXT line (M2)', () => {
  it('carries a step’s wait and leaves the others without one', () => {
    const wait = { kind: 'marinate', min_minutes: 240, max_minutes: 720, overnight: true };
    const found = cookSteps([
      { kind: 'step', text: 'Rub the chicken.', wait },
      { kind: 'step', text: 'Fry the onions.' }
    ]);
    expect(found[0]?.wait).toEqual(wait);
    expect(found[1]?.wait).toBeUndefined();
  });
});
