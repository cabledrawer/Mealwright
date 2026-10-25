import { describe, expect, it } from 'vitest';
import type { LineOut, RecipeOut } from '#lib/client/recipes.js';
import { compareLines, compareSteps, otherChanges, quantityOf } from './compare';

const line = (
  id: number,
  words: string,
  amount_text: string | null = null,
  unit: string | null = null
): LineOut => ({
  id,
  kind: 'ingredient',
  words,
  amount: amount_text ? Number(amount_text) : null,
  amount_text,
  unit,
  size: null,
  food: null,
  recipe: null,
  link: 'none',
  note: null
});

describe('quantityOf', () => {
  it('joins the amount and unit with a no-break space', () => {
    expect(quantityOf(line(1, 'dal', '200', 'g'))).toBe('200 g');
    expect(quantityOf(line(1, 'shallots', '10'))).toBe('10');
    expect(quantityOf(line(1, 'salt'))).toBe('');
  });

  it('uses the size’s plural for more than one', () => {
    const sized = {
      ...line(1, 'dal', '2'),
      amount: 2,
      size: { id: 1, name: 'packet', plural: 'packets' }
    };
    expect(quantityOf(sized)).toBe('2 packets');
  });
});

describe('compareLines', () => {
  const opened = [line(1, 'dal', '200', 'g'), line(2, 'turmeric', '½', 'tsp'), line(3, 'salt')];

  it('marks a changed amount, an added line and a line taken out, and the rest as the same', () => {
    const theirs = [
      line(1, 'dal', '300', 'g'),
      line(2, 'turmeric', '½', 'tsp'),
      line(9, 'aubergine', '1')
    ];
    const shown = compareLines(opened, theirs);
    expect(shown.map((l) => [l.words, l.status, l.was])).toEqual([
      ['dal', 'changed', '200 g'],
      ['turmeric', 'same', null],
      ['aubergine', 'added', null],
      ['salt', 'removed', null]
    ]);
  });

  it('says what the words were when only the words changed', () => {
    const shown = compareLines([line(1, 'dal')], [line(1, 'toor dal')]);
    expect(shown[0]).toMatchObject({ status: 'changed', was: '“dal”' });
  });
});

describe('compareSteps and otherChanges', () => {
  const step = (id: number, text: string) => ({ id, kind: 'step' as const, text });

  it('numbers steps and marks the ones that differ', () => {
    const shown = compareSteps(
      [step(1, 'a'), step(2, 'b')],
      [step(1, 'a'), { id: 5, kind: 'heading', text: 'h' }, step(2, 'c')]
    );
    expect(shown.map((s) => [s.n, s.changed])).toEqual([
      [1, false],
      [null, true],
      [2, true]
    ]);
  });

  it('lists the other boxes that changed', () => {
    const base = {
      name: 'a',
      description: null,
      time_minutes: 10,
      serves: 4,
      makes: null,
      made_ahead: false,
      tags: [],
      nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
      source_note: null,
      photo: null
    } as unknown as RecipeOut;
    expect(otherChanges(base, { ...base, time_minutes: 20, tags: ['x'] })).toEqual([
      'time',
      'tags'
    ]);
    expect(otherChanges(base, base)).toEqual([]);
  });
});
