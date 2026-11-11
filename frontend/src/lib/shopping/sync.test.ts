// The sender (sync-protocol 11.3) against a pretend server, one test per case.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { network } from '#lib/network.svelte.js';
import { deviceId, loadDeviceId } from '#lib/offline/device.js';
import { phoneDatabaseName } from '#lib/offline/phone.js';
import { addToQueue, readQueue } from '#lib/offline/store.js';
import { wipeDevice } from '#lib/offline/wipe.js';
import { session } from '#lib/session.svelte.js';
import { ME, fakeShopping, sampleCopy } from '#lib/testing/fakeShopping.js';
import { dropPhone, freshPhone } from '#lib/testing/phone.js';
import { toasts } from '#lib/toast.svelte.js';
import { makeAction, type Action } from './actions';
import { COULDNT_SEND, retryDelay, sendAction, shoppingSync, TIMING } from './sync.svelte';

interface Sent {
  path: string;
  body: { protocol: number; login_id: number; device_id: string; since: number; actions: Action[] };
  queuedFirst: number;
}

/** A pretend server: `reply` answers each batch (status and body, or never). */
function server(reply: (sent: Sent, n: number) => [number, unknown] | 'hang' | 'drop') {
  const sent: Sent[] = [];
  vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
    const path = String(input).replace(/^\/api\/v1/, '');
    if (!path.startsWith('/shopping/actions')) {
      return new Response(JSON.stringify({ detail: 'no' }), { status: 404 });
    }
    const one: Sent = {
      path,
      body: JSON.parse(String(init.body)),
      queuedFirst: (await readQueue()).length
    };
    sent.push(one);
    const answer = reply(one, sent.length);
    if (answer === 'drop') throw new TypeError('Failed to fetch');
    if (answer === 'hang') {
      return new Promise<Response>((_, reject) =>
        init.signal?.addEventListener('abort', () => reject(new DOMException('', 'TimeoutError')))
      );
    }
    return new Response(JSON.stringify(answer[1]), { status: answer[0] });
  });
  return sent;
}

const applied = (sent: Sent): [number, unknown] => [
  200,
  {
    results: sent.body.actions.map((a, i) => ({ id: a.id, seq: 41 + i, status: 'applied' })),
    changes: { ...sampleCopy(), cursor: 41 + sent.body.actions.length, reset: false }
  }
];

const tick = (item: string) => makeAction({ kind: 'tick', item_id: item });

beforeEach(() => {
  freshPhone();
  shoppingSync.timing = {
    ...TIMING,
    retries: [20, 40, 80, 160, 300, 600],
    gatherMs: 0,
    random: () => 0.5
  };
  session.me = { ...ME };
  network.reset();
  toasts.dismiss();
});

afterEach(async () => {
  await dropPhone();
  vi.unstubAllGlobals();
  network.reset();
});

describe('the queue comes first', () => {
  it('stores a change on the phone before sending it', async () => {
    const sent = server(applied);
    await sendAction(tick('i-onions'));
    expect(sent[0]!.queuedFirst).toBe(1);
    expect(await readQueue()).toEqual([]);
  });

  it('sends the envelope of sync-protocol 4.1, protocol 1', async () => {
    const sent = server(applied);
    await sendAction(tick('i-onions'));
    expect(sent[0]!.body).toMatchObject({ protocol: 1, login_id: ME.id, since: 0 });
    expect(sent[0]!.body.device_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('counts waiting changes of the signed-in login for the bar', async () => {
    server(() => 'drop');
    void sendAction(tick('a'));
    void sendAction(tick('b'));
    await vi.waitFor(() => expect(network.waiting).toBe(2));
    expect(shoppingSync.waiting).toBe(2);
  });
});

describe('batches', () => {
  it('gathers what is made within 250 ms into one batch, in order', async () => {
    shoppingSync.timing.gatherMs = 250;
    const sent = server(applied);
    const a = tick('a');
    const b = tick('b');
    const c = tick('c');
    await Promise.all([sendAction(a), sendAction(b), sendAction(c)]);
    expect(sent).toHaveLength(1);
    expect(sent[0]!.body.actions.map((x) => x.id)).toEqual([a.id, b.id, c.id]);
  });

  it('sends at most 100 changes in a batch, oldest first, one batch at a time', async () => {
    // Each batch is held in flight for a while before it's answered, and more triggers come
    // while it is: none of them may start a second batch alongside.
    let inFlight = 0;
    let most = 0;
    const sent: Sent['body'][] = [];
    vi.stubGlobal('fetch', async (_input: string, init: RequestInit = {}) => {
      const body = JSON.parse(String(init.body)) as Sent['body'];
      sent.push(body);
      inFlight++;
      most = Math.max(most, inFlight);
      await new Promise((r) => setTimeout(r, 60));
      inFlight--;
      const [status, answer] = applied({ path: '', body, queuedFirst: 0 });
      return new Response(JSON.stringify(answer), { status });
    });
    // 150 changes waiting on the phone (made offline), then triggers.
    const actions = Array.from({ length: 150 }, (_, i) => tick(`i${i}`));
    for (const a of actions) await addToQueue(a, ME.id, deviceId());
    const first = shoppingSync.send();
    await vi.waitFor(() => expect(inFlight).toBe(1));
    const more = [shoppingSync.send(), shoppingSync.tryAgain(), shoppingSync.send()];
    await Promise.all([first, ...more]);
    await vi.waitFor(() => expect(shoppingSync.queue).toHaveLength(0));
    expect(sent.map((s) => s.actions.length)).toEqual([100, 50]);
    expect(sent.flatMap((s) => s.actions.map((a) => a.id))).toEqual(actions.map((a) => a.id));
    expect(most).toBe(1);
  });

  it('never sends another login’s waiting changes', async () => {
    // Alex's change is waiting on this phone; her session ran out and cabledrawer signed in.
    await addToQueue(tick('alex'), 5, deviceId());
    const sent = server(applied);
    await sendAction(tick('tess'));
    for (const s of sent) expect(s.body.login_id).toBe(ME.id);
    expect(
      sent.flatMap((s) => s.body.actions.map((a) => (a as { item_id?: string }).item_id))
    ).toEqual(['tess']);
    expect(shoppingSync.queue.map((e) => e.login_id)).toEqual([5]);
    expect(shoppingSync.waiting).toBe(0);
  });
});

describe('no answer: the same batch again, later', () => {
  it('waits 2, 4, 8, 16, 30 s, then every 60 s, each ±20%', () => {
    const at = (random: number) =>
      Array.from({ length: 8 }, (_, n) => retryDelay(n, { ...TIMING, random: () => random }));
    expect(at(0.5)).toEqual([2000, 4000, 8000, 16000, 30000, 60000, 60000, 60000]);
    expect(at(0)).toEqual([1600, 3200, 6400, 12800, 24000, 48000, 48000, 48000]);
    expect(at(1)).toEqual([2400, 4800, 9600, 19200, 36000, 72000, 72000, 72000]);
  });

  it.each([
    ['a network error', 'drop' as const],
    ['a 500', [500, { detail: 'oops' }] as [number, unknown]],
    ['a 502 from the proxy', [502, null] as [number, unknown]],
    ['a 503 from the proxy', [503, null] as [number, unknown]],
    ['a 504 from the proxy', [504, null] as [number, unknown]]
  ])('after %s, sends the same batch again', async (_, failure) => {
    shoppingSync.timing.retries = [300];
    const sent = server((one, n) => (n <= 2 ? failure : applied(one)));
    const a = tick('a');
    const result = sendAction(a);
    await vi.waitFor(() => expect(sent).toHaveLength(1));
    // Made while the first batch waits: it goes in a later batch, not this one.
    const b = tick('b');
    void sendAction(b);
    await result;
    expect(sent.slice(0, 3).map((s) => s.body.actions.map((x) => x.id))).toEqual([
      [a.id],
      [a.id],
      [a.id]
    ]);
    await vi.waitFor(() => expect(sent.at(-1)!.body.actions.map((x) => x.id)).toEqual([b.id]));
  });

  it('after 15 s with no answer, sends the same batch again', async () => {
    shoppingSync.timing.timeoutMs = 50;
    const sent = server((one, n) => (n === 1 ? 'hang' : applied(one)));
    const a = tick('a');
    await sendAction(a);
    expect(sent.map((s) => s.body.actions[0]!.id)).toEqual([a.id, a.id]);
    expect(TIMING.timeoutMs).toBe(15_000);
  });

  it('a trigger sends at once instead of waiting for the timer', async () => {
    shoppingSync.timing.retries = [60_000];
    const sent = server((one, n) => (n === 1 ? 'drop' : applied(one)));
    const done = sendAction(tick('a'));
    await vi.waitFor(() => expect(sent).toHaveLength(1));
    const stop = shoppingSync.watch();
    window.dispatchEvent(new Event('online'));
    await done;
    expect(sent).toHaveLength(2);
    stop();
  });

  it('a failure never rolls the change back: it stays waiting', async () => {
    server(() => 'drop');
    const outcome = vi.fn();
    sendAction(tick('a')).then(outcome, outcome);
    await vi.waitFor(() => expect(shoppingSync.queue).toHaveLength(1));
    await new Promise((r) => setTimeout(r, 100));
    expect(outcome).not.toHaveBeenCalled();
    expect(await readQueue()).toHaveLength(1);
  });
});

describe('starting on a weak signal (cabledrawer 20 Oct, hand test)', () => {
  it('start() reads the phone and starts sending what is waiting, without waiting for the answer (11.6)', async () => {
    shoppingSync.timing.timeoutMs = 200;
    const sent = server(() => 'hang');
    shoppingSync.forget();
    const waiting = tick('a');
    await addToQueue(waiting, ME.id, await loadDeviceId());
    const started = performance.now();
    await shoppingSync.start();
    expect(performance.now() - started).toBeLessThan(150);
    // Read from the phone, so it shows on top of the copy at once, and on its way.
    expect(shoppingSync.waitingActions.map((a) => a.id)).toEqual([waiting.id]);
    await vi.waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]!.body.actions.map((a) => a.id)).toEqual([waiting.id]);
    shoppingSync.forget();
  });

  it('triggers that come before a turn of sending has started share it: a hanging signal is waited for once', async () => {
    shoppingSync.timing.timeoutMs = 50;
    shoppingSync.timing.retries = [60_000];
    const sent = server((one, n) => (n <= 2 ? 'hang' : applied(one)));
    shoppingSync.forget();
    const waiting = tick('a');
    await addToQueue(waiting, ME.id, await loadDeviceId());
    await shoppingSync.start();
    await vi.waitFor(() => expect(sent).toHaveLength(1));
    // Two triggers while the first batch hangs (the app opening, the stream's hello): one turn.
    await Promise.all([shoppingSync.send(), shoppingSync.send()]);
    expect(sent).toHaveLength(2);
    // The next trigger gets through: the same change, by the same ID, applied once.
    await shoppingSync.send();
    expect(sent).toHaveLength(3);
    expect(sent.map((one) => one.body.actions.map((a) => a.id))).toEqual([
      [waiting.id],
      [waiting.id],
      [waiting.id]
    ]);
    expect(await readQueue()).toEqual([]);
    expect(shoppingSync.queue).toEqual([]);
    shoppingSync.forget();
  });

  it('a change is queued as whoever made it, even if the app turns to another login while it’s stored (11.4)', async () => {
    server(() => 'hang');
    const me = session.me;
    let queued!: () => void;
    const stored = new Promise<void>((done) => (queued = done));
    void shoppingSync.enqueue(tick('a'), queued).catch(() => {});
    // A late answer at the start turns the app away to sign in, mid-store.
    session.me = null;
    await stored;
    session.me = me;
    expect((await readQueue()).map((e) => e.login_id)).toEqual([ME.id]);
    shoppingSync.forget();
  });
});

describe('the server says no to the whole batch', () => {
  it('401: stops sending and keeps the queue', async () => {
    const sent = server(() => [401, { detail: 'Please sign in again.' }]);
    void sendAction(tick('a'));
    await vi.waitFor(() => expect(shoppingSync.stopped).toBe('signed_out'));
    await shoppingSync.send();
    expect(sent).toHaveLength(1);
    expect(await readQueue()).toHaveLength(1);
  });

  it('SY-62 (frontend half): signing back in as the same login sends at once, same device', async () => {
    let signedIn = false;
    const sent = server((one) => (signedIn ? applied(one) : [401, { detail: 'Sign in again.' }]));
    void sendAction(tick('a'));
    await vi.waitFor(() => expect(shoppingSync.stopped).toBe('signed_out'));
    const device = deviceId();
    // The same login signs back in: the app starts again (the device ID is kept).
    signedIn = true;
    await shoppingSync.start();
    await vi.waitFor(() => expect(shoppingSync.queue).toHaveLength(0));
    expect(sent).toHaveLength(2);
    expect(sent[1]!.body).toMatchObject({ device_id: device, login_id: ME.id });
    expect(sent[1]!.body.actions.map((a) => a.id)).toEqual(sent[0]!.body.actions.map((a) => a.id));
  });

  it('409 other_login: doesn’t send', async () => {
    const sent = server(() => [409, { code: 'other_login', detail: 'Another login.' }]);
    void sendAction(tick('a'));
    await vi.waitFor(() => expect(shoppingSync.stopped).toBe('other_login'));
    await shoppingSync.send();
    expect(sent).toHaveLength(1);
    expect(await readQueue()).toHaveLength(1);
  });

  it('413: halves the batch and carries on', async () => {
    const sent = server((one) =>
      one.body.actions.length > 3 ? [413, { code: 'too_many' }] : applied(one)
    );
    shoppingSync.timing.gatherMs = 250; // the app's own window: 20 ms was too short under load (all six must land in one batch)
    const actions = Array.from({ length: 6 }, (_, i) => tick(`i${i}`));
    await Promise.all(actions.map((a) => sendAction(a)));
    expect(sent.map((s) => s.body.actions.length)).toEqual([6, 3, 3]);
    expect(sent.slice(1).flatMap((s) => s.body.actions.map((a) => a.id))).toEqual(
      actions.map((a) => a.id)
    );
  });

  it('422: stops, keeps the queue, and says so with Try now', async () => {
    let fixed = false;
    const sent = server((one) => (fixed ? applied(one) : [422, { detail: 'bad' }]));
    const done = sendAction(tick('a'));
    await vi.waitFor(() => expect(shoppingSync.stopped).toBe('refused'));
    const toast = toasts.current;
    expect(toast?.message).toBe(COULDNT_SEND);
    expect(toast?.tone).toBe('problem');
    expect(toast?.action?.label).toBe('Try now');
    await shoppingSync.send();
    expect(sent).toHaveLength(1); // stopped: no more tries by itself
    fixed = true;
    toast!.action!.run();
    await done;
    expect(sent).toHaveLength(2);
    expect(await readQueue()).toEqual([]);
  });
});

describe('answers to each change', () => {
  it('a refused change rejects; the others go through', async () => {
    server((one) => [
      200,
      {
        results: one.body.actions.map((a, i) =>
          i === 0
            ? { id: a.id, status: 'refused', reason: 'bad_action', message: 'Not that.' }
            : { id: a.id, status: 'applied' }
        )
      }
    ]);
    shoppingSync.timing.gatherMs = 250; // both must land in one batch: 20 ms was too short under load
    const [bad, good] = await Promise.allSettled([sendAction(tick('a')), sendAction(tick('b'))]);
    expect(bad.status).toBe('rejected');
    expect(good.status).toBe('fulfilled');
    expect(await readQueue()).toEqual([]);
  });

  it('keeps the copy the server sends, on the phone', async () => {
    server(applied);
    await sendAction(tick('a'));
    expect(shoppingSync.copy?.cursor).toBe(42);
    shoppingSync.forget();
    await shoppingSync.open();
    expect(shoppingSync.copy?.cursor).toBe(42);
    expect(shoppingSync.copy?.items.length).toBe(sampleCopy().items.length);
  });
});

describe('changes sent from an earlier visit (after a reload)', () => {
  /** A change left on the phone by an earlier visit: nobody on this page is waiting for it. */
  async function leftFromEarlier(result: Record<string, unknown>) {
    server((one) => [
      200,
      { results: one.body.actions.map((a) => ({ id: a.id, seq: 41, ...result })) }
    ]);
    shoppingSync.forget();
    await addToQueue(tick('a'), ME.id, await loadDeviceId());
    const shown = vi.spyOn(toasts, 'show');
    await shoppingSync.start();
    await vi.waitFor(async () => expect(await readQueue()).toEqual([]));
    shoppingSync.forget();
    return shown;
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('a first answer with a message says it', async () => {
    const shown = await leftFromEarlier({
      status: 'ignored',
      message: 'Alex had removed this.',
      repeat: false
    });
    expect(shown).toHaveBeenCalledWith('Alex had removed this.');
  });

  it('an answer marked repeat: true doesn’t say it again (F67)', async () => {
    const shown = await leftFromEarlier({
      status: 'ignored',
      message: 'Alex had removed this.',
      repeat: true
    });
    expect(shown).not.toHaveBeenCalled();
  });

  it('nor does a repeated refusal', async () => {
    const shown = await leftFromEarlier({
      status: 'refused',
      reason: 'bad_action',
      message: 'Not that.',
      repeat: true
    });
    expect(shown).not.toHaveBeenCalled();
  });
});

describe('a reset (FE-7)', () => {
  it('replaces the copy, keeps the queue and sends it afterwards, in order', async () => {
    // A was synced with an older server at cursor 90, and holds 2 waiting changes.
    const restored = sampleCopy();
    const fake = fakeShopping(restored);
    await shoppingSync.refresh();
    const before = shoppingSync.copy!;
    expect(before.cursor).toBe(40);
    vi.unstubAllGlobals();
    server(() => 'drop');
    const tickOnions = makeAction({ kind: 'tick', item_id: 'i-onions' });
    const removeMilk = makeAction({ kind: 'delete', item_id: 'i-milk' });
    void sendAction(tickOnions);
    void sendAction(removeMilk);
    await vi.waitFor(() => expect(shoppingSync.queue).toHaveLength(2));
    // Back on the restored server, which knows nothing past 40 and answers with a reset.
    vi.unstubAllGlobals();
    const again = fakeShopping(restored, {
      'GET /shopping/changes': () => [
        200,
        { ...structuredClone(restored), reset: true, items: restored.items }
      ]
    });
    await shoppingSync.refresh();
    expect(shoppingSync.copy).not.toBe(before);
    await vi.waitFor(() => expect(shoppingSync.queue).toEqual([]));
    expect(again.actions.map((a) => a.id)).toEqual([tickOnions.id, removeMilk.id]);
    expect(fake.actions).toEqual([]);
    const onions = shoppingSync.copy!.items.find((i) => i.id === 'i-onions');
    expect(onions?.ticks.some((t) => t.standing)).toBe(true);
    expect(shoppingSync.copy!.items.some((i) => i.id === 'i-milk')).toBe(false);
  });
});

describe('signing out (sync-protocol 12): a wiped phone stays wiped', () => {
  const exists = async () =>
    (await indexedDB.databases()).some((db) => db.name === phoneDatabaseName());

  it('an answer that comes after the wipe writes nothing back', async () => {
    let answer: (value: [number, unknown]) => void = () => undefined;
    let asked: Sent | undefined;
    vi.stubGlobal('fetch', async (_input: string, init: RequestInit = {}) => {
      asked = { path: '', body: JSON.parse(String(init.body)), queuedFirst: 0 };
      const [status, body] = await new Promise<[number, unknown]>((done) => (answer = done));
      return new Response(JSON.stringify(body), { status });
    });
    void sendAction(tick('i-onions')).catch(() => undefined);
    await vi.waitFor(() => expect(asked).toBeDefined());
    await wipeDevice();
    expect(await exists()).toBe(false);
    answer(applied(asked!));
    await new Promise((done) => setTimeout(done, 50));
    expect(await exists()).toBe(false);
    expect(shoppingSync.copy).toBeNull();
    expect(network.waiting).toBe(0);
  });

  it('with nobody signed in, sending and loading never make a new database', async () => {
    const sent = server(applied);
    await wipeDevice();
    session.me = null;
    await shoppingSync.start();
    await shoppingSync.send();
    await expect(shoppingSync.refresh()).rejects.toThrow('Please sign in again.');
    await expect(sendAction(tick('i-onions'))).rejects.toThrow('Please sign in again.');
    expect(sent).toEqual([]);
    expect(await exists()).toBe(false);
  });
});
