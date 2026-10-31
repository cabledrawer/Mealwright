import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { ImportReview, ReviewLine } from '#lib/client/imports.js';
import { network } from '#lib/network.svelte.js';
import { fakeApi } from '#lib/testing/fakeApi.js';
import type { DraftOut } from './client/drafts';
import { PINTS_REVIEW } from '#lib/testing/importSamples.js';
import { amountWords, DRAFT_OFFLINE, ImportFlow, leftOutWords, volumeWords } from './import.svelte';

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
      ['2 onions and a link https://x.example', false],
      ['https://a.example/x\nhttps://b.example/y', true],
      ['https://a.example/x https://b.example/y\n', true],
      ['https://a.example/x\n2 onions', false]
    ] as const) {
      flow.text = text;
      expect(flow.isLink, text).toBe(link);
    }
  });

  it('counts the links when the box holds only links (F25)', () => {
    const flow = new ImportFlow();
    flow.text = 'https://a.example/x\nhttps://b.example/y';
    expect(flow.linkCount).toBe(2);
    flow.text = 'https://a.example/x';
    expect(flow.linkCount).toBe(1);
    flow.text = 'Sambar\nhttps://b.example/y';
    expect(flow.linkCount).toBe(0);
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
      expect(flow.linkOf(0)).toMatchObject({ kind: 'ingredient', learn: false });
      expect(flow.linkOf(1)).toBeNull();
      expect(flow.unlinked).toBe(2);
    });

    it('same as: ties the line to the ingredient and learns the name', async () => {
      const flow = await reviewing();
      flow.sameAs(1, { id: 2, name: 'Onions' });
      expect(flow.unlinked).toBe(1);
      expect(flow.body()!.lines[1]!.link).toEqual({
        kind: 'ingredient',
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

    it('sends Makes back in the units the review showed it in (24 cookies stays 24)', async () => {
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      fakeApi({
        'POST /recipes/import': [200, { ...REVIEW, makes: { amount: 24, unit: 'cookies' } }]
      });
      await flow.read();
      expect(flow.body()!.makes).toEqual({ amount: 24, unit: 'cookies' });
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

  describe('drafts', () => {
    const DRAFT: DraftOut = {
      id: 5,
      name: 'My sambar',
      source: { kind: 'link', site: 'kitchen.example' },
      started_by: 'Wren',
      started_at: '2026-10-20T10:00:00Z',
      updated_at: '2026-10-21T10:00:00Z',
      expires_at: '2026-11-05T10:00:00Z',
      days_left: 12,
      lines_total: 3,
      lines_checked: 2,
      text: 'https://kitchen.example/dal',
      review: REVIEW,
      choices: {
        name: 'My sambar',
        serves: '6',
        minutes: null,
        lines: {
          '1': { kind: 'ingredient', food: { id: 2, name: 'Onions' }, learn: true },
          '2': { kind: 'staple', name: 'Hing', counted_as: 'volume', place_id: null }
        }
      }
    };

    async function reviewing() {
      fakeApi({ 'POST /recipes/import': [200, REVIEW] });
      const flow = new ImportFlow();
      flow.text = 'https://kitchen.example/dal';
      await flow.read();
      return flow;
    }

    it('keeps the review as a draft once, then saves over the same draft', async () => {
      const flow = await reviewing();
      flow.name = 'My sambar';
      flow.sameAs(1, { id: 2, name: 'Onions' });
      expect(flow.unkept).toBe(true); // not kept yet: leaving always asks
      const requests = fakeApi({
        'POST /recipes/drafts': [201, DRAFT],
        'PUT /recipes/drafts/5': [200, DRAFT],
        'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
      });
      expect(await flow.keepAsDraft()).toBe(true);
      expect(flow.draftId).toBe(5);
      expect(flow.unkept).toBe(false);
      const sent = requests[0]!.body as { text: string; review: { name: string }; choices: object };
      expect(requests[0]!.method + ' ' + requests[0]!.path).toBe('POST /recipes/drafts');
      expect(sent.text).toBe('https://kitchen.example/dal');
      expect(sent.review.name).toBe('Sambar');
      expect(sent.choices).toMatchObject({
        name: 'My sambar',
        serves: '4',
        minutes: '50',
        lines: { '1': { kind: 'ingredient', food: { id: 2 }, learn: true } }
      });
      // A change after that is not kept yet, and saves over the draft (a PUT), not a new one.
      flow.minutes = '30';
      expect(flow.unkept).toBe(true);
      expect(await flow.keepAsDraft()).toBe(true);
      expect(requests.filter((r) => r.method === 'PUT')).toHaveLength(1);
      expect(
        requests.filter((r) => r.method === 'POST' && r.path === '/recipes/drafts')
      ).toHaveLength(1);
    });

    it('opens a draft with every choice made so far, and nothing changed', () => {
      const flow = new ImportFlow();
      flow.load(DRAFT);
      expect(flow.phase).toBe('review');
      expect(flow.draftId).toBe(5);
      expect(flow.text).toBe('https://kitchen.example/dal');
      expect(flow.name).toBe('My sambar');
      expect(flow.serves).toBe('6');
      expect(flow.minutes).toBe('50'); // left as read
      expect(flow.choices[1]).toMatchObject({ kind: 'ingredient', learn: true });
      expect(flow.choices[2]).toMatchObject({ kind: 'staple', name: 'Hing' });
      expect(flow.unlinked).toBe(0);
      expect(flow.unkept).toBe(false);
      flow.choose(2, null);
      expect(flow.unkept).toBe(true);
      flow.choose(2, DRAFT.choices.lines['2']!);
      expect(flow.unkept).toBe(false); // back as it was: nothing to keep
    });

    it('says the server’s sentence when it can’t keep one, and keeps nothing', async () => {
      const flow = await reviewing();
      fakeApi({
        'POST /recipes/drafts': [
          409,
          { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
        ]
      });
      expect(await flow.keepAsDraft()).toBe(false);
      expect(flow.draftProblem).toBe('You have 50 drafts. Finish or delete one first.');
      expect(flow.draftId).toBeNull();
      expect(flow.unkept).toBe(true);
    });

    it('says it needs the server when there is no connection', async () => {
      const flow = await reviewing();
      vi.stubGlobal('fetch', () => Promise.reject(new TypeError('offline')));
      expect(await flow.keepAsDraft()).toBe(false);
      expect(flow.draftProblem).toBe(DRAFT_OFFLINE);
    });

    it('saves from a draft by sending its id, and the same change ID on a retry', async () => {
      const flow = new ImportFlow();
      flow.load(DRAFT);
      const requests = fakeApi({
        'POST /recipes/import/save': [409, { detail: 'No.', code: 'name_taken', line: 1 }],
        'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
      });
      await flow.save();
      await flow.save();
      expect((requests[0]!.body as Record<string, unknown>).draft_id).toBe(5);
      expect(requests[0]!.headers['idempotency-key']).toBe(requests[1]!.headers['idempotency-key']);
    });

    it('sends no draft id when it was never kept', async () => {
      const flow = await reviewing();
      expect(flow.body()?.draft_id).toBeNull();
    });
  });
});

describe('pints on a US recipe', () => {
  beforeEach(() => network.reset());
  afterEach(() => vi.unstubAllGlobals());

  const milk = PINTS_REVIEW.lines[0]!;

  async function read(review: ImportReview = PINTS_REVIEW): Promise<ImportFlow> {
    fakeApi({ 'POST /recipes/import': [200, review] });
    const flow = new ImportFlow();
    flow.text = 'https://www.allrecipes.com/recipe/1/x/';
    await flow.read();
    return flow;
  }

  it('starts with the pint the server read the lines with', async () => {
    const flow = await read();
    expect(flow.pints).toBe('us');
    expect(flow.offersPints).toBe(true);
    const other = await read({
      ...PINTS_REVIEW,
      pints: { household: 'uk', us_site: false, reading: 'uk' }
    });
    expect(other.pints).toBe('uk');
    expect(other.offersPints).toBe(false);
  });

  it('gives a pint line the amount for the pint chosen, and no other line', async () => {
    const flow = await read();
    expect(flow.withPints(milk)).toMatchObject({ amount: 946, amount_text: '946', unit: 'ml' });
    flow.pints = 'uk';
    expect(flow.withPints(milk)).toMatchObject({ amount: 1136, amount_text: '1136', unit: 'ml' });
    const vanilla = PINTS_REVIEW.lines[1]!;
    expect(flow.withPints(vanilla)).toBe(vanilla);
  });

  it('sends the chosen pint’s amount on Save', async () => {
    const flow = await read();
    flow.pints = 'uk';
    const body = flow.body()!;
    expect(body.lines[0]).toMatchObject({ amount: 1136, unit: 'ml' });
    expect(body.lines[1]).toMatchObject({ amount: 1, unit: 'tsp' });
    flow.pints = 'us';
    expect(flow.body()!.lines[0]).toMatchObject({ amount: 946, unit: 'ml' });
  });

  it('says what the other pint would read, from the first pint line', async () => {
    const flow = await read();
    expect(flow.otherPints).toEqual({ words: 'whole milk', reads: '1.14 L', kind: 'uk' });
    flow.pints = 'uk';
    expect(flow.otherPints).toEqual({ words: 'whole milk', reads: '946 ml', kind: 'us' });
    const none = await read({ ...PINTS_REVIEW, lines: [PINTS_REVIEW.lines[1]!] });
    expect(none.otherPints).toBeNull();
  });

  it('keeps the switch in a draft only when it differs from how the review read', async () => {
    const flow = await read();
    expect(flow.draftBody()!.choices.pints).toBeNull();
    flow.pints = 'uk';
    expect(flow.draftBody()!.choices.pints).toBe('uk');
  });

  it('opens a draft with the switch as it was left, and a draft from before with the review’s', () => {
    const draft = (pints: 'uk' | 'us' | undefined): DraftOut =>
      ({
        id: 1,
        text: 'https://www.allrecipes.com/recipe/1/x/',
        review: PINTS_REVIEW,
        choices: { name: null, serves: null, minutes: null, pints, lines: {} }
      }) as unknown as DraftOut;
    const left = new ImportFlow();
    left.load(draft('uk'));
    expect(left.pints).toBe('uk');
    const before = new ImportFlow();
    before.load(draft(undefined));
    expect(before.pints).toBe('us');
  });

  it('counts a change of pint as a change since the draft was kept', () => {
    const flow = new ImportFlow();
    flow.load({
      id: 1,
      text: 'x',
      review: PINTS_REVIEW,
      choices: { name: null, serves: null, minutes: null, lines: {} }
    } as unknown as DraftOut);
    expect(flow.unkept).toBe(false);
    flow.pints = 'uk';
    expect(flow.unkept).toBe(true);
  });
});

describe('amounts in words', () => {
  it('reads a number or a volume', () => {
    expect(amountWords(946)).toBe('946');
    expect(amountWords(189.3333)).toBe('189.333');
    expect(volumeWords(284)).toBe('284 ml');
    expect(volumeWords(1000)).toBe('1 L');
    expect(volumeWords(1136)).toBe('1.14 L');
  });
});

describe('importer consistency on Check (0.7)', () => {
  beforeEach(() => network.reset());
  afterEach(() => vi.unstubAllGlobals());

  const icing = (over: Partial<ReviewLine>) =>
    line({
      written: '140g icing sugar, sifted',
      words: 'icing sugar',
      label: 'needs_you',
      food: null,
      place: null,
      learn_name: 'icing sugar',
      new_ingredient: { name: 'Icing sugar', counted_as: 'weight', place: null },
      ...over
    });

  function flowOf(review: Partial<ImportReview>): ImportFlow {
    const flow = new ImportFlow();
    flow.load({
      id: 1,
      name: 'Sponge',
      source: { kind: 'text', site: null },
      started_by: 'K',
      started_at: '',
      updated_at: '',
      expires_at: '',
      days_left: 15,
      lines_total: 0,
      lines_checked: 0,
      text: 'x',
      review: { ...REVIEW, ...review },
      choices: { name: null, serves: null, minutes: null, lines: {} }
    });
    return flow;
  }

  describe('F6: a choice made on one line is used on matching lines', () => {
    const lines = [
      icing({}),
      icing({ written: 'icing sugar, to decorate', note: 'to decorate' }),
      icing({ written: '1 egg', words: 'egg', learn_name: 'egg', new_ingredient: null })
    ];

    it('links a New ingredient to the other line with the same name, and only that one', () => {
      const flow = flowOf({ lines });
      flow.newIngredient(0);
      expect(flow.choices[1]).toMatchObject({ kind: 'new', name: 'Icing sugar' });
      expect(flow.choices[2]).toBeUndefined();
      expect(flow.followers(0)).toEqual([1]);
      expect(flow.unlinked).toBe(1);
    });

    it('follows a staple, and a staple tick on the first line', () => {
      const flow = flowOf({ lines });
      flow.newIngredient(0, true);
      expect(flow.choices[1]).toMatchObject({ kind: 'staple' });
      flow.setStaple(0, false);
      expect(flow.choices[0]).toMatchObject({ kind: 'new' });
      expect(flow.choices[1]).toMatchObject({ kind: 'new' });
    });

    it('links a picked ingredient to the matching line too', () => {
      const flow = flowOf({ lines });
      flow.sameAs(0, { id: 9, name: 'Icing sugar' });
      expect(flow.choices[1]).toMatchObject({ kind: 'ingredient', food: { id: 9 } });
    });

    it('leaves a line that has its own choice, and lets a followed line be changed', () => {
      const flow = flowOf({ lines });
      flow.sameAs(1, { id: 5, name: 'Sugar' });
      flow.newIngredient(0);
      expect(flow.choices[1]).toMatchObject({ kind: 'ingredient', food: { id: 5 } });
      flow.unchoose(1);
      expect(flow.choices[1]).toBeUndefined();
      expect(flow.followers(0)).toEqual([]);
    });
  });

  describe('F30.6: fixing the amount, unit and note', () => {
    it('changes what Save sends, and a draft keeps it', () => {
      const flow = flowOf({});
      const before = flow.unkept;
      flow.editLine(2, { amount: 2, amount_text: '2', unit: 'tbsp', note: 'heaped' });
      const sent = flow.body()!.lines[2]!;
      expect(sent).toMatchObject({ amount: 2, unit: 'tbsp', note: 'heaped' });
      expect(flow.draftBody()!.review.lines[2]).toMatchObject({ amount: 2, unit: 'tbsp' });
      expect(before).toBe(false);
      expect(flow.unkept).toBe(true);
    });

    it('takes a line off the pint switch once its amount is typed', () => {
      const flow = flowOf({
        pints: { household: 'uk', us_site: true, reading: 'us' },
        lines: [
          line({
            amount: 946,
            unit: 'ml',
            pint_ml: { uk_ml: 1136, us_ml: 946 }
          })
        ]
      });
      flow.editLine(0, { amount: 500, amount_text: '500' });
      flow.pints = 'uk';
      expect(flow.body()!.lines[0]).toMatchObject({ amount: 500, unit: 'ml' });
    });

    it('leaves the pint reading alone when only the note changes', () => {
      const flow = flowOf({
        pints: { household: 'uk', us_site: true, reading: 'us' },
        lines: [line({ amount: 946, unit: 'ml', pint_ml: { uk_ml: 1136, us_ml: 946 } })]
      });
      flow.editLine(0, { note: 'cold' });
      flow.pints = 'uk';
      expect(flow.body()!.lines[0]).toMatchObject({ amount: 1136, note: 'cold' });
    });

    it('does nothing to a heading', () => {
      const flow = flowOf({});
      flow.editLine(3, { amount: 5 });
      expect(flow.review!.lines[3]!.amount).toBe(1);
    });
  });

  describe('F4: going through the lines with no ingredient', () => {
    it('saves at once when every line is linked', async () => {
      const flow = flowOf({ lines: [line({})] });
      fakeApi({
        'POST /recipes/import/save': [
          200,
          {
            recipe: { id: 1, name: 'x' },
            change: { id: 1, summary: 's' },
            new_ingredients: [],
            learned: 0
          }
        ]
      });
      await flow.trySave();
      expect(flow.walk).toBeNull();
      expect(flow.saved).not.toBeNull();
    });

    it('opens the walk on the first unlinked line instead of saving', async () => {
      const flow = flowOf({});
      const saved = await flow.trySave();
      expect(saved).toBeNull();
      expect(flow.saved).toBeNull();
      expect(flow.walk).toEqual({ queue: [1, 2], at: 0 });
      expect(flow.walkLine).toBe(1);
    });

    it('moves on with Skip, skips lines settled meanwhile, and closes after the last', async () => {
      const flow = flowOf({});
      await flow.trySave();
      flow.walkNext();
      expect(flow.walkLine).toBe(2);
      flow.walkNext(); // both were skipped: the sheet stays, on its last card (L1)
      expect(flow.walk).not.toBeNull();
      expect(flow.walkLine).toBeNull();
      flow.walkClose();

      await flow.trySave();
      flow.sameAs(2, { id: 7, name: 'Hing' }); // settled before its turn
      flow.walkNext();
      expect(flow.walk).toBeNull();
    });

    it('Back to Check closes it with nothing saved', async () => {
      const flow = flowOf({});
      await flow.trySave();
      flow.walkClose();
      expect(flow.walk).toBeNull();
      expect(flow.saved).toBeNull();
    });

    it('Save anyway saves the lines as words', async () => {
      const flow = flowOf({});
      await flow.trySave();
      fakeApi({
        'POST /recipes/import/save': [
          200,
          {
            recipe: { id: 1, name: 'x' },
            change: { id: 1, summary: 's' },
            new_ingredients: [],
            learned: 0
          }
        ]
      });
      const saved = await flow.saveAnyway();
      expect(saved).not.toBeNull();
      expect(flow.walk).toBeNull();
      expect(flow.body()!.lines[1]!.link).toBeNull();
    });
  });

  describe('a new ingredient for a line with no guess', () => {
    it('starts from the line’s words', () => {
      const flow = flowOf({
        lines: [line({ label: 'needs_you', food: null, new_ingredient: null, words: 'asafoetida' })]
      });
      flow.newIngredient(0);
      expect(flow.choices[0]).toMatchObject({
        kind: 'new',
        name: 'Asafoetida',
        counted_as: 'weight'
      });
    });
  });

  describe('F13: splitting long steps', () => {
    const LONG =
      'Beat the butter and sugar until pale. Add the eggs one at a time. Fold in the flour. Divide between the tins. Level the tops.';
    const steps: ImportReview['steps'] = [
      { kind: 'step', text: 'Heat the oven.' },
      { kind: 'step', text: LONG }
    ];

    it('shows the split without changing anything', () => {
      const flow = flowOf({ steps });
      expect(flow.splitOf(0)).toBeNull();
      expect(flow.splitOf(1)).toHaveLength(3);
      expect(flow.review!.steps).toHaveLength(2);
      expect(flow.stepsBefore).toBeNull();
    });

    it('keeps the split only when asked, and puts the steps back', () => {
      const flow = flowOf({ steps });
      flow.keepSplit(1);
      expect(flow.review!.steps).toHaveLength(4);
      expect(flow.body()!.steps).toHaveLength(4);
      flow.putStepsBack();
      expect(flow.review!.steps).toEqual(steps);
      expect(flow.stepsBefore).toBeNull();
    });

    it('never splits a heading', () => {
      const flow = flowOf({ steps: [{ kind: 'heading', text: LONG }] });
      expect(flow.splitOf(0)).toBeNull();
    });
  });
});

describe('the save walk-through ends (L1)', () => {
  it('keeps the sheet on its last card while lines are still unlinked, and closes once none are', async () => {
    const flow = new ImportFlow();
    flow.review = {
      ...REVIEW,
      lines: [line({ label: 'needs_you', food: null }), line({ label: 'needs_you', food: null })]
    };
    await flow.trySave();
    flow.walkNext();
    flow.walkNext();
    expect(flow.walk).not.toBeNull();
    expect(flow.walkLine).toBeNull();
    expect(flow.unlinkedLines()).toHaveLength(2);
    flow.sameAs(0, { id: 1, name: 'A' });
    flow.sameAs(1, { id: 1, name: 'A' });
    flow.walkNext();
    expect(flow.walk).toBeNull();
  });
});
