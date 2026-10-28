import { describe, expect, it } from 'vitest';
import { perTubWords, timesWords, tubNumbers } from './cookOnce.svelte';

describe('Cook once words', () => {
  it('says which tubs, in a run or apart', () => {
    expect(tubNumbers([])).toBe('');
    expect(tubNumbers([5])).toBe('Tub 5');
    expect(tubNumbers([5, 6])).toBe('Tubs 5–6');
    expect(tubNumbers([2, 3, 4])).toBe('Tubs 2–4');
    expect(tubNumbers([2, 4, 6])).toBe('Tubs 2, 4 and 6');
  });

  it('words what is in a tub, leaving out what is unknown', () => {
    expect(perTubWords({ kcal: 410, protein_g: 12, fibre_g: 6 })).toBe(
      '410 kcal · 12 g protein · 6 g fibre'
    );
    expect(perTubWords({ kcal: 410, protein_g: null, fibre_g: null })).toBe('410 kcal');
    expect(perTubWords({ kcal: null, protein_g: null, fibre_g: null })).toBeNull();
  });

  it('says how much more than the recipe the batch makes', () => {
    expect(timesWords(5, 4)).toBe('× 1.5');
    expect(timesWords(3, 4)).toBe('× 1');
    expect(timesWords(4, 3)).toBe('× 1.67');
    expect(timesWords(5, null)).toBeNull();
  });
});
