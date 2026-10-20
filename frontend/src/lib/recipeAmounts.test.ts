import { describe, expect, it } from 'vitest';
import type { RecipeLine } from './client/recipes';
import { factorOf, gramsText, lineAmount, makesAmount, quarters } from './recipeAmounts';

const line = (extra: Partial<RecipeLine>): RecipeLine => ({
  id: 1,
  kind: 'ingredient',
  words: 'x',
  amount: 1,
  amount_text: '1',
  unit: null,
  size: null,
  food: null,
  recipe: null,
  link: 'none',
  note: null,
  ...extra
});
const NB = '\u00a0';

describe('amounts at the recipe’s own servings', () => {
  it('are shown exactly as typed', () => {
    expect(lineAmount(line({ amount: 1.2, amount_text: '1.2', unit: 'tbsp' }), 1)).toBe(
      `1.2${NB}tbsp`
    );
    expect(lineAmount(line({ amount: 1.5, amount_text: '1½', unit: 'cup' }), 1)).toBe(
      `1½${NB}cups`
    );
    expect(lineAmount(line({ amount: 1, amount_text: '1', unit: 'cup' }), 1)).toBe(`1${NB}cup`);
    expect(lineAmount(line({ amount: 10, amount_text: '10' }), 1)).toBe('10');
  });

  it('are missing when the line has none', () => {
    expect(lineAmount(line({ amount: null, amount_text: null }), 2)).toBeNull();
  });
});

describe('amounts scaled on screen (question 26)', () => {
  it('grams and millilitres are whole numbers', () => {
    const grams = line({ amount: 200, amount_text: '200', unit: 'g' });
    expect(lineAmount(grams, 1.5)).toBe(`300${NB}g`);
    expect(lineAmount(line({ amount: 100, amount_text: '100', unit: 'ml' }), 1 / 3)).toBe(
      `33${NB}ml`
    );
    expect(lineAmount(line({ amount: 1, amount_text: '1', unit: 'g' }), 0.25)).toBe(`1${NB}g`);
  });

  it('spoons and cups come in quarters', () => {
    const spoons = line({ amount: 2, amount_text: '2', unit: 'tbsp' });
    expect(lineAmount(spoons, 1.5)).toBe(`3${NB}tbsp`);
    expect(lineAmount(spoons, 0.75)).toBe(`1½${NB}tbsp`);
    expect(lineAmount(spoons, 0.625)).toBe(`1¼${NB}tbsp`);
    expect(lineAmount(spoons, 0.1)).toBe(`¼${NB}tbsp`);
    expect(lineAmount(line({ amount: 1, amount_text: '1', unit: 'cup' }), 2)).toBe(`2${NB}cups`);
    expect(lineAmount(line({ amount: 1, amount_text: '1', unit: 'cup' }), 0.5)).toBe(`½${NB}cup`);
    expect(lineAmount(line({ amount: 1, amount_text: '1', unit: 'cup' }), 0.75)).toBe(`¾${NB}cup`);
  });

  it('counts come in halves', () => {
    const shallots = line({ amount: 10, amount_text: '10' });
    expect(lineAmount(shallots, 1.5)).toBe('15');
    expect(lineAmount(line({ amount: 3, amount_text: '3' }), 0.5)).toBe('1½');
    expect(lineAmount(line({ amount: 1, amount_text: '1' }), 0.1)).toBe('½');
  });

  it('packets use their own plural', () => {
    const size = { id: 1, name: 'packet', plural: 'packets' };
    expect(lineAmount(line({ amount: 1, amount_text: '1', size }), 2)).toBe(`2${NB}packets`);
    expect(lineAmount(line({ amount: 2, amount_text: '2', size }), 0.5)).toBe(`1${NB}packet`);
  });

  it('kilograms and litres keep two decimals', () => {
    expect(lineAmount(line({ amount: 1, amount_text: '1', unit: 'kg' }), 1.25)).toBe(`1.25${NB}kg`);
    expect(lineAmount(line({ amount: 1, amount_text: '1', unit: 'l' }), 3)).toBe(`3${NB}l`);
  });
});

describe('makes, nutrition and the scale', () => {
  it('makes scales with the servings', () => {
    const makes = { amount: 1.5, amount_text: '1½', unit: 'l' };
    expect(makesAmount(makes, 1)).toBe(`1½${NB}litres`);
    expect(makesAmount(makes, 2)).toBe(`3${NB}litres`);
    expect(makesAmount({ amount: 12, amount_text: '12', unit: 'dosas' }, 0.5)).toBe(`6${NB}dosas`);
  });

  it('shows grams to one decimal', () => {
    expect(gramsText(14.5)).toBe(`14.5${NB}g`);
    expect(gramsText(16)).toBe(`16${NB}g`);
    expect(quarters(2.75)).toBe('2¾');
    expect(factorOf(6, 4)).toBe(1.5);
  });
});
