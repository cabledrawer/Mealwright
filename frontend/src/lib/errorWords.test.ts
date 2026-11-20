import { describe, expect, it } from 'vitest';
import { ApiError, SOMETHING_WENT_WRONG, cantReachWords, wordsFor, wordsForSave } from './api';
import { couldntAdd, couldntLoad } from './errorWords';
import { nothingChanged } from './downWords';
import { network } from './network.svelte';

describe('error words (FE5, FE23)', () => {
  it('builds the load and add sentences in one shape', () => {
    expect(couldntLoad('the plan')).toBe('Couldn’t load the plan. Try again.');
    expect(couldntAdd('that shop')).toBe('Couldn’t add that shop. Try again.');
  });
  it('wordsFor: no connection gives the can’t-reach words, whatever the fallback', () => {
    expect(wordsFor(new ApiError(0, 'x'), 'Couldn’t load the plan. Try again.')).toBe(
      cantReachWords()
    );
  });
  it('wordsFor: a screen’s own sentence wins over the server’s reason', () => {
    expect(wordsFor(new ApiError(500, 'Boom'), couldntLoad('the plan'))).toBe(
      'Couldn’t load the plan. Try again.'
    );
  });
  it('wordsFor: with no sentence of its own it shows the server’s reason, else the one fallback', () => {
    expect(wordsFor(new ApiError(404, 'That is gone.'))).toBe('That is gone.');
    expect(wordsFor(new Error('odd'))).toBe(SOMETHING_WENT_WRONG);
  });
  it('wordsForSave: says nothing changed when the server can’t be reached', () => {
    expect(wordsForSave(new ApiError(0, 'x'))).toBe(nothingChanged(network.deviceOffline));
    expect(wordsForSave(new ApiError(400, 'Too long.'))).toBe('Too long.');
    expect(wordsForSave(new Error('odd'))).toBe(SOMETHING_WENT_WRONG);
  });
});
