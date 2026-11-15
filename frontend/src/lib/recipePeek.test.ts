import { afterEach, describe, expect, it } from 'vitest';
import { sessionEnded } from './api';
import type { RecipeRow } from './client/recipes';
import { runWipeHooks } from './offline/wipeHooks';
import { recipePeek } from './recipePeek';

const row = (id: number, name: string) => ({ id, name }) as unknown as RecipeRow;

afterEach(() => recipePeek.forget());

describe('the recipe row held for the next page', () => {
  it('is given only for its own recipe', () => {
    recipePeek.hold(row(123, 'Sam’s dal'));
    expect(recipePeek.of(123)?.name).toBe('Sam’s dal');
    expect(recipePeek.of(124)).toBeNull();
  });

  it('is forgotten when the browser is wiped at sign-out', () => {
    recipePeek.hold(row(123, 'Sam’s dal'));
    runWipeHooks();
    expect(recipePeek.of(123)).toBeNull();
  });

  it('is forgotten when the session ends (a 401, or the live stream says signed out)', () => {
    recipePeek.hold(row(123, 'Sam’s dal'));
    sessionEnded();
    expect(recipePeek.of(123)).toBeNull();
  });
});
