import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api';
import { COULDNT_SAVE, save, useSender, worthRetrying, type Change } from './save';
import { askOnce } from './askOnce.svelte';
import type { Ask } from './client/types';
import { toasts } from './toast.svelte';
import { UNDONE, undoHistory } from './undo.svelte';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

beforeEach(() => {
  undoHistory.clear();
  toasts.dismiss();
});

afterEach(() => useSender(null));

/** A pretend "where does toor dal live" setting, saved through save(). */
function placeChange(
  state: { place: string },
  to: string,
  send: Change<string>['send'],
  withUndo = false
): Change<string> {
  const before = state.place;
  return {
    apply: () => (state.place = to),
    rollback: () => (state.place = before),
    send,
    undo: withUndo
      ? { label: `Toor dal lives in ${to}`, run: () => void (state.place = before) }
      : undefined
  };
}

/** A promise you settle yourself, to look at the screen while a save is on its way. */
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('save', () => {
  it('shows the change at once, before the server answers', async () => {
    const state = { place: 'Cupboard' };
    const reply = deferred<string>();
    const done = save(placeChange(state, 'Fridge', () => reply.promise));
    expect(state.place).toBe('Fridge');
    reply.resolve('ok');
    expect(await done).toEqual({ ok: true, value: 'ok' });
    expect(state.place).toBe('Fridge');
  });

  it('sends a fresh change ID (a UUID) with every change', async () => {
    const ids: string[] = [];
    const send = async (id: string) => {
      ids.push(id);
      return 'ok';
    };
    await save(placeChange({ place: 'Cupboard' }, 'Fridge', send));
    await save(placeChange({ place: 'Cupboard' }, 'Freezer', send));
    expect(ids).toHaveLength(2);
    expect(ids[0]).toMatch(UUID);
    expect(ids[1]).toMatch(UUID);
    expect(ids[0]).not.toBe(ids[1]);
  });

  it('rolls back and says so calmly when it can’t save', async () => {
    const state = { place: 'Cupboard' };
    const result = await save(
      placeChange(state, 'Fridge', () => Promise.reject(new ApiError(0, 'offline')))
    );
    expect(result.ok).toBe(false);
    expect(state.place).toBe('Cupboard');
    expect(toasts.current?.message).toBe(COULDNT_SAVE);
    expect(toasts.current?.tone).toBe('problem');
    expect(toasts.current?.action?.label).toBe('Try again');
  });

  it('Try again sends the same change ID, so the server can ignore a double', async () => {
    const state = { place: 'Cupboard' };
    const ids: string[] = [];
    let fail = true;
    const send = async (id: string) => {
      ids.push(id);
      if (fail) throw new ApiError(503, 'busy');
      return 'ok';
    };
    await save(placeChange(state, 'Fridge', send));
    expect(state.place).toBe('Cupboard');
    fail = false;
    toasts.act();
    expect(state.place).toBe('Fridge'); // shown again at once
    await vi.waitFor(() => expect(ids).toHaveLength(2));
    expect(ids[1]).toBe(ids[0]);
    expect(state.place).toBe('Fridge');
  });

  it("shows the server's reason, without Try again, when it says no", async () => {
    const state = { place: 'Cupboard' };
    await save(
      placeChange(state, 'Fridge', () =>
        Promise.reject(new ApiError(422, 'There’s already an ingredient called Toor dal.'))
      )
    );
    expect(state.place).toBe('Cupboard');
    expect(toasts.current?.message).toBe('There’s already an ingredient called Toor dal.');
    expect(toasts.current?.action).toBeUndefined();
  });

  it('stays quiet when the session has ended (sign in takes over)', async () => {
    await save(
      placeChange({ place: 'Cupboard' }, 'Fridge', () =>
        Promise.reject(new ApiError(401, 'Please sign in.'))
      )
    );
    expect(toasts.current).toBeNull();
  });

  it('knows which problems are worth trying again', () => {
    expect(worthRetrying(new ApiError(0, ''))).toBe(true);
    expect(worthRetrying(new ApiError(500, ''))).toBe(true);
    expect(worthRetrying(new ApiError(429, ''))).toBe(true);
    expect(worthRetrying(new TypeError('Failed to fetch'))).toBe(true);
    expect(worthRetrying(new ApiError(404, ''))).toBe(false);
    expect(worthRetrying(new ApiError(422, ''))).toBe(false);
  });
});

describe('save with Undo', () => {
  it('shows the change with Undo straight away, and Undo takes it back', async () => {
    const state = { place: 'Cupboard' };
    await save(placeChange(state, 'Fridge', async () => 'ok', true));
    expect(toasts.current?.message).toBe('Toor dal lives in Fridge');
    toasts.act();
    await vi.waitFor(() => expect(toasts.current?.message).toBe(UNDONE));
    expect(state.place).toBe('Cupboard');
  });

  it('Undo pressed before the server answers waits for it, then undoes', async () => {
    const state = { place: 'Cupboard' };
    const reply = deferred<string>();
    const undoRan = vi.fn();
    const change = placeChange(state, 'Fridge', () => reply.promise);
    change.undo = { label: 'Moved', run: undoRan };
    void save(change);
    const undone = undoHistory.undoLast();
    expect(undoRan).not.toHaveBeenCalled();
    reply.resolve('saved-id');
    await undone;
    expect(undoRan).toHaveBeenCalledWith('saved-id');
  });

  it('a change that failed to save leaves nothing to undo', async () => {
    await save(
      placeChange({ place: 'Cupboard' }, 'Fridge', () => Promise.reject(new ApiError(0, '')), true)
    );
    expect(undoHistory.size).toBe(0);
  });

  it('Undo pressed before a save that then fails says nothing more', async () => {
    const reply = deferred<string>();
    const change = placeChange({ place: 'Cupboard' }, 'Fridge', () => reply.promise, true);
    void save(change);
    const undone = undoHistory.undoLast();
    reply.reject(new ApiError(0, ''));
    await undone;
    expect(toasts.current?.message).toBe(COULDNT_SAVE);
  });
});

describe('the sender (where the 0.3 offline queue plugs in)', () => {
  it('every change goes out through it, with its ID', async () => {
    const seen: string[] = [];
    useSender(async (change) => {
      seen.push(change.changeId);
      return change.send(change.changeId, change.answers);
    });
    const result = await save(placeChange({ place: 'Cupboard' }, 'Fridge', async () => 'ok'));
    expect(result).toEqual({ ok: true, value: 'ok' });
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatch(UUID);
  });
});

describe('ask once', () => {
  const ask: Ask = {
    food_id: 7,
    food_name: 'Toor dal',
    kind: 'weight_per_ml',
    question: 'About how much does 1 cup of toor dal weigh?',
    unit: 'g',
    per: 'cup',
    cup_ml: 250,
    suggested: 200
  };
  const askError = () =>
    new ApiError(409, ask.question, 'ask_once', { detail: ask.question, code: 'ask_once', ask });

  afterEach(() => askOnce.dismiss());

  it('asks, then sends the same change again, with the same ID and the answer', async () => {
    const calls: { id: string; answers: unknown[] }[] = [];
    const state = { place: 'Cupboard' };
    const done = save(
      placeChange(state, 'Fridge', async (id, answers) => {
        calls.push({ id, answers: [...answers] });
        if (!answers.length) throw askError();
        return 'ok';
      })
    );
    await vi.waitFor(() => expect(askOnce.current?.ask.question).toBe(ask.question));
    expect(state.place).toBe('Fridge'); // still shown while the question is open
    askOnce.answer(180, true);
    expect(await done).toEqual({ ok: true, value: 'ok' });
    expect(calls).toHaveLength(2);
    expect(calls[1]!.id).toBe(calls[0]!.id);
    expect(calls[1]!.answers).toEqual([
      { kind: 'weight_per_ml', food_id: 7, grams: 180, remember: true }
    ]);
  });

  it('puts things back quietly when the person chooses not to answer', async () => {
    const state = { place: 'Cupboard' };
    const done = save(
      placeChange(
        state,
        'Fridge',
        async () => {
          throw askError();
        },
        true
      )
    );
    await vi.waitFor(() => expect(askOnce.current).not.toBeNull());
    askOnce.dismiss();
    const result = await done;
    expect(result).toMatchObject({ ok: false, cancelled: true });
    expect(state.place).toBe('Cupboard');
    expect(undoHistory.size).toBe(0);
    expect(toasts.current).toBeNull();
  });
});

describe('Undo and a question', () => {
  afterEach(() => askOnce.dismiss());

  it('no Undo button while the question is open; it comes back once saved', async () => {
    const ask = {
      food_id: 7,
      food_name: 'Toor dal',
      kind: 'item_weight' as const,
      question: 'About how much does 1 toor dal weigh?',
      suggested: 100
    };
    const change = placeChange({ place: 'Cupboard' }, 'Fridge', async (_id, answers) => {
      if (!answers.length) throw new ApiError(409, ask.question, 'ask_once', { ask });
      return 'Toor dal is now counted by number';
    });
    change.undo = { label: 'Changed', labelFrom: (v) => v, run: () => {} };
    const done = save(change);
    await vi.waitFor(() => expect(askOnce.current).not.toBeNull());
    expect(toasts.current).toBeNull();
    askOnce.answer(100, true);
    await done;
    expect(toasts.current?.message).toBe('Toor dal is now counted by number');
    expect(toasts.current?.action?.label).toBe('Undo');
  });
});

describe("the server's own words", () => {
  it('replace the toast once the server answers', async () => {
    const change = placeChange(
      { place: 'Cupboard' },
      'Fridge',
      async () => 'Moved toor dal → Fridge'
    );
    change.undo = { label: 'Moved', labelFrom: (summary) => summary, run: () => {} };
    await save(change);
    expect(toasts.current?.message).toBe('Moved toor dal → Fridge');
  });

  it('a refusal can be handled by the caller instead of a toast', async () => {
    const change = placeChange({ place: 'Cupboard' }, 'Fridge', () =>
      Promise.reject(new ApiError(409, 'Taken', 'name_taken', { food_id: 3 }))
    );
    const refused = vi.fn(() => true);
    change.refused = refused;
    await save(change);
    expect(refused).toHaveBeenCalledOnce();
    expect(toasts.current).toBeNull();
  });
});

describe('nothing changed', () => {
  it('no Undo when the server says nothing changed', async () => {
    const change = placeChange({ place: 'Cupboard' }, 'Cupboard', async () => 'same');
    change.undo = { label: 'Moved', skip: () => true, run: () => {} };
    await save(change);
    expect(undoHistory.size).toBe(0);
    expect(toasts.current).toBeNull();
  });
});
