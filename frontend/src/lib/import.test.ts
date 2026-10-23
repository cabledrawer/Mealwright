import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ImportReview, ReviewLine } from '$lib/client/imports';
import { network } from '$lib/network.svelte';
import { fakeApi } from '$lib/testing/fakeApi';
import { ImportFlow, leftOutWords } from './import.svelte';

const line = (over: Partial<ReviewLine>): ReviewLine => ({
  kind: 'ingredient',
  written: '1 onion',
  words: 'onion',
  amount: 1,
  amount_text: '1',
  unit: null,
  size: null,
  note: null,
  readable: true,
  label: 'matched',
  food: { id: 2, name: 'Onions' },
  place: 'Cupboard',
  matched_by: null,
  counts: true,
  new_ingredient: { name: 'Onion', counted_as: 'count', place: { id: 3, name: 'Cupboard' } },
  learn_name: 'onion',
  ...over
});

const REVIEW: ImportReview = {
  source: { kind: 'link', url: 'https://kitchen.example/dal', site: 'kitchen.example' },
  name: 'Sambar',
  description: null,
  author: 'A cook',
  time_minutes: 50,
  serves: 4,
  makes: null,
  tags: ['Dinner'],
  nutrition: { kcal: 320, protein: null, carbs: null, fat: null, fibre: null },
  photo: { state: 'off', photo: null, message: 'Photo not downloaded' },
  lines: [
    line({}),
    line({
      written: '1 red onion, sliced',
      words: 'red onion',
      label: 'to_confirm',
      learn_name: 'red onion'
    }),
    line({
      written: '¼ tsp asafoetida',
      words: 'asafoetida',
      label: 'needs_you',
      food: null,
      place: null,
      learn_name: 'asafoetida',
      new_ingredient: { name: 'Asafoetida', counted_as: 'volume', place: null }
    }),
    { ...line({ words: 'For the tadka' }), kind: 'heading', label: null, food: null }
  ],
  steps: [{ kind: 'step', text: 'Boil.' }],
  counts: { matched: 1, to_confirm: 1, needs_you: 1, staple: 0 },
  lines_cut: false,
  steps_cut: false,
  steps_shortened: 0,
  left_out: []
};

describe('the import flow', () => {
  beforeEach(() => network.reset());
  afterEach(() => vi.unstubAllGlobals());

  it('tells a link from pasted text', () => {
    const flow = new ImportFlow();
    for (const [text, link] of [
      ['https://bbcgoodfood.com/recipes/x', true],
      ['www.example.com/sambar', true],
      ['ftp://example.test/x', true],
      ['Sambar\n1 onion', false],
      ['Sambar', false],
      ['2 onions and a link https://x.example', false]
    ] as const) {
      flow.text = text;
      expect(flow.isLink, text).toBe(link);
    }
  });

  it('asks the server and shows the review; nothing is saved', async () => {
    const requests = fakeApi({ 'POST /recipes/import': [200, REVIEW] });
    const flow = new ImportFlow();
    flow.text = '  https://kitchen.example/dal  ';
    await flow.read();
    expect(flow.phase).toBe('review');
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['POST /recipes/import']);
    expect(requests[0]!.body).toEqual({ text: 'https://kitchen.example/dal', again: false });
    expect(flow.name).toBe('Sambar');
    expect(flow.serves).toBe('4');
    expect(flow.minutes).toBe('50');
  });

  it('does nothing for an empty box', async () => {
    const requests = fakeApi({});
    const flow = new ImportFlow();
    await flow.read();
    expect(flow.phase).toBe('start');
    expect(flow.problem?.message).toBe('Paste a link or the recipe’s text.');
    expect(requests).toHaveLength(0);
  });

  it('keeps the sentence and what to offer when the switch is off', async () => {
    fakeApi({
      'POST /recipes/import': [
        403,
        { detail: 'Importing from links is switched off', code: 'import_switched_off', admin: true }
      ]
    });
    const flow = new ImportFlow();
    flow.text = 'https://kitchen.example/dal';
    await flow.read();
    expect(flow.phase).toBe('start');
    expect(flow.problem).toMatchObject({
      message: 'Importing from links is switched off',
      switchedOff: true,
      admin: true
    });
    expect(flow.text).toBe('https://kitchen.example/dal'); // what was typed stays
  });

  it('shows the server’s sentence for any other refusal', async () => {
    fakeApi({
      'POST /recipes/import': [422, { detail: 'This link isn’t a web page.', code: 'not_a_page' }]
    });
    const flow = new ImportFlow();
    flow.text = 'https://kitchen.example/x.pdf';
    await flow.read();
    expect(flow.problem).toMatchObject({
      code: 'not_a_page',
      message: 'This link isn’t a web page.'
    });
  });

  it('says it needs the server when there is no connection, and queues nothing', async () => {
    vi.stubGlobal('fetch', () => Promise.reject(new TypeError('offline')));
    const flow = new ImportFlow();
    flow.text = 'https://kitchen.example/dal';
    await flow.read();
    expect(flow.phase).toBe('start');
    expect(flow.problem?.code).toBe('offline');
    expect(flow.problem?.message).toContain('needs your Mealwright server');
  });

  it('offers Open it and Import again as a copy for the same link', async () => {
    const requests = fakeApi({
      'POST /recipes/import': (r) =>
        (r.body as { again: boolean }).again
          ? [200, REVIEW]
          : [
              409,
              {
                detail: 'You already have this recipe',
                code: 'already_imported',
                recipe: { id: 9, name: 'Sambar' },
                site: 'kitchen.example',
                imported_at: '2026-10-03T10:00:00Z',
                photo: null
              }
            ]
    });
    const flow = new ImportFlow();
    flow.text = 'https://kitchen.example/dal';
    await flow.read();
    expect(flow.already?.recipe).toEqual({ id: 9, name: 'Sambar' });
    expect(flow.phase).toBe('start');
    await flow.read(true);
    expect(flow.already).toBeNull();
    expect(flow.phase).toBe('review');
    expect(requests.at(-1)!.body).toEqual({ text: 'https://kitchen.example/dal', again: true });
  });

  describe('the review', () => {
    async function reviewing() {
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      fakeApi({ 'POST /recipes/import': [200, REVIEW] });
      await flow.read();
      return flow;
    }

    it('links matched lines by themselves and counts the rest as unlinked', async () => {
      const flow = await reviewing();
      expect(flow.linkOf(0)).toMatchObject({ kind: 'food', learn: false });
      expect(flow.linkOf(1)).toBeNull();
      expect(flow.unlinked).toBe(2);
    });

    it('same as: ties the line to the ingredient and learns the name', async () => {
      const flow = await reviewing();
      flow.sameAs(1, { id: 2, name: 'Onions' });
      expect(flow.unlinked).toBe(1);
      expect(flow.body()!.lines[1]!.link).toEqual({
        kind: 'food',
        food_id: 2,
        learn: 'red onion'
      });
      flow.choose(1, null); // Change
      expect(flow.body()!.lines[1]!.link).toBeNull();
    });

    it('new ingredient and treat as staple start from the first guess', async () => {
      const flow = await reviewing();
      flow.newIngredient(2);
      expect(flow.body()!.lines[2]!.link).toEqual({
        kind: 'new',
        name: 'Asafoetida',
        counted_as: 'volume',
        place_id: null
      });
      flow.newIngredient(2, true);
      expect(flow.body()!.lines[2]!.link).toMatchObject({ kind: 'staple', name: 'Asafoetida' });
    });

    it('sends the name, serves and time as changed on the screen', async () => {
      const flow = await reviewing();
      flow.name = 'Hotel sambar';
      flow.serves = '6';
      flow.minutes = '';
      const body = flow.body()!;
      expect([body.name, body.serves, body.time_minutes]).toEqual(['Hotel sambar', 6, null]);
      expect(body.source_url).toBe('https://kitchen.example/dal');
      expect(body.source_author).toBe('A cook');
      expect(body.photo_id).toBeNull();
      // A heading is sent with no link.
      expect(body.lines[3]).toMatchObject({ kind: 'heading', link: null });
    });

    it('saves once, with one change ID, and keeps the server’s sentence on a refusal', async () => {
      const flow = await reviewing();
      const requests = fakeApi({
        'POST /recipes/import/save': [
          409,
          { detail: 'There’s already an ingredient called Onions.', code: 'name_taken', line: 1 }
        ]
      });
      expect(await flow.save()).toBeNull();
      expect(flow.saveProblem).toEqual({
        message: 'There’s already an ingredient called Onions.',
        line: 1
      });
      await flow.save();
      // The same save, tried again, is the same change.
      expect(requests[0]!.headers['idempotency-key']).toBe(requests[1]!.headers['idempotency-key']);
    });

    it('refuses an empty name or a bad number before asking the server', async () => {
      const flow = await reviewing();
      const requests = fakeApi({});
      flow.name = '  ';
      expect(await flow.save()).toBeNull();
      expect(flow.saveProblem?.message).toBe('Type a name.');
      flow.name = 'Sambar';
      flow.serves = '100';
      expect(await flow.save()).toBeNull();
      expect(flow.saveProblem?.message).toContain('Serves is 1 to 99');
      expect(requests).toHaveLength(0);
    });

    it('goes back to the box with what was typed', async () => {
      const flow = await reviewing();
      flow.backToBox();
      expect(flow.phase).toBe('start');
      expect(flow.text).toBe('https://kitchen.example/dal');
    });
  });

  it('words the lines left out', () => {
    expect(leftOutWords('Tips', 4)).toBe('4 lines after “Tips” were left out');
    expect(leftOutWords('Notes', 1)).toBe('1 line after “Notes” was left out');
  });
});
