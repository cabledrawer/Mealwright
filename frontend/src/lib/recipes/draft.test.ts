import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '#lib/api.js';
import type { LineOut, RecipeOut } from '#lib/client/recipes.js';
import { toasts } from '#lib/toast.svelte.js';
import { blankLine, blankStep, RecipeDraft, releaseWhenToastGoes } from './draft.svelte';

const photo = {
  id: 5,
  width: 1600,
  height: 1200,
  url: '/api/v1/recipes/photos/5/large',
  list_width: 208,
  list_height: 156,
  list_url: '/api/v1/recipes/photos/5/list'
};

function line(over: Partial<LineOut>): LineOut {
  return {
    id: 1,
    kind: 'ingredient',
    words: 'dal',
    amount: null,
    amount_text: null,
    unit: null,
    size: null,
    food: null,
    recipe: null,
    link: 'none',
    note: null,
    ...over
  };
}

function recipe(over: Partial<RecipeOut> = {}): RecipeOut {
  return {
    id: 3,
    name: 'Sambar',
    description: 'Lentil & vegetable stew',
    time_minutes: 50,
    serves: 6,
    makes: { amount: 1.5, amount_text: '1½', unit: 'l' },
    made_ahead: false,
    homemade: null,
    tags: ['Quick'],
    nutrition: { kcal: 320, protein: 14.5, carbs: null, fat: 0, fibre: null },
    lines: [
      line({ id: 41, kind: 'heading', words: 'For the dal', link: null }),
      line({
        id: 42,
        words: 'thuvaram paruppu',
        amount: 1.5,
        amount_text: '1½',
        unit: 'cup',
        food: { id: 7, name: 'Toor dal', other_names: [] },
        link: 'ingredient',
        note: 'rinsed'
      }),
      line({
        id: 43,
        words: 'packet of dal',
        amount: 1,
        amount_text: '1',
        size: { id: 12, name: 'packet', plural: 'packets' },
        food: { id: 7, name: 'Toor dal', other_names: [] },
        link: 'ingredient'
      }),
      line({
        id: 44,
        words: 'Sambar powder',
        amount: 2,
        amount_text: '2',
        unit: 'tbsp',
        recipe: { id: 9, name: 'Sambar powder' },
        link: 'recipe_removed'
      })
    ],
    steps: [{ id: 1, kind: 'step', text: 'Boil the dal.' }],
    source_note: 'Amma’s',
    photo,
    used_by: [],
    version: 4,
    updated_at: '2026-10-19T18:04:11+00:00',
    updated_by: { login_id: 1, name: 'Tess' },
    ...over
  };
}

describe('a new draft', () => {
  it('starts at Serves 4 with one empty line and one empty step, and is not changed yet', () => {
    const draft = new RecipeDraft();
    draft.markSaved();
    expect(draft.serves).toBe(4);
    expect(draft.lines).toHaveLength(1);
    expect(draft.steps).toHaveLength(1);
    expect(draft.dirty).toBe(false);
    draft.name = 'Rasam';
    expect(draft.dirty).toBe(true);
  });

  it('sends only what was filled in, with empty lines and steps left out', () => {
    const draft = new RecipeDraft();
    draft.name = '  Rasam ';
    const { body, errors } = draft.build();
    expect(errors).toEqual({});
    expect(body).toMatchObject({
      name: 'Rasam',
      description: null,
      time_minutes: null,
      serves: 4,
      makes: null,
      made_ahead: false,
      homemade_name: null,
      tags: [],
      lines: [],
      steps: [],
      source_note: null
    });
    expect(body.nutrition).toEqual({
      kcal: null,
      protein: null,
      carbs: null,
      fat: null,
      fibre: null
    });
  });
});

describe('opening a saved recipe', () => {
  it('fills every box and is not changed', () => {
    const draft = RecipeDraft.from(recipe());
    expect(draft.name).toBe('Sambar');
    expect(draft.time).toBe('50');
    expect(draft.serves).toBe(6);
    expect(draft.makesAmount).toBe('1½');
    expect(draft.makesUnit).toBe('l');
    expect(draft.nutrition).toEqual({
      kcal: '320',
      protein: '14.5',
      carbs: '',
      fat: '0',
      fibre: ''
    });
    expect(draft.lines.map((l) => [l.kind, l.words, l.amount, l.unit])).toEqual([
      ['heading', 'For the dal', '', ''],
      ['ingredient', 'thuvaram paruppu', '1½', 'cup'],
      ['ingredient', 'packet of dal', '1', 'size:12'],
      ['ingredient', 'Sambar powder', '2', 'tbsp']
    ]);
    expect(draft.lines[3]!.recipeRemoved).toBe(true);
    expect(draft.sizes[7]).toEqual([{ id: 12, name: 'packet', plural: 'packets' }]);
    expect(draft.dirty).toBe(false);
  });

  it('sends the whole recipe back, with line ids, sizes, links and a zero kept as zero', () => {
    const draft = RecipeDraft.from(recipe());
    const { body, errors, lineKeys } = draft.build();
    expect(errors).toEqual({});
    expect(lineKeys).toHaveLength(4);
    expect(body.makes).toEqual({ amount: '1½', unit: 'l' });
    expect(body.nutrition).toEqual({
      kcal: '320',
      protein: '14.5',
      carbs: null,
      fat: '0',
      fibre: null
    });
    expect(body.lines).toEqual([
      { id: 41, kind: 'heading', words: 'For the dal' },
      {
        id: 42,
        kind: 'ingredient',
        words: 'thuvaram paruppu',
        amount: '1½',
        unit: 'cup',
        size_id: null,
        food_id: 7,
        recipe_id: null,
        note: 'rinsed',
        optional: false
      },
      {
        id: 43,
        kind: 'ingredient',
        words: 'packet of dal',
        amount: '1',
        unit: null,
        size_id: 12,
        food_id: 7,
        recipe_id: null,
        note: null,
        optional: false
      },
      {
        id: 44,
        kind: 'ingredient',
        words: 'Sambar powder',
        amount: '2',
        unit: 'tbsp',
        size_id: null,
        food_id: null,
        recipe_id: 9, // the link to a removed recipe is kept for Undo
        note: null,
        optional: false
      }
    ]);
  });

  it('keeps what is Optional, on a line and on a step, and notices the switch (R3)', () => {
    const draft = RecipeDraft.from(
      recipe({
        lines: [line({ id: 1, words: 'kewra water', optional: true }), line({ id: 2 })],
        steps: [
          { id: 1, kind: 'step', text: 'Boil.' },
          { id: 2, kind: 'step', text: 'Top it.', optional: true },
          { id: 3, kind: 'heading', text: 'To serve' }
        ]
      })
    );
    expect(draft.lines.map((l) => l.optional)).toEqual([true, false]);
    expect(draft.steps.map((s) => s.optional)).toEqual([false, true, false]);
    const { body } = draft.build();
    expect(body.lines.map((l) => l.optional)).toEqual([true, false]);
    // A heading is never sent as optional.
    expect(body.steps.map((s) => s.optional)).toEqual([false, true, false]);
    expect(draft.dirty).toBe(false);
    draft.lines[1]!.optional = true;
    expect(draft.dirty).toBe(true);
    draft.lines[1]!.optional = false;
    draft.steps[0]!.optional = true;
    expect(draft.dirty).toBe(true);
  });

  it('an Optional switch survives the tab keeping the boxes (R3)', () => {
    const draft = RecipeDraft.from(
      recipe({
        lines: [line({ id: 1, optional: true })],
        steps: [{ id: 1, kind: 'step', text: 'Top it.', optional: true }]
      })
    );
    const again = RecipeDraft.from(recipe());
    expect(again.applyCarried(JSON.parse(JSON.stringify(draft.toCarried())))).toBe(true);
    expect(again.lines.map((l) => l.optional)).toEqual([true]);
    expect(again.steps.map((s) => s.optional)).toEqual([true]);
  });

  it("keeps a step's wait, sends it, notices a change and keeps it across the tab (M1)", () => {
    const wait = { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false };
    const draft = RecipeDraft.from(
      recipe({
        steps: [
          { id: 1, kind: 'step', text: 'Ferment the batter.', wait },
          { id: 2, kind: 'step', text: 'Cook.' }
        ]
      })
    );
    expect(draft.steps.map((s) => s.wait)).toEqual([wait, null]);
    expect(draft.build().body.steps.map((s) => s.wait)).toEqual([wait, null]);
    expect(draft.dirty).toBe(false);
    draft.steps[0]!.wait = { ...wait, max_minutes: 900 };
    expect(draft.dirty).toBe(true);
    const again = RecipeDraft.from(recipe());
    expect(again.applyCarried(JSON.parse(JSON.stringify(draft.toCarried())))).toBe(true);
    expect(again.steps[0]!.wait).toEqual({ ...wait, max_minutes: 900 });
    expect(again.steps[1]!.wait).toBeNull();
  });

  it("won't build while a step's Waits boxes are not right, so the old wait is never saved (M1)", () => {
    const wait = { kind: 'ferment', min_minutes: 480, max_minutes: 720, overnight: false };
    const draft = RecipeDraft.from(
      recipe({ steps: [{ id: 1, kind: 'step', text: 'Ferment the batter.', wait }] })
    );
    draft.steps[0]!.waitInvalid = true;
    const step = draft.steps[0]!;
    expect(Object.keys(draft.build().errors)).toEqual([`wait:${step.key}`]);
    step.waitInvalid = false;
    expect(draft.build().errors).toEqual({});
    step.waitInvalid = true;
    step.wait = null; // "Take off the wait" puts it right
    expect(draft.build().errors).toEqual({});
  });

  it('holds two ways of cooking it: switch, name, send both, remove one (M2)', () => {
    const draft = RecipeDraft.from(
      recipe({
        lines: [line({ id: 1, words: 'water' })],
        steps: [{ id: 1, kind: 'step', text: 'Simmer.' }],
        time_minutes: 45
      })
    );
    expect(draft.hidden).toBeNull();
    expect(draft.build().body.second_method).toBeUndefined(); // one way: nothing said of methods
    draft.addSecondMethod();
    expect(draft.at).toBe(1);
    draft.lines = [{ ...blankLine(), words: 'stock' }];
    draft.steps = [{ ...blankStep(), text: 'Pressure cook.' }];
    draft.time = '30';
    expect(Object.keys(draft.build().errors).sort()).toEqual(['method0', 'method1']);
    draft.names = ['Stovetop', 'Instant Pot'];
    const { body, errors } = draft.build();
    expect(errors).toEqual({});
    expect(body.method_name).toBe('Stovetop');
    expect(body.time_minutes).toBe(45);
    expect(body.lines.map((l) => l.words)).toEqual(['water']);
    expect(body.second_method).toMatchObject({ name: 'Instant Pot', time_minutes: 30 });
    expect(body.second_method?.lines.map((l) => l.words)).toEqual(['stock']);
    expect(draft.at).toBe(1); // building doesn't move the person
    draft.showMethod(0);
    expect(draft.lines.map((l) => l.words)).toEqual(['water']);
    expect(draft.time).toBe('45');
    draft.names = ['Same', 'same'];
    expect(draft.build().errors.method1).toMatch(/different names/);
  });

  it('opened with two ways, the second can be taken out, and the first too (M2)', () => {
    const two = recipe({
      lines: [line({ id: 1, words: 'water' })],
      steps: [{ id: 1, kind: 'step', text: 'Simmer.' }],
      methods: [
        { id: 10, name: 'Stovetop', time_minutes: 45, used_last: false },
        { id: 11, name: 'Instant Pot', time_minutes: 30, used_last: true }
      ],
      second_method: {
        id: 11,
        name: 'Instant Pot',
        time_minutes: 30,
        used_last: true,
        lines: [line({ id: 2, words: 'stock' })],
        steps: [{ id: 2, kind: 'step', text: 'Pressure cook.' }]
      }
    } as Partial<RecipeOut>);
    const draft = RecipeDraft.from(two);
    expect(draft.names).toEqual(['Stovetop', 'Instant Pot']);
    expect(draft.dirty).toBe(false);
    draft.showMethod(1);
    expect(draft.dirty).toBe(true);
    draft.showMethod(0);
    expect(draft.dirty).toBe(false);
    expect(draft.build().body.second_method?.lines[0]?.id).toBe(2);
    draft.showMethod(1);
    draft.removeShownMethod(); // the second goes
    const gone = draft.build().body;
    expect(gone.second_method).toBeNull();
    expect(gone.lines.map((l) => l.words)).toEqual(['water']);
    const again = RecipeDraft.from(two);
    again.removeShownMethod(); // the first goes: the second's lines are new ones
    const kept = again.build().body;
    expect(kept.second_method).toBeNull();
    expect(kept.lines.map((l) => [l.words, l.id])).toEqual([['stock', undefined]]);
    expect(again.toCarried().twoMethods).toBe(false);
    expect(RecipeDraft.from(two).toCarried().twoMethods).toBe(true);
  });

  it('opened from "Update nutrition", Save says the figures were looked at (R3)', () => {
    const draft = RecipeDraft.from(recipe());
    expect(draft.build().body.nutrition_checked).toBeUndefined();
    draft.nutritionChecked = true;
    expect(draft.build().body.nutrition_checked).toBe(true);
  });

  it('shows a makes unit that is a word as "count"', () => {
    const draft = RecipeDraft.from(
      recipe({ makes: { amount: 12, amount_text: '12', unit: 'dosas' } })
    );
    expect([draft.makesUnit, draft.makesWord]).toEqual(['count', 'dosas']);
    expect(draft.build().body.makes).toEqual({ amount: '12', unit: 'dosas' });
  });

  it('notices a change, and a change put back', () => {
    const draft = RecipeDraft.from(recipe());
    draft.lines[1]!.amount = '2';
    expect(draft.dirty).toBe(true);
    draft.lines[1]!.amount = '1½';
    expect(draft.dirty).toBe(false);
  });
});

describe('an upload that lands after the editor was left', () => {
  afterEach(() => vi.unstubAllGlobals());

  /** A server whose photo upload answers only when the test says so. */
  function slowUpload() {
    const sent: string[] = [];
    const waiting: ((answer: Response) => void)[] = [];
    let arrived: () => void = () => {};
    const posted = new Promise<void>((resolve) => (arrived = resolve));
    vi.stubGlobal('fetch', (input: string, init: RequestInit = {}) => {
      const call = `${init.method ?? 'GET'} ${String(input).replace('/api/v1', '')}`;
      sent.push(call);
      if (call === 'POST /recipes/photos') {
        return new Promise<Response>((resolve) => {
          waiting.push(resolve);
          arrived();
        });
      }
      return Promise.resolve(new Response(null, { status: 204 }));
    });
    const file = new File([new Uint8Array([1])], 'dish.png', { type: 'image/png' });
    return {
      sent,
      file,
      posted,
      land: (answer: Response, which = 0) => waiting[which]!(answer)
    };
  }
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('is deleted at once, and shows nothing', async () => {
    const { sent, file, posted, land } = slowUpload();
    const draft = new RecipeDraft();
    const picking = draft.pickPhoto(file);
    await posted;
    draft.discardUpload(); // Cancel while it is going up
    land(new Response(JSON.stringify({ ...photo, id: 9 }), { status: 201 }));
    await picking;
    await flush();
    expect(sent).toContain('DELETE /recipes/photos/9');
    expect(draft.photo).toMatchObject({
      shown: null,
      change: 'none',
      uploading: null,
      error: null
    });
    expect(draft.build().body).not.toHaveProperty('photo_id');
  });

  it('shows no error if it failed after the editor was left', async () => {
    const { sent, file, posted, land } = slowUpload();
    const draft = new RecipeDraft();
    const picking = draft.pickPhoto(file);
    await posted;
    draft.discardUpload();
    land(new Response(JSON.stringify({ detail: 'x', code: 'not_a_photo' }), { status: 422 }));
    await picking;
    expect(draft.photo.error).toBeNull();
    expect(sent.some((c) => c.startsWith('DELETE'))).toBe(false);
  });

  it('is kept when the editor was left and then opened again before it landed', async () => {
    const { sent, file, posted, land } = slowUpload();
    const draft = new RecipeDraft();
    const first = draft.pickPhoto(file);
    await posted;
    draft.discardUpload();
    const again = draft.pickPhoto(file); // Undo opened the editor again
    await flush();
    land(new Response(JSON.stringify({ ...photo, id: 9 }), { status: 201 }), 0);
    land(new Response(JSON.stringify({ ...photo, id: 10 }), { status: 201 }), 1);
    await Promise.all([first, again]);
    await flush();
    expect(sent).toContain('DELETE /recipes/photos/9'); // the first one, left behind
    expect(sent).not.toContain('DELETE /recipes/photos/10');
    expect(draft.photo).toMatchObject({ change: 'new' });
  });
});

describe('an upload kept for Undo', () => {
  afterEach(() => vi.unstubAllGlobals());

  function server() {
    const sent: string[] = [];
    const waiting: ((answer: Response) => void)[] = [];
    let arrived: () => void = () => {};
    const posted = new Promise<void>((resolve) => (arrived = resolve));
    vi.stubGlobal('fetch', (input: string, init: RequestInit = {}) => {
      const call = `${init.method ?? 'GET'} ${String(input).replace('/api/v1', '')}`;
      sent.push(call);
      if (call === 'POST /recipes/photos') {
        return new Promise<Response>((resolve) => {
          waiting.push(resolve);
          arrived();
        });
      }
      return Promise.resolve(new Response(null, { status: 204 }));
    });
    const file = new File([new Uint8Array([1])], 'dish.png', { type: 'image/png' });
    const land = (id: number) =>
      waiting[0]!(new Response(JSON.stringify({ ...photo, id }), { status: 201 }));
    return { sent, file, posted, land };
  }
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
  const deletes = (sent: string[]) => sent.filter((c) => c.startsWith('DELETE'));

  async function withUpload() {
    const s = server();
    const draft = RecipeDraft.from(recipe({ photo: null }));
    const picking = draft.pickPhoto(s.file);
    await s.posted;
    s.land(9);
    await picking;
    return { ...s, draft };
  }

  it('is not deleted while Undo can still be used, and is sent when Undo brought it back', async () => {
    const { sent, draft } = await withUpload();
    draft.park();
    await flush();
    expect(deletes(sent)).toEqual([]);
    draft.resume(); // Undo was pressed
    draft.release(); // the toast goes after that: nothing happens
    await flush();
    expect(deletes(sent)).toEqual([]);
    expect(draft.build().body.photo_id).toBe(9);
  });

  it('is deleted when Undo can no longer be used, and the photo goes back to how it was opened', async () => {
    const { sent, draft } = await withUpload();
    draft.park();
    draft.release();
    await flush();
    expect(deletes(sent)).toEqual(['DELETE /recipes/photos/9']);
    expect(draft.photo).toMatchObject({ shown: null, change: 'none', uploading: null });
    expect('photo_id' in draft.build().body).toBe(false); // never the deleted upload's id
  });

  it('puts back the recipe’s own photo, not a stale id, when the upload had replaced it', async () => {
    const s = server();
    const draft = RecipeDraft.from(recipe({ photo }));
    const picking = draft.pickPhoto(s.file);
    await s.posted;
    s.land(9);
    await picking;
    draft.park();
    draft.release();
    expect(draft.photo).toMatchObject({ shown: photo, change: 'none' });
    expect('photo_id' in draft.build().body).toBe(false);
  });

  it('is deleted when the "Changes not saved" toast goes', async () => {
    const { sent, draft } = await withUpload();
    const id = toasts.show('Changes not saved');
    draft.park();
    releaseWhenToastGoes(draft, id);
    await flush();
    expect(deletes(sent)).toEqual([]);
    toasts.dismiss(id);
    await vi.waitFor(() => expect(deletes(sent)).toEqual(['DELETE /recipes/photos/9']));
  });

  it('is left alone when Undo was pressed as the toast went', async () => {
    const { sent, draft } = await withUpload();
    const id = toasts.show('Changes not saved');
    draft.park();
    releaseWhenToastGoes(draft, id);
    draft.resume(); // Undo's button dismisses the toast, then reopens the editor
    toasts.dismiss(id);
    await flush();
    await flush();
    expect(deletes(sent)).toEqual([]);
    expect(draft.photo.change).toBe('new');
  });

  it('one still going up when Cancel was pressed is kept for Undo if it lands in time', async () => {
    const { sent, file, posted, land } = server();
    const draft = new RecipeDraft();
    const picking = draft.pickPhoto(file);
    await posted;
    draft.park();
    land(9);
    await picking;
    await flush();
    expect(deletes(sent)).toEqual([]);
    expect(draft.photo).toMatchObject({ change: 'new', uploading: null });
    draft.resume(); // Undo
    expect(draft.build().body.photo_id).toBe(9);
    draft.park();
    draft.release(); // ...and when Undo goes, it goes too
    await flush();
    expect(deletes(sent)).toEqual(['DELETE /recipes/photos/9']);
  });

  it('one still going up is deleted the moment it lands, if Undo is gone by then', async () => {
    const { sent, file, posted, land } = server();
    const draft = new RecipeDraft();
    const picking = draft.pickPhoto(file);
    await posted;
    draft.park();
    draft.release();
    land(9);
    await picking;
    await flush();
    expect(deletes(sent)).toEqual(['DELETE /recipes/photos/9']);
    expect(draft.photo).toMatchObject({
      shown: null,
      change: 'none',
      uploading: null,
      error: null
    });
  });
});

describe('the photo (cabledrawer 20 Oct)', () => {
  it('leaves photo_id out when the photo is untouched', () => {
    const { body } = RecipeDraft.from(recipe()).build();
    expect('photo_id' in body).toBe(false);
  });

  it('leaves photo_id out for a new recipe with no photo', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    expect('photo_id' in draft.build().body).toBe(false);
  });

  it('sends photo_id null, explicitly, when Remove photo was pressed', () => {
    const draft = RecipeDraft.from(recipe());
    draft.removePhoto();
    const { body } = draft.build();
    expect('photo_id' in body).toBe(true);
    expect(body.photo_id).toBeNull();
    expect(draft.dirty).toBe(true);
  });

  it('sends the upload’s id when a new photo was picked', () => {
    const draft = RecipeDraft.from(recipe({ photo: null }));
    draft.photo = {
      shown: { ...photo, id: 8 },
      change: 'new',
      uploading: null,
      file: null,
      error: null
    };
    expect(draft.build().body.photo_id).toBe(8);
  });

  it('removing a photo from a recipe that had none leaves the field out', () => {
    const draft = RecipeDraft.from(recipe({ photo: null }));
    draft.photo = {
      shown: { ...photo, id: 8 },
      change: 'new',
      uploading: null,
      file: null,
      error: null
    };
    draft.removePhoto();
    expect('photo_id' in draft.build().body).toBe(false);
  });
});

describe('what is wrong with the boxes', () => {
  it('marks whole minutes, nutrition and a line with no words, and sends nothing', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    draft.time = '1h';
    draft.nutrition.kcal = 'lots';
    draft.lines = [{ ...blankLine(), amount: '2' }];
    const { errors } = draft.build();
    expect(errors.time).toBe('Use whole minutes, from 1 to 14,400.');
    expect(errors['nutrition.kcal']).toBe('Use a number like 320 or 14.5, or leave it empty.');
    expect(errors[`line:${draft.lines[0]!.key}`]).toBe('Type what it is, or pick an ingredient.');
  });

  it('accepts a comma as the decimal point', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    draft.nutrition.protein = '14,5';
    expect(draft.build().body.nutrition.protein).toBe('14.5');
  });

  it('asks what a count is called', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    draft.makesAmount = '12';
    draft.makesUnit = 'count';
    expect(draft.build().errors.makes).toBe('Say what it makes, like dosas.');
  });

  it('puts the server’s refusals on the right boxes', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    draft.lines = [blankLine(), { ...blankLine(), words: 'salt', amount: 'lots' }];
    draft.lines[0]!.words = 'dal';
    draft.steps = [{ ...blankStep(), text: 'a' }];
    const built = draft.build();
    const refusal = new ApiError(422, 'Type an amount', null, {
      detail: [
        { loc: ['body', 'lines', 1, 'amount'], msg: 'Value error, Type an amount like 200.' },
        { loc: ['body', 'steps', 0, 'text'], msg: 'Type the step.' },
        { loc: ['body', 'nutrition', 'kcal'], msg: 'Too much.' },
        { loc: ['body', 'time_minutes'], msg: 'Too long.' }
      ]
    });
    expect(draft.explain(refusal, built)).toEqual({
      [`line:${built.lineKeys[1]}.amount`]: 'Type an amount like 200.',
      [`step:${built.stepKeys[0]}`]: 'Type the step.',
      'nutrition.kcal': 'Too much.',
      time: 'Too long.'
    });
  });

  it('puts a loop on its line, the made-ahead name clash under Made ahead, and a photo under the photo', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    draft.lines = [{ ...blankLine(), words: 'powder' }];
    const built = draft.build();
    const loop = new ApiError(
      409,
      'Sambar powder can’t use Sambar, because Sambar uses Sambar powder.',
      'recipe_loop',
      {
        line: 0
      }
    );
    expect(draft.explain(loop, built)).toEqual({
      [`line:${built.lineKeys[0]}`]:
        'Sambar powder can’t use Sambar, because Sambar uses Sambar powder.'
    });
    const taken = new ApiError(
      409,
      'There’s already an ingredient called Dosa batter.',
      'name_taken',
      {}
    );
    expect(draft.explain(taken, built)).toEqual({
      homemade: 'There’s already an ingredient called Dosa batter.'
    });
    const gone = new ApiError(404, 'That photo isn’t here any more.', 'not_found', {});
    expect(draft.explain(gone, built)).toEqual({});
    draft.photo = { ...draft.photo, shown: { ...photo, id: 8 }, change: 'new' };
    expect(draft.explain(gone, built)).toEqual({ photo: 'That photo isn’t here any more.' });
  });

  it('knows a photo problem by its code, and shows the server’s own words', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    const built = draft.build();
    for (const [status, code, words] of [
      [413, 'photo_too_big', 'That photo is bigger than 15 MB.'],
      [
        422,
        'too_many_pixels',
        'That photo is too big to use (over 50 megapixels). Try a smaller copy.'
      ],
      [422, 'not_a_photo', 'That isn’t a photo Mealwright can use. Try a JPEG, PNG or WebP.'],
      [
        409,
        'too_many_photos_waiting',
        'Too many photos waiting to be saved. Save or cancel a recipe first.'
      ]
    ] as const) {
      expect(draft.explain(new ApiError(status, words, code, {}), built)).toEqual({ photo: words });
    }
  });

  it('does not take a refusal for a photo problem just because it says "photo"', () => {
    const draft = new RecipeDraft();
    draft.name = 'x';
    const built = draft.build();
    const other = new ApiError(422, 'Photo sauce needs a name.', null, {
      detail: [{ loc: ['body', 'name'], msg: 'Give it a name.' }]
    });
    expect(draft.explain(other, built)).toEqual({ name: 'Give it a name.' });
    const server = new ApiError(500, 'The photo cookbook broke.', 'server_error', {});
    expect(draft.explain(server, built)).toEqual({});
  });
});

describe('made ahead', () => {
  it('sends the ingredient’s own name only when it was typed', () => {
    const draft = new RecipeDraft();
    draft.name = 'Dosa batter';
    draft.madeAhead = true;
    expect(draft.build().body).toMatchObject({ made_ahead: true, homemade_name: null });
    draft.homemadeName = ' Batter ';
    expect(draft.build().body.homemade_name).toBe('Batter');
  });
});

describe('restoring a cancelled editor', () => {
  it('brings back every box, as it was, and what counted as saved', () => {
    const was = RecipeDraft.from(recipe());
    was.name = 'Changed';
    was.lines[1]!.amount = '3';
    was.tags.push('Kids');
    const again = new RecipeDraft();
    again.restore(was);
    expect(again.name).toBe('Changed');
    expect(again.lines[1]!.amount).toBe('3');
    expect(again.tags).toEqual(['Quick', 'Kids']);
    expect(again.opened?.version).toBe(4);
    expect(again.dirty).toBe(true);
    again.name = 'Sambar';
    again.lines[1]!.amount = '1½';
    again.tags.pop();
    expect(again.dirty).toBe(false);
  });
});
