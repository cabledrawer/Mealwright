import { describe, expect, it } from 'vitest';
import type { EditFood } from './amountEdit';
import { readDraft, startDraft, stepDraft, switchUnit, unitChoices } from './amountBox';
import type { FoodSize } from './types';

const packet: FoodSize = { id: 12, name: 'packet', plural: 'packets', amount: 500, usual: true };
const dozen: FoodSize = { id: 7, name: 'dozen', plural: 'dozens', amount: 12, usual: false };

const dal = { counted_as: 'weight' as const };
const dalFood: EditFood = {
  counted_as: 'weight',
  count_word: null,
  count_word_plural: null,
  sizes: [packet]
};
const eggs = { counted_as: 'count' as const };
const eggsFood: EditFood = {
  counted_as: 'count',
  count_word: null,
  count_word_plural: null,
  sizes: [dozen]
};

describe('unitChoices', () => {
  it('offers g and kg, then the ingredient’s own sizes with what they hold', () => {
    const choices = unitChoices(dal, [packet]);
    expect(choices.map((c) => c.label)).toEqual(['g', 'kg', 'packet (500 g)']);
  });
  it('offers ml and L for a liquid', () => {
    expect(unitChoices({ counted_as: 'volume' }, []).map((c) => c.label)).toEqual(['ml', 'L']);
  });
  it('offers only items for something counted one by one with no sizes', () => {
    expect(unitChoices(eggs, [])).toHaveLength(1);
    expect(unitChoices(eggs, [dozen]).map((c) => c.key)).toEqual(['count', 'size:7']);
  });
});

describe('startDraft', () => {
  const choices = unitChoices(dal, [packet]);
  it('shows the real amount, not a hint', () => {
    expect(startDraft({ amount: 500, size_id: null }, dal, choices)).toEqual({
      text: '500',
      unit: 'g'
    });
  });
  it('shows a whole number of kilos as kilos', () => {
    expect(startDraft({ amount: 2000, size_id: null }, dal, choices)).toEqual({
      text: '2',
      unit: 'kg'
    });
  });
  it('shows a line written in packets as packets, halves included', () => {
    expect(startDraft({ amount: 750, size_id: 12 }, dal, choices)).toEqual({
      text: '1.5',
      unit: 'size:12'
    });
  });
  it('falls back to grams when the packet count would be an odd fraction', () => {
    expect(startDraft({ amount: 333, size_id: 12 }, dal, choices)).toEqual({
      text: '333',
      unit: 'g'
    });
  });
  it('starts empty, in the usual size, when there is no amount', () => {
    expect(startDraft({ amount: null, size_id: null }, dal, choices)).toEqual({
      text: '',
      unit: 'size:12'
    });
    expect(startDraft({ amount: null, size_id: null }, eggs, unitChoices(eggs, [dozen]))).toEqual({
      text: '',
      unit: 'count'
    });
  });
});

describe('readDraft', () => {
  const choices = unitChoices(dal, [packet]);
  it('reads the number in the chosen unit', () => {
    expect(readDraft({ text: '2', unit: 'kg' }, choices, dalFood)).toEqual({
      amount: 2000,
      sizeId: null
    });
    expect(readDraft({ text: '1.5', unit: 'size:12' }, choices, dalFood)).toEqual({
      amount: 750,
      sizeId: 12
    });
  });
  it('reads a bare count', () => {
    const c = unitChoices(eggs, []);
    expect(readDraft({ text: '6', unit: 'count' }, c, eggsFood)).toEqual({
      amount: 6,
      sizeId: null
    });
  });
  it('says what is wrong with nothing or with words', () => {
    expect(readDraft({ text: '', unit: 'g' }, choices, dalFood)).toHaveProperty('problem');
    expect(readDraft({ text: 'lots', unit: 'g' }, choices, dalFood)).toHaveProperty('problem');
  });
});

describe('switchUnit', () => {
  const choices = unitChoices(dal, [packet]);
  it('keeps the same amount in the new unit', () => {
    expect(switchUnit({ text: '500', unit: 'g' }, 'kg', choices, dalFood)).toEqual({
      text: '0.5',
      unit: 'kg'
    });
    expect(switchUnit({ text: '500', unit: 'g' }, 'size:12', choices, dalFood)).toEqual({
      text: '1',
      unit: 'size:12'
    });
  });
  it('only changes the unit when there is nothing to convert', () => {
    expect(switchUnit({ text: '', unit: 'g' }, 'kg', choices, dalFood)).toEqual({
      text: '',
      unit: 'kg'
    });
    expect(switchUnit({ text: 'lots', unit: 'g' }, 'kg', choices, dalFood)).toEqual({
      text: 'lots',
      unit: 'kg'
    });
  });
});

describe('stepDraft', () => {
  const choices = unitChoices(dal, [packet]);
  it('moves by 50 g, half a kilo or half a packet', () => {
    expect(stepDraft({ text: '500', unit: 'g' }, 1, choices, dalFood).text).toBe('550');
    expect(stepDraft({ text: '2', unit: 'kg' }, -1, choices, dalFood).text).toBe('1.5');
    expect(stepDraft({ text: '1', unit: 'size:12' }, 1, choices, dalFood).text).toBe('1.5');
  });
  it('counts one at a time', () => {
    const c = unitChoices(eggs, []);
    expect(stepDraft({ text: '4', unit: 'count' }, 1, c, eggsFood).text).toBe('5');
  });
  it('never goes to zero or below', () => {
    expect(stepDraft({ text: '50', unit: 'g' }, -1, choices, dalFood).text).toBe('50');
    expect(stepDraft({ text: '1', unit: 'count' }, -1, unitChoices(eggs, []), eggsFood).text).toBe(
      '1'
    );
  });
  it('starts from nothing with the first step', () => {
    expect(stepDraft({ text: '', unit: 'g' }, 1, choices, dalFood).text).toBe('50');
  });
});
