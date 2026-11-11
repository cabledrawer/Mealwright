// "Who's this?" on a shared login (0.9 A1): asked when nobody is picked, not for an hour after
// "Just looking", and again after 30 minutes without use (the old pick cleared first).

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { session } from './session.svelte';
import { fakeApi, type FakeRequest } from './testing/fakeApi';
import { IDLE_MS, LOOKING_MS, whosThis } from './whosThis.svelte';

const PEOPLE = [
  { id: 1, name: 'Tess', colour: null },
  { id: 3, name: 'Joss', colour: 'amber' }
];

describe('whosThis', () => {
  let now = 1_000_000;
  let requests: FakeRequest[] = [];
  let picked: number | null = null;
  let ask = true;

  function serve() {
    requests = fakeApi({
      'GET /whos-this': () => [200, { ask, picked, people: PEOPLE }],
      'PUT /whos-this': (r) => {
        picked = (r.body as { member_id: number | null }).member_id;
        return [200, { ask, picked, people: PEOPLE }];
      }
    });
  }

  beforeEach(() => {
    try {
      localStorage.clear();
    } catch {
      // nothing stored
    }
    now = 1_000_000;
    picked = null;
    ask = true;
    session.me = {
      id: 9,
      name: 'Kitchen tablet',
      username: 'tablet',
      role: 'member',
      theme: 'auto',
      member_id: 9,
      shared: true
    };
    whosThis.forget();
    whosThis.useClock(() => now);
    serve();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    session.me = null;
    whosThis.forget();
  });

  it('asks on a shared login when nobody is picked', async () => {
    await whosThis.check();
    expect(whosThis.open).toBe(true);
    expect(whosThis.people.map((p) => p.name)).toEqual(['Tess', 'Joss']);
  });

  it('does not ask when someone is picked, or when the household switch is off', async () => {
    picked = 3;
    await whosThis.check();
    expect(whosThis.open).toBe(false);
    picked = null;
    ask = false;
    await whosThis.check();
    expect(whosThis.open).toBe(false);
  });

  it('never asks, nor asks the server, on a login that is not shared', async () => {
    session.me = { ...session.me!, shared: false };
    await whosThis.check();
    now += IDLE_MS * 2;
    whosThis.used();
    expect(whosThis.open).toBe(false);
    expect(requests).toEqual([]);
  });

  it('picks someone and closes', async () => {
    await whosThis.check();
    await whosThis.pick(3);
    expect(whosThis.open).toBe(false);
    expect(requests.at(-1)).toMatchObject({ method: 'PUT', body: { member_id: 3 } });
  });

  it('"Just looking" picks nobody and does not ask again for an hour', async () => {
    await whosThis.check();
    await whosThis.pick(null);
    expect(requests.at(-1)).toMatchObject({ method: 'PUT', body: { member_id: null } });
    now += LOOKING_MS - 1;
    await whosThis.check();
    expect(whosThis.open).toBe(false);
    now += 1;
    await whosThis.check();
    expect(whosThis.open).toBe(true);
  });

  it('after 30 minutes without use, clears the pick and asks again', async () => {
    await whosThis.check();
    await whosThis.pick(3);
    now += IDLE_MS - 1;
    whosThis.used();
    await vi.waitFor(() => expect(requests.length).toBe(2));
    expect(whosThis.open).toBe(false);
    now += IDLE_MS;
    whosThis.used();
    await vi.waitFor(() => expect(whosThis.open).toBe(true));
    const puts = requests.filter((r) => r.method === 'PUT');
    expect(puts.at(-1)!.body).toEqual({ member_id: null });
  });

  it('says so when the pick could not be sent, and stays open', async () => {
    await whosThis.check();
    fakeApi({ 'PUT /whos-this': [500, { detail: 'Boom' }] });
    await whosThis.pick(3);
    expect(whosThis.open).toBe(true);
    expect(whosThis.problem).toBe('Something went wrong. Try again.');
  });
});
