import { beforeEach, describe, expect, it } from 'vitest';
import type { ImportReview, ReviewLine, ReviewStep } from '#lib/client/imports.js';
import { network } from '#lib/network.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import { undoHistory } from '#lib/undo.svelte.js';
import { ImportFlow } from './import.svelte';
import { keepInMain, makeOwn } from './importOwnEdits';
import { otherSectionCalled, ownDefaults, ownLineWords, sectionOf } from './importOwn';

// A section as its own recipe on Check (F190, cabledrawer 8 Nov): the pure work, what Save sends, and
// what a draft keeps.

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

const step = (text: string): ReviewStep => ({ kind: 'step', text });
const stepHeading = (text: string): ReviewStep => ({ kind: 'heading', text });

/** Masala dosa: the batter (two lines, two steps), then the dosa, which says "Dosa batter, as above". */
function dosa(): ImportFlow {
  const flow = new ImportFlow();
  const review: ImportReview = {
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
    lines: [
      heading('For the batter'),
      line({}),
      line({
        words: 'idli rice',
        written: '3 cups idli rice',
        amount: 3,
        food: { id: 3, name: 'Idli rice' }
      }),
      heading('For the dosa'),
      line({
        written: '4 cups dosa batter, as above',
        words: 'dosa batter',
        amount: 4,
        label: 'needs_you',
        food: null,
        note: 'as above'
      }),
      line({
        words: 'ghee',
        written: 'ghee',
        amount: null,
        unit: null,
        food: { id: 4, name: 'Ghee' }
      })
    ],
    steps: [
      stepHeading('For the batter'),
      step('Soak the dal.'),
      step('Grind and ferment.'),
      stepHeading('For the dosa'),
      step('Spread and fry.')
    ],
    counts: { matched: 0, to_confirm: 0, needs_you: 0, staple: 0 },
    lines_cut: false,
    steps_cut: false,
    steps_shortened: 0,
    left_out: []
  };
  flow.review = review;
  flow.name = 'Masala dosa';
  return flow;
}

describe('the section under a heading', () => {
  it('finds the method’s heading when it ends in a colon, as a page writes it', () => {
    const flow = dosa();
    flow.review!.steps[0]!.text = 'For the batter:';
    flow.review!.steps[3]!.text = 'FOR THE DOSA:';
    expect(sectionOf(flow.review!, 0).steps).toEqual([1, 2]);
  });

  it('is its lines, its steps under the same heading in the method, and the line that names it', () => {
    const flow = dosa();
    expect(sectionOf(flow.review!, 0)).toEqual({
      lines: [1, 2],
      stepHeading: 0,
      steps: [1, 2],
      use: 4
    });
    expect(sectionOf(flow.review!, 3)).toMatchObject({ lines: [4, 5], steps: [4], use: null });
  });

  it('starts the sheet with the name and amount a line that names it says', () => {
    expect(ownDefaults(dosa().review!, 0)).toEqual({
      name: 'Dosa batter',
      amount: '4',
      unit: 'cup'
    });
  });

  it('starts with the heading’s own words when nothing names it, and takes no steps when the method has no such heading', () => {
    const flow = dosa();
    flow.review!.lines.splice(4, 1);
    flow.review!.steps.splice(0, 1);
    expect(ownDefaults(flow.review!, 0)).toEqual({ name: 'Batter', amount: '', unit: 'cup' });
    expect(sectionOf(flow.review!, 0).steps).toEqual([]);
  });

  it('is worded as the one line the main recipe gets', () => {
    expect(ownLineWords({ name: 'Dosa batter', amount: 4, unit: 'cup' })).toBe(
      'Dosa batter · 4 cups'
    );
  });
});

describe('Save with a section made its own recipe', () => {
  beforeEach(() => {
    network.reset();
    undoHistory.clear();
  });

  it('sends the section as its own recipe and the main recipe without it', () => {
    const flow = dosa();
    expect(makeOwn(flow, 0, { name: 'Dosa batter', amount: 4, unit: 'cup' })).toBe(true);
    const body = flow.body()!;
    expect(body.own_recipes).toEqual([
      {
        name: 'Dosa batter',
        makes: { amount: 4, unit: 'cup' },
        lines: [
          expect.objectContaining({
            words: 'urad dal',
            link: { kind: 'ingredient', food_id: 2, learn: null }
          }),
          expect.objectContaining({ words: 'idli rice' })
        ],
        steps: [
          { kind: 'step', text: 'Soak the dal.', optional: undefined, wait: undefined },
          { kind: 'step', text: 'Grind and ferment.', optional: undefined, wait: undefined }
        ]
      }
    ]);
    // The main recipe: the dosa heading, "Dosa batter, as above" as the link to the new recipe (its
    // own amount kept), and the ghee. The batter's heading, lines and steps are gone from it.
    expect(body.lines.map((l) => [l.kind, l.words])).toEqual([
      ['heading', 'For the dosa'],
      ['ingredient', 'Dosa batter'],
      ['ingredient', 'ghee']
    ]);
    expect(body.lines[1]).toMatchObject({
      words: 'Dosa batter',
      amount: 4,
      unit: 'cup',
      link: { kind: 'own_recipe', own_recipe: 0 }
    });
    expect(body.steps.map((s) => s.text)).toEqual(['For the dosa', 'Spread and fry.']);
  });

  it('puts one line in the heading’s place when no line already names the recipe', () => {
    const flow = dosa();
    flow.review!.lines.splice(4, 1);
    makeOwn(flow, 0, { name: 'Batter', amount: 1.5, unit: 'l' });
    const body = flow.body()!;
    expect(body.lines.map((l) => l.words)).toEqual(['Batter', 'For the dosa', 'ghee']);
    expect(body.lines[0]).toMatchObject({
      amount: 1.5,
      unit: 'l',
      link: { kind: 'own_recipe', own_recipe: 0 }
    });
  });

  it('counts the section’s lines and the line that stands for it as ready, so Save does not ask about them', () => {
    const flow = dosa();
    expect(flow.unlinkedLines()).toEqual([4]);
    makeOwn(flow, 0, { name: 'Dosa batter', amount: 4, unit: 'cup' });
    expect(flow.unlinkedLines()).toEqual([]);
    expect(flow.counts).toMatchObject({ needs_you: 0, matched: 4 });
  });

  it('sends nothing extra when no section was made its own recipe', () => {
    const flow = dosa();
    const body = flow.body()!;
    expect(body.own_recipes).toBeUndefined();
    expect(body.lines).toHaveLength(6);
    expect(body.steps).toHaveLength(5);
  });

  it('maps a refusal’s line numbers back to the review’s own places', async () => {
    const flow = dosa();
    makeOwn(flow, 0, { name: 'Dosa batter', amount: 4, unit: 'cup' });
    // The section's second line is the server's line 1 of its own recipe, and the review's line 2.
    fakeApi({
      'POST /recipes/import/save': [
        422,
        { code: 'invalid_recipe', detail: 'Pick an ingredient.', line: 1, own_recipe: 0 }
      ]
    });
    expect(await flow.save()).toBeNull();
    expect(flow.saveProblem).toEqual({ message: 'Pick an ingredient.', line: 2 });
    // A line of the main recipe: the server counts what it was sent ("ghee" is its third line).
    fakeApi({
      'POST /recipes/import/save': [
        422,
        { code: 'invalid_recipe', detail: 'Pick an ingredient.', line: 2 }
      ]
    });
    await flow.save();
    expect(flow.saveProblem).toEqual({ message: 'Pick an ingredient.', line: 5 });
  });
});

describe('making it, changing it and keeping it in', () => {
  it('lives on the heading, so a draft keeps it', () => {
    const flow = dosa();
    makeOwn(flow, 0, { name: 'Dosa batter', amount: 4, unit: 'cup' });
    expect(flow.review!.lines[0]!.own).toEqual({ name: 'Dosa batter', amount: 4, unit: 'cup' });
    expect(flow.draftBody()!.review.lines[0]!.own).toMatchObject({ name: 'Dosa batter' });
  });

  it('can be kept in the recipe again, and each has an Undo', async () => {
    const flow = dosa();
    makeOwn(flow, 0, { name: 'Dosa batter', amount: 4, unit: 'cup' });
    expect(keepInMain(flow, 0)).toBe(true);
    expect(flow.review!.lines[0]!.own).toBeNull();
    expect(flow.body()!.own_recipes).toBeUndefined();
    await undoHistory.undoLast();
    expect(flow.review!.lines[0]!.own).toMatchObject({ name: 'Dosa batter' });
  });

  it('does nothing on a line that is not a heading, or a heading that is not its own recipe', () => {
    const flow = dosa();
    expect(makeOwn(flow, 1, { name: 'x', amount: 1, unit: 'l' })).toBe(false);
    expect(keepInMain(flow, 0)).toBe(false);
  });
});

describe('a stand-in line that already had a choice', () => {
  const newBatter = {
    kind: 'new',
    name: 'Dosa batter',
    counted_as: 'volume',
    place_id: 1
  } as const;

  it('shows and sends the own recipe, not the old choice, and Keep or Undo gives the choice back', async () => {
    const flow = dosa();
    flow.choose(4, { ...newBatter });
    makeOwn(flow, 0, { name: 'Dosa batter', amount: 4, unit: 'cup' });
    // Screen, counts and Save agree: the line is the new recipe, its old choice set aside.
    expect(flow.choices[4]).toBeUndefined();
    expect(flow.linkOf(4)).toMatchObject({ kind: 'recipe' });
    expect(flow.body()!.lines[1]).toMatchObject({ link: { kind: 'own_recipe', own_recipe: 0 } });
    expect(flow.counts).toMatchObject({ matched: 4, needs_you: 0 });
    // Keep in this recipe: the choice is back, exactly.
    expect(keepInMain(flow, 0)).toBe(true);
    expect(flow.choices[4]).toEqual(newBatter);
    // Undo of Keep: set aside again; Undo of that: back to the start.
    await undoHistory.undoLast();
    expect(flow.choices[4]).toBeUndefined();
    await undoHistory.undoLast();
    expect(flow.review!.lines[0]!.own).toBeNull();
    expect(flow.choices[4]).toEqual(newBatter);
  });
});

describe('a stand-in line inside another section made its own recipe', () => {
  it('is never picked: the heading’s place gets a line instead', () => {
    const flow = dosa();
    // "Dosa batter" listed under the batter's own heading too (a second candidate), and the
    // dosa section made its own recipe first.
    const lines = flow.review!.lines;
    lines.splice(3, 0, line({ words: 'dosa batter', written: 'dosa batter', amount: 1 }));
    makeOwn(flow, 4, { name: 'Dosa', amount: 1, unit: 'cup' });
    // The batter section (heading 0) is made own: its only "dosa batter" candidate (line 3)... is in
    // the batter section itself (inside), and the one at 6 is inside the dosa section (own).
    makeOwn(flow, 0, { name: 'Dosa batter', amount: 4, unit: 'cup' });
    expect(sectionOf(flow.review!, 0, 'Dosa batter').use).toBeNull();
    expect(flow.ownUseOf(6)).toBeNull();
    const body = flow.body()!;
    expect(body.own_recipes).toHaveLength(2);
    // Every line that links to a section recipe is a line the server can match to its save.
    const links = body.lines.filter((l) => l.link?.kind === 'own_recipe');
    expect(links.map((l) => (l.link as { own_recipe: number }).own_recipe).sort()).toEqual([0, 1]);
  });
});

describe('two sections with one name (RF4 I13)', () => {
  it('finds another section already making a recipe of that name, in any case and spacing', () => {
    const flow = dosa();
    const review = flow.review!;
    const heading0 = review.lines.findIndex((l) => l.kind === 'heading');
    makeOwn(flow, heading0, { name: 'Dosa batter', amount: 4, unit: 'cup' });
    review.lines.push(heading('For the chutney'));
    const chutney = review.lines.length - 1;
    expect(otherSectionCalled(review, chutney, ' dosa   BATTER ')).toBe(heading0);
    expect(otherSectionCalled(review, chutney, 'Coconut chutney')).toBeNull();
    // the section's own name is not "another section"
    expect(otherSectionCalled(review, heading0, 'Dosa batter')).toBeNull();
  });
});
