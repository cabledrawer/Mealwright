import { describe, expect, it } from 'vitest';
import { cookTargetOf } from './cookHere';

describe('cookTargetOf (Cook once here…)', () => {
  it('opens Cook once for the meal and item the add answered, with the picked recipe', () => {
    const target = cookTargetOf({ meal_id: 7, item_id: 9 }, '2026-11-05', 3, {
      id: 4,
      name: 'Pongal'
    });
    expect(target?.meal).toMatchObject({ id: 7, date: '2026-11-05', slot_id: 3 });
    expect(target?.item).toMatchObject({
      id: 9,
      kind: 'recipe',
      recipe: { id: 4, name: 'Pongal' }
    });
    expect(target?.meal.items).toEqual([target?.item]);
  });

  it('gives nothing when the answer has no meal or no item', () => {
    expect(
      cookTargetOf({ meal_id: null, item_id: 9 }, '2026-11-05', 3, { id: 4, name: 'P' })
    ).toBeNull();
    expect(
      cookTargetOf({ meal_id: 7, item_id: null }, '2026-11-05', 3, { id: 4, name: 'P' })
    ).toBeNull();
  });
});
