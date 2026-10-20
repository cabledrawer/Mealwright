import { describe, expect, it } from 'vitest';
import { ApiError } from '$lib/api';
import type { LineOut, RecipeOut } from '$lib/client/recipes';
import { blankLine, blankStep, RecipeDraft } from './draft.svelte';

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
        food: { id: 7, name: 'Toor dal' },
        link: 'ingredient',
        note: 'rinsed'
      }),
      line({
        id: 43,
        words: 'packet of dal',
        amount: 1,
        amount_text: '1',
        size: { id: 12, name: 'packet', plural: 'packets' },
        food: { id: 7, name: 'Toor dal' },
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
        note: 'rinsed'
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
        note: null
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
        note: null
      }
    ]);
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
    expect(draft.explain(gone, built)).toEqual({ photo: 'That photo isn’t here any more.' });
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
