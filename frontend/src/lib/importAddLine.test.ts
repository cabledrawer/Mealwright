import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ImportReview, ReviewLine } from '#lib/client/imports.js';
import { network } from '#lib/network.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { addLineWords, ImportFlow, isBlank } from './import.svelte';

// "Add a line" at the end of each section on Check (F187, cabledrawer 8 Nov).

const line = (over: Partial<ReviewLine>): ReviewLine => ({
  kind: 'ingredient',
  written: '1 cup urad dal',
  words: 'urad dal',
  amount: 1,
  amount_text: '1',
  unit: 'cup',
  size: null,
  note: null,
  readable: true,
  label: 'matched',
  food: { id: 2, name: 'Urad dal' },
  place: 'Cupboard',
  matched_by: null,
  counts: true,
  new_ingredient: null,
  learn_name: null,
  ...over
});

const heading = (words: string): ReviewLine => ({
  ...line({ words, written: words }),
  kind: 'heading',
  label: null,
  food: null
});

const review = (lines: ReviewLine[]): ImportReview => ({
  source: { kind: 'text', url: null, site: null },
  name: 'Masala dosa',
  description: null,
  author: null,
  time_minutes: null,
  serves: 2,
  makes: null,
  tags: [],
  nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
  photo: { state: 'none', photo: null, message: null },
  lines,
  steps: [],
  counts: { matched: 0, to_confirm: 0, needs_you: 0, staple: 0 },
  lines_cut: false,
  steps_cut: false,
  steps_shortened: 0,
  left_out: []
});

function flowOf(lines: ReviewLine[]): ImportFlow {
  const flow = new ImportFlow();
  flow.review = review(lines);
  return flow;
}

describe('where "Add a line" goes', () => {
  it('is at the end of each section, named for it', () => {
    const flow = flowOf([
      heading('For the batter'),
      line({}),
      line({ words: 'rice' }),
      heading('For the dosa'),
      line({ words: 'ghee' })
    ]);
    expect(flow.sectionEnds).toEqual([
      { at: 3, label: 'Add a line to the batter' },
      { at: 5, label: 'Add a line to the dosa' }
    ]);
  });

  it('is one plain button when there are no headings, and for an empty recipe', () => {
    expect(flowOf([line({}), line({})]).sectionEnds).toEqual([{ at: 2, label: 'Add a line' }]);
    expect(flowOf([]).sectionEnds).toEqual([{ at: 0, label: 'Add a line' }]);
  });

  it('gives the lines before the first heading a section of their own, and an empty section its button', () => {
    const flow = flowOf([line({}), heading('For the topping'), heading('To assemble')]);
    expect(flow.sectionEnds).toEqual([
      { at: 1, label: 'Add a line' },
      { at: 2, label: 'Add a line to the topping' },
      { at: 3, label: 'Add a line to “To assemble”' }
    ]);
  });

  it('words the button', () => {
    expect(addLineWords('For the batter')).toBe('Add a line to the batter');
    expect(addLineWords('To make the Dosa')).toBe('Add a line to the dosa');
    expect(addLineWords('Serving')).toBe('Add a line to “Serving”');
    expect(addLineWords('')).toBe('Add a line');
  });
});

describe('a line added on Check', () => {
  beforeEach(() => network.reset());
  afterEach(() => vi.unstubAllGlobals());

  it('goes at the end of its section and moves the choices of the lines after it', () => {
    const flow = flowOf([
      heading('For the batter'),
      line({}),
      heading('For the dosa'),
      line({ label: 'needs_you', food: null, words: 'ghee' })
    ]);
    flow.newIngredient(3);
    const at = flow.addLine(flow.sectionEnds[0]!.at);
    expect(at).toBe(2);
    expect(flow.review!.lines.map((l) => l.kind)).toEqual([
      'heading',
      'ingredient',
      'ingredient',
      'heading',
      'ingredient'
    ]);
    expect(isBlank(flow.review!.lines[2]!)).toBe(true);
    expect(flow.choices[4]).toMatchObject({ kind: 'new', name: 'Ghee' });
    expect(flow.choices[3]).toBeUndefined();
  });

  it('is not counted, not unlinked and not saved until it has a name', () => {
    const flow = flowOf([line({})]);
    flow.addLine(1);
    expect(flow.counts).toEqual({ matched: 1, to_confirm: 0, needs_you: 0, staple: 0 });
    expect(flow.unlinked).toBe(0);
    expect(flow.unlinkedLines()).toEqual([]);
    expect(flow.body()!.lines).toHaveLength(1);
  });

  it('takes an ingredient with exactly that name, as a read line does', async () => {
    fakeApi({
      'GET /foods': [
        200,
        {
          foods: [
            {
              id: 9,
              name: 'Ghee',
              other_names: [],
              place: { id: 1, name: 'Fridge' },
              staple: false
            }
          ]
        }
      ],
      'GET /recipes': [200, { recipes: [{ id: 4, name: 'Ghee rice' }] }]
    });
    const flow = flowOf([line({})]);
    flow.addLine(1);
    expect(await flow.nameLine(1, '  Ghee ')).toBe(true);
    expect(flow.review!.lines[1]).toMatchObject({
      words: 'Ghee',
      written: '',
      label: 'matched',
      food: { id: 9, name: 'Ghee' },
      place: 'Fridge'
    });
    expect(flow.counts.matched).toBe(2);
    const sent = flow.body()!.lines[1]!;
    expect(sent).toMatchObject({ words: 'Ghee', link: { kind: 'ingredient', food_id: 9 } });
  });

  it('asks the person when a recipe has exactly that name too, so the recipe is offered first (F189)', async () => {
    // cabledrawer's case: a stray plain ingredient and a recipe, both "Dosa batter".
    fakeApi({
      'GET /foods': [
        200,
        { foods: [{ id: 9, name: 'Dosa batter', other_names: [], place: null, staple: false }] }
      ],
      'GET /recipes': [200, { recipes: [{ id: 4, name: 'Dosa Batter' }] }]
    });
    const flow = flowOf([line({})]);
    flow.addLine(1);
    await flow.nameLine(1, 'dosa batter');
    expect(flow.review!.lines[1]).toMatchObject({ label: 'needs_you', food: null });
  });

  it('asks like any other line when no ingredient has that name, and then has the same choices', async () => {
    fakeApi({ 'GET /foods': [200, { foods: [] }] });
    const flow = flowOf([line({})]);
    flow.addLine(1);
    await flow.nameLine(1, 'coconut chutney');
    expect(flow.review!.lines[1]).toMatchObject({ label: 'needs_you', food: null });
    expect(flow.counts.needs_you).toBe(1);
    expect(flow.guessFor(1)).toMatchObject({ name: 'Coconut chutney' });
    flow.newIngredient(1);
    expect(flow.choices[1]).toMatchObject({ kind: 'new', name: 'Coconut chutney' });
    expect(flow.body()!.lines[1]!.link).toMatchObject({ kind: 'new', name: 'Coconut chutney' });
    flow.unchoose(1);
    flow.madeHere(1);
    expect(flow.choices[1]).toEqual({ kind: 'here' });
    expect(flow.body()!.lines[1]!.link).toBeNull();
  });

  it('says no to an empty name', async () => {
    const flow = flowOf([line({})]);
    flow.addLine(1);
    expect(await flow.nameLine(1, '   ')).toBe(false);
    expect(isBlank(flow.review!.lines[1]!)).toBe(true);
  });

  it('is dropped without an Undo when it is given up before it has a name', () => {
    const flow = flowOf([line({}), line({})]);
    flow.newIngredient(0);
    flow.addLine(1);
    flow.dropBlank(1);
    expect(flow.review!.lines).toHaveLength(2);
    expect(flow.choices[0]).toMatchObject({ kind: 'new' });
  });

  it('stops at the most lines a recipe may hold', () => {
    const flow = flowOf(Array.from({ length: 200 }, () => line({})));
    expect(flow.canAddLine).toBe(false);
    expect(flow.addLine(200)).toBe(-1);
    expect(flow.review!.lines).toHaveLength(200);
  });
});

describe('a save refused on a line, with an added line never named before it', () => {
  beforeEach(() => network.reset());
  afterEach(() => vi.unstubAllGlobals());

  it('points at the refused line on the screen, not one before it', async () => {
    const flow = flowOf([
      heading('For the batter'),
      line({}),
      heading('For the dosa'),
      line({ words: 'dosa batter' })
    ]);
    flow.name = 'Masala dosa';
    flow.addLine(flow.sectionEnds[0]!.at); // an empty line at 2; the dosa batter moves to 4
    fakeApi({
      // The server numbers the lines it was sent (headings too): the dosa batter is its line 3.
      'POST /recipes/import/save': [404, { detail: 'That recipe has gone.', line: 3 }]
    });
    expect(await flow.save()).toBeNull();
    expect(flow.saveProblem).toEqual({ message: 'That recipe has gone.', line: 4 });
  });
});
