import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Stocktake, StocktakePlace, StocktakeRow } from './client/stocktake';

const api = vi.hoisted(() => ({
  getStocktake: vi.fn(),
  getStocktakePlace: vi.fn(),
  answerFood: vi.fn(),
  makeStapleHere: vi.fn(),
  setPackSize: vi.fn(),
  addSomethingElse: vi.fn(),
  finishPlace: vi.fn(),
  restartStocktake: vi.fn()
}));
vi.mock('./client/stocktake', () => api);

import { toasts } from './toast.svelte';
import {
  countOf,
  countWords,
  fractionOf,
  moreOf,
  shareOf,
  StocktakeModel
} from './stocktake.svelte';

const stock = { amount: 0, display: '0 g' };

function row(id: number, name: string, extra: Partial<StocktakeRow> = {}): StocktakeRow {
  return {
    food: { id, name, counted_as: 'weight' },
    staple: false,
    restocked_on: null,
    restocked_days_ago: null,
    added: false,
    answered: false,
    stock,
    pack: {
      id: 1,
      name: 'bag',
      plural: 'bags',
      amount: 1000,
      display: 'Bag = 1 kg',
      usual: true,
      added_when_shopping: false
    },
    pack_suggestions: [],
    answer: null,
    fraction_now: null,
    more_now: 0,
    counted: false,
    count_now: null,
    count_word: null,
    count_word_plural: null,
    ...extra
  };
}

const cupboard = { id: 3, name: 'Cupboard', kind: 'cupboard' as const };
const spices = { id: 4, name: 'Spice rack', kind: 'cupboard' as const };

function place(rows: StocktakeRow[], number = 1): StocktakePlace {
  return {
    place: number === 1 ? cupboard : spices,
    number,
    of: 2,
    finished: false,
    answered: 0,
    total: rows.length,
    previous: number === 1 ? null : cupboard,
    next: number === 1 ? spices : null,
    rows
  };
}

function overview(current: number | null, complete = false): Stocktake {
  return {
    places: [
      { ...cupboard, finished: current !== 3, answered: 0, total: 2 },
      { ...spices, finished: complete, answered: 0, total: 0 }
    ],
    current_place_id: current,
    started: true,
    complete
  };
}

const change = (id: number) => ({
  id,
  kind: 'stocktake',
  at: '2026-11-07T10:00:00Z',
  who: { login_id: 1, name: 'Tess' },
  summary: 'Stocktake: Toor dal ½ bag in the Cupboard',
  can_undo: true,
  undo_until: null,
  undone: null
});

describe('the stocktake', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset();
  });

  it('opens at the first place not finished', async () => {
    api.getStocktake.mockResolvedValue(overview(4));
    api.getStocktakePlace.mockResolvedValue(place([], 2));
    const model = new StocktakeModel();
    await model.open();
    expect(api.getStocktakePlace).toHaveBeenCalledWith(4);
    expect(model.place?.number).toBe(2);
    expect(model.loading).toBe(false);
    expect(model.failed).toBe(false);
  });

  it('opens at the last place when everything is finished', async () => {
    api.getStocktake.mockResolvedValue(overview(null, true));
    api.getStocktakePlace.mockResolvedValue(place([], 2));
    const model = new StocktakeModel();
    await model.open();
    expect(api.getStocktakePlace).toHaveBeenCalledWith(4);
    expect(model.overview?.complete).toBe(true);
  });

  it('says so when the server cannot be reached', async () => {
    api.getStocktake.mockRejectedValue(new Error('down'));
    const model = new StocktakeModel();
    await model.open();
    expect(model.failed).toBe(true);
    expect(model.loading).toBe(false);
  });

  it('shows a pick at once and then the server’s row', async () => {
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValue(place([row(7, 'Toor dal')]));
    const model = new StocktakeModel();
    await model.open();
    let release: (value: unknown) => void = () => {};
    api.answerFood.mockReturnValue(new Promise((resolve) => (release = resolve)));
    const saving = model.pick(7, 'Toor dal', 0.5);
    expect(fractionOf(model.place!.rows[0]!)).toBe(0.5); // before the server has answered
    expect(model.place!.rows[0]!.answered).toBe(true);
    release({
      change: change(11),
      row: row(7, 'Toor dal', {
        answered: true,
        answer: { fraction: '0.5', more: 0, count: null }
      }),
      answered: 1,
      total: 1
    });
    await saving;
    expect(api.answerFood).toHaveBeenCalledWith(
      3,
      7,
      { fraction: 0.5, more: 0 },
      expect.any(String)
    );
    expect(model.place!.answered).toBe(1);
    expect(fractionOf(model.place!.rows[0]!)).toBe(0.5);
  });

  it('puts the row back when the server refuses', async () => {
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValue(place([row(7, 'Toor dal')]));
    const model = new StocktakeModel();
    await model.open();
    api.answerFood.mockRejectedValue(new Error('no'));
    await model.pick(7, 'Toor dal', 1);
    const back = model.place!.rows[0]!;
    expect(back.answered).toBe(false);
    expect(back.answer).toBeNull();
  });

  it('sends the count of an ingredient counted one by one', async () => {
    const eggs = row(8, 'Eggs', { food: { id: 8, name: 'Eggs', counted_as: 'count' }, pack: null });
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValue(place([eggs]));
    const model = new StocktakeModel();
    await model.open();
    api.answerFood.mockResolvedValue({
      change: change(12),
      row: { ...eggs, answered: true, answer: { fraction: null, more: 0, count: '6' } },
      answered: 1,
      total: 1
    });
    await model.count(8, 'Eggs', 6);
    expect(api.answerFood).toHaveBeenCalledWith(3, 8, { count: 6 }, expect.any(String));
    expect(countOf(model.place!.rows[0]!)).toBe(6);
  });

  it('makes a staple and shows it as one', async () => {
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValue(place([row(9, 'Sambar powder')]));
    const model = new StocktakeModel();
    await model.open();
    api.makeStapleHere.mockResolvedValue({
      change: change(13),
      row: row(9, 'Sambar powder', { staple: true, answered: true }),
      answered: 1,
      total: 1
    });
    await model.staple(9, 'Sambar powder');
    expect(model.place!.rows[0]!.staple).toBe(true);
    expect(api.makeStapleHere).toHaveBeenCalledWith(3, 9, expect.any(String));
  });

  it('asks the pack size once and shows it', async () => {
    const tamarind = row(5, 'Tamarind', { pack: null });
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValue(place([tamarind]));
    const model = new StocktakeModel();
    await model.open();
    const choice = {
      pack: null,
      name: 'pack',
      amount: 500,
      display: 'pack · 500 g',
      amount_text: '500 g'
    };
    api.setPackSize.mockResolvedValue({
      change: change(14),
      row: row(5, 'Tamarind', {
        pack: { ...row(5, 'x').pack!, name: 'pack', display: 'Pack = 500 g' }
      }),
      answered: 0,
      total: 1
    });
    await model.size(5, 'Tamarind', { name: 'pack', amount: 500 }, choice);
    expect(api.setPackSize).toHaveBeenCalledWith(
      3,
      5,
      { name: 'pack', amount: 500 },
      expect.any(String)
    );
    expect(model.place!.rows[0]!.pack?.display).toBe('Pack = 500 g');
  });

  it('goes on to the next place once this one is finished', async () => {
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValueOnce(place([row(7, 'Toor dal')]));
    const model = new StocktakeModel();
    await model.open();
    api.finishPlace.mockResolvedValue(overview(4));
    api.getStocktakePlace.mockResolvedValueOnce(place([], 2));
    expect(await model.next()).toBe(true);
    expect(api.finishPlace).toHaveBeenCalledWith(3);
    expect(model.place?.number).toBe(2);
  });

  it('adds something else to the place in A to Z order, once', async () => {
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValue(place([row(7, 'Toor dal'), row(2, 'Atta')]));
    const model = new StocktakeModel();
    await model.open();
    api.addSomethingElse.mockResolvedValue({
      change: null,
      row: row(6, 'Jam', { added: true }),
      answered: 0,
      total: 3
    });
    await model.addHere(6);
    await model.addHere(6);
    expect(model.place!.rows.map((r) => r.food.name)).toEqual(['Atta', 'Jam', 'Toor dal']);
    expect(model.place!.total).toBe(3);
  });

  it('reads the packets there now until an answer says otherwise', () => {
    const there = row(1, 'Dal', { fraction_now: '0.5', more_now: 2 });
    expect([shareOf(there), moreOf(there)]).toEqual([0.5, 2]);
    const said = row(1, 'Dal', {
      fraction_now: '0.5',
      more_now: 2,
      answer: { fraction: '1', more: 0, count: null }
    });
    expect([shareOf(said), moreOf(said)]).toEqual([1, 0]);
    expect(shareOf(row(1, 'Dal'))).toBe(0);
  });

  it('words a count with the ingredient’s own word', () => {
    const tins = row(2, 'Tomatoes', { count_word: 'tin', count_word_plural: 'tins' });
    expect(countWords(tins, 1)).toBe('1\u00a0tin');
    expect(countWords(tins, 2)).toBe('2\u00a0tins');
    expect(countWords(row(3, 'Onion'), 2)).toBe('2');
  });

  it('tells the person when adding, going back or going on cannot be saved', async () => {
    api.getStocktake.mockResolvedValue(overview(3));
    api.getStocktakePlace.mockResolvedValue(place([row(7, 'Toor dal')]));
    const model = new StocktakeModel();
    await model.open();
    const show = vi.spyOn(toasts, 'show');
    api.addSomethingElse.mockRejectedValue(new Error('down'));
    expect(await model.addHere(6)).toBe(false);
    api.getStocktakePlace.mockRejectedValue(new Error('down'));
    expect(await model.goTo(4)).toBe(false);
    api.finishPlace.mockRejectedValue(new Error('down'));
    expect(await model.next()).toBe(false);
    expect(show).toHaveBeenCalledTimes(3);
    expect(show).toHaveBeenCalledWith('Couldn’t save. Try again.', { tone: 'problem' });
    show.mockRestore();
  });
});
