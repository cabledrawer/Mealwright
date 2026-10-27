// For the gallery and tests only: a review as the server would answer it, with a line in each
// state (matched, staple, to confirm, needs you, unreadable, a very long name), and the flows
// the import screens show in each of their states.

import type { ImportReview, ReviewLine } from '#lib/client/imports.js';
import { ImportFlow } from '#lib/import.svelte.js';

const base: ReviewLine = {
  kind: 'ingredient',
  written: '',
  words: '',
  amount: null,
  amount_text: null,
  unit: null,
  size: null,
  note: null,
  readable: true,
  label: 'matched',
  food: null,
  place: null,
  matched_by: null,
  counts: true,
  new_ingredient: null,
  learn_name: null
};

const guess = (name: string, counted_as: 'weight' | 'volume' | 'count') => ({
  name,
  counted_as,
  place: { id: 3, name: 'Cupboard' }
});

export const SAMPLE_LINES: ReviewLine[] = [
  { ...base, kind: 'heading', label: null, written: 'For the sambar:', words: 'For the sambar' },
  {
    ...base,
    written: '1 cup (200 g) thuvaram paruppu',
    words: 'thuvaram paruppu',
    amount: 200,
    amount_text: '200',
    unit: 'g',
    note: 'as written: 1 cup (200 g) thuvaram paruppu',
    food: { id: 1, name: 'Toor dal' },
    place: 'Cupboard',
    matched_by: 'thuvaram paruppu',
    new_ingredient: guess('Thuvaram paruppu', 'weight'),
    learn_name: 'thuvaram paruppu'
  },
  {
    ...base,
    written: '2–3 green chillies, slit',
    words: 'green chillies',
    amount: 3,
    amount_text: '3',
    note: 'as written: 2-3 green chillies, slit',
    food: { id: 4, name: 'Green chillies' },
    place: 'Fridge',
    new_ingredient: guess('Green chillies', 'count'),
    learn_name: 'green chillies'
  },
  {
    ...base,
    written: '1 red onion, sliced',
    words: 'red onion',
    amount: 1,
    amount_text: '1',
    note: 'sliced',
    label: 'to_confirm',
    food: { id: 2, name: 'Onions' },
    new_ingredient: guess('Red onion', 'count'),
    learn_name: 'red onion'
  },
  {
    ...base,
    written: '¼ tsp asafoetida',
    words: 'asafoetida',
    amount: 0.25,
    amount_text: '¼',
    unit: 'tsp',
    label: 'needs_you',
    new_ingredient: guess('Asafoetida', 'volume'),
    learn_name: 'asafoetida'
  },
  {
    ...base,
    written: '(a line with nothing readable in it) ???',
    words: '(a line with nothing readable in it) ???',
    readable: false,
    label: 'needs_you',
    counts: false,
    new_ingredient: guess('(a line with nothing readable in it) ???', 'weight'),
    learn_name: null
  },
  {
    ...base,
    written: 'salt to taste',
    words: 'salt',
    note: 'to taste',
    label: 'staple',
    food: { id: 5, name: 'Salt' },
    counts: false,
    new_ingredient: guess('Salt', 'weight')
  },
  {
    ...base,
    written:
      '250 g வெண்டைக்காய் (வெண்டைக்காய் / भिंडी, okra), cut into rounds, washed and dried well on a clean towel',
    words: 'வெண்டைக்காய் (வெண்டைக்காய் / भिंडी, okra) cut into rounds, washed and dried well',
    amount: 250,
    amount_text: '250',
    unit: 'g',
    label: 'needs_you',
    new_ingredient: guess('வெண்டைக்காய் (வெண்டைக்காய் / भिंडी, okra)', 'weight'),
    learn_name: 'வெண்டைக்காய்'
  }
];

export const SAMPLE_REVIEW: ImportReview = {
  source: { kind: 'link', url: 'https://kitchen.example/sambar', site: 'kitchen.example' },
  name: 'Sambar',
  description: 'Lentil & vegetable stew',
  author: 'Meena Raman',
  time_minutes: 50,
  serves: 4,
  makes: null,
  tags: ['Dinner', 'South Indian'],
  nutrition: { kcal: 320, protein: 16, carbs: null, fat: null, fibre: null },
  photo: { state: 'off', photo: null, message: 'Photo not downloaded' },
  lines: SAMPLE_LINES,
  steps: [
    { kind: 'heading', text: 'The tempering' },
    { kind: 'step', text: 'Boil the dal until soft.' },
    { kind: 'step', text: 'Add the vegetables and simmer.' }
  ],
  counts: { matched: 2, to_confirm: 1, needs_you: 3, staple: 1 },
  lines_cut: false,
  steps_cut: false,
  steps_shortened: 0,
  left_out: [{ heading: 'Tips', lines: 4 }]
};

/** A US recipe site read for a UK household (mockup ImportPints-*): its pints are read as US
 *  pints, and the card offers the switch back. */
export const PINTS_REVIEW: ImportReview = {
  ...SAMPLE_REVIEW,
  source: { kind: 'link', url: 'https://www.allrecipes.com/recipe/1/x/', site: 'allrecipes.com' },
  name: 'Creamy rice pudding',
  description: null,
  author: null,
  time_minutes: null,
  serves: null,
  tags: [],
  nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
  lines: [
    {
      ...base,
      written: '2 pints whole milk',
      words: 'whole milk',
      amount: 946,
      amount_text: '946',
      unit: 'ml',
      note: 'as written: 2 pints whole milk',
      food: { id: 7, name: 'Whole milk' },
      place: 'Fridge',
      matched_by: 'whole milk',
      new_ingredient: guess('Whole milk', 'volume'),
      learn_name: 'whole milk',
      pint_ml: { uk_ml: 1136, us_ml: 946 }
    },
    {
      ...base,
      written: '1 tsp vanilla extract',
      words: 'vanilla extract',
      amount: 1,
      amount_text: '1',
      unit: 'tsp',
      food: { id: 8, name: 'Vanilla extract' },
      place: 'Cupboard',
      new_ingredient: guess('Vanilla extract', 'volume'),
      learn_name: 'vanilla extract'
    }
  ],
  counts: { matched: 2, to_confirm: 0, needs_you: 0, staple: 0 },
  left_out: [],
  pints: { household: 'uk', us_site: true, reading: 'us' }
};

/** A flow showing the review (the places for "New ingredient" come from the page). */
export function reviewFlow(over: Partial<ImportReview> = {}): ImportFlow {
  const flow = new ImportFlow();
  flow.text = 'https://kitchen.example/sambar';
  flow.review = { ...SAMPLE_REVIEW, ...over };
  flow.pints = flow.review.pints?.reading ?? 'uk';
  flow.name = flow.review.name;
  flow.serves = String(flow.review.serves ?? '');
  flow.minutes = String(flow.review.time_minutes ?? '');
  flow.phase = 'review';
  return flow;
}

export function boxFlow(
  text: string,
  problem: ImportFlow['problem'] = null,
  phase: ImportFlow['phase'] = 'start'
): ImportFlow {
  const flow = new ImportFlow();
  flow.text = text;
  flow.problem = problem;
  flow.phase = phase;
  return flow;
}
