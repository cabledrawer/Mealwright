// Import from Mealie's words (words.md section 81): counts, the file line, what is left out,
// the Undo line and what Undo took out, and the lines a recipe couldn't read.

import { describe, expect, it } from 'vitest';
import type { MealieImport } from './client/mealie';
import { stepOf } from './mealieFlow.svelte';
import {
  bringInWords,
  broughtInWords,
  chosenCount,
  fileWords,
  fromFileWords,
  newIngredientsWords,
  alreadyWords,
  notBroughtIn,
  noteCheckWords,
  noteWords,
  photosWords,
  resultWords,
  saveAllWords,
  showingWords,
  tooManyIngredientsWords,
  undoWords,
  undoneWords,
  unreadWords
} from './mealieWords';

const NBSP = ' ';

const counts = (over: Partial<MealieImport['counts']> = {}) => ({
  counts: { saved: 171, drafts: 31, already: 12, skipped: 0, new_foods: 85, ...over }
});

describe('Import from Mealie words', () => {
  it('counts recipes and lines, one and many', () => {
    expect(bringInWords(202)).toBe('Bring in 202 recipes');
    expect(bringInWords(1)).toBe('Bring in 1 recipe');
    expect(broughtInWords(counts())).toBe('202 recipes brought in');
    expect(saveAllWords(31)).toBe('Save all 31 as they are');
    expect(saveAllWords()).toBe('Save all as they are');
    expect(noteWords(202)).toBe('202 recipes brought in from Mealie');
    expect(noteCheckWords(31)).toBe('31 have lines to check');
    expect(noteCheckWords(1)).toBe('1 has lines to check');
  });

  it('says what the file holds that is never brought in, leaving out what it hasn’t', () => {
    expect(notBroughtIn({ meal_plans: 6, shopping_lists: 2, users: 3, cookbooks: 4 })).toBe(
      'Not brought in: 6 meal plans, 2 shopping lists, 3 users, 4 cookbooks.'
    );
    expect(notBroughtIn({ users: 1, cookbooks: 0 })).toBe('Not brought in: 1 user.');
    expect(notBroughtIn({})).toBeNull();
  });

  it('says the file’s size and the photos’ size', () => {
    expect(fileWords({ file_bytes: 48_000_000 })).toBe(`48.0${NBSP}MB · read just now`);
    expect(fileWords({ file_bytes: null })).toBe('Read just now');
    expect(photosWords({ photo_bytes: 41_200_000 })).toBe(
      `About 41.2${NBSP}MB more on your server`
    );
    // Never "About 300 KB": a few small photos are about a megabyte.
    expect(photosWords({ photo_bytes: 300_000 })).toBe(`About 1.0${NBSP}MB more on your server`);
  });

  it('says where it came from and when, mid-sentence', () => {
    const now = new Date(2026, 10, 13, 22, 0);
    const finished = new Date(2026, 10, 13, 21, 40).toISOString();
    expect(fromFileWords({ file_name: 'mealie_2026.11.10.zip', finished_at: finished }, now)).toBe(
      'From mealie_2026.11.10.zip, today 21:40'
    );
  });

  it('says what Undo takes out and what it took out', () => {
    expect(undoWords(counts())).toBe(
      'Takes out the 202 recipes and the 85 new ingredients. Works for 7 days; recipes you’ve changed or cooked since are kept.'
    );
    expect(undoWords(counts({ new_foods: 0, saved: 1, drafts: 0 }))).toBe(
      'Takes out the 1 recipe. Works for 7 days; recipes you’ve changed or cooked since are kept.'
    );
    expect(undoneWords({ recipes: 150, drafts: 21, foods: 85, kept: 3 })).toBe(
      'Took out 171 recipes and 85 ingredients; kept 3 you’d changed or cooked.'
    );
    expect(undoneWords({ recipes: 1, drafts: 0, foods: 0, kept: 0 })).toBe('Took out 1 recipe.');
  });

  it('quotes the lines it couldn’t read: the phone adds …, the computer how many more', () => {
    expect(unreadWords(['1 tin coconut milk (optional)', 'salt to taste'], 2)).toBe(
      '“1 tin coconut milk (optional)”, “salt to taste”'
    );
    expect(unreadWords(['2 tins tomatoes or 6 fresh', 'a', 'b'], 3, false, 1)).toBe(
      '“2 tins tomatoes or 6 fresh”, …'
    );
    expect(unreadWords(['levain (see note)', 'a', 'b'], 4, true, 1)).toBe(
      '“levain (see note)”, and 3 more'
    );
  });

  it('lists the new ingredients under See, and how many more the preview left off', () => {
    expect(newIngredientsWords(['Asafoetida', 'Tamarind'], 2)).toBe('Asafoetida, Tamarind');
    expect(newIngredientsWords(['Asafoetida', 'Tamarind'], 207)).toBe(
      'Asafoetida, Tamarind and 205 more'
    );
  });

  it('lists at most 200 recipes under See which, then how many more', () => {
    expect(alreadyWords(["Sam's dal", "Lorna's soup"])).toBe("Sam's dal, Lorna's soup");
    const names = Array.from({ length: 212 }, (_, i) => `Noor's dish ${i}`);
    const words = alreadyWords(names);
    expect(words.endsWith("Noor's dish 199 and 12 more")).toBe(true);
    expect(words).not.toContain("Noor's dish 200");
  });

  it('says when a file has more new ingredients than one import adds', () => {
    expect(tooManyIngredientsWords({ foods_new: 85 })).toBeNull();
    expect(tooManyIngredientsWords({ foods_new: 85, foods_left_out: 0 })).toBeNull();
    expect(tooManyIngredientsWords({ foods_new: 6240, foods_left_out: 1240 })).toBe(
      'Only the first 5,000 new ingredients are added. Recipes that use the other 1,240 wait in Drafts for you to check.'
    );
  });

  it('says how each recipe went while it runs', () => {
    expect(resultWords({ state: 'saved', unread_count: 0 })).toBe('Ready');
    expect(resultWords({ state: 'draft', unread_count: 2 })).toBe('2 lines to check');
    expect(resultWords({ state: 'draft', unread_count: 1 })).toBe('1 line to check');
    expect(resultWords({ state: 'already', unread_count: 0 })).toBe('You already have it');
    expect(showingWords(8, 214)).toBe('Showing 8 of 214. Untick any you don’t want.');
  });

  it('counts the recipes Bring in brings in, after the ones unticked', () => {
    const preview = {
      new: 2,
      already: 1,
      with_photo: 0,
      photo_bytes: 0,
      foods_matching: 0,
      foods_new: 0,
      left_out: {},
      recipes: [
        { key: 'a', name: 'Dal', tags: [], photo: false, already: false },
        { key: 'b', name: 'Soup', tags: [], photo: false, already: false },
        { key: 'c', name: 'Curry', tags: [], photo: false, already: true }
      ]
    };
    expect(chosenCount(preview, new Set())).toBe(2);
    expect(chosenCount(preview, new Set(['b']))).toBe(1);
    // Once started the list is gone: the preview's own count.
    expect(chosenCount({ ...preview, recipes: [] }, new Set(['b']))).toBe(2);
  });

  it('shows Done while Undo works, then starts again', () => {
    const now = Date.parse('2026-11-14T12:00:00Z');
    const job = (state: MealieImport['state'], undo_until: string | null) =>
      ({ state, undo_until }) as MealieImport;
    expect(stepOf(null, now)).toBe('start');
    expect(stepOf(job('ready', null), now)).toBe('preview');
    expect(stepOf(job('running', null), now)).toBe('running');
    expect(stepOf(job('done', '2026-11-20T12:00:00Z'), now)).toBe('done');
    expect(stepOf(job('failed', '2026-11-20T12:00:00Z'), now)).toBe('done');
    expect(stepOf(job('done', '2026-11-13T12:00:00Z'), now)).toBe('start');
    expect(stepOf(job('undone', null), now)).toBe('start');
  });
});
