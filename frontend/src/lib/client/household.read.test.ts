import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { changePints, getHousehold } from './household';
import { askServer } from '../offline/opening';
import { runWipeHooks } from '../offline/wipeHooks';
import { sessionEnded } from '../api';

type Wait = { url: string; method: string; answer: (body: unknown, status?: number) => void };

/** A fetch that answers only when the test says so, and remembers what was asked and when. */
function slowServer() {
  const asked: Wait[] = [];
  const fetch = (url: RequestInfo | URL, init?: RequestInit) =>
    new Promise<Response>((done) => {
      asked.push({
        url: String(url),
        method: init?.method ?? 'GET',
        answer: (body, status = 200) => done(new Response(JSON.stringify(body), { status }))
      });
    });
  return { asked, fetch: fetch as typeof globalThis.fetch };
}

const settle = () => new Promise((done) => setTimeout(done, 0));

describe('reading the household', () => {
  let server: ReturnType<typeof slowServer>;
  beforeEach(() => {
    server = slowServer();
    vi.stubGlobal('fetch', server.fetch);
  });
  afterEach(() => vi.unstubAllGlobals());

  it('asks the server once when several screens ask at the same moment', async () => {
    const first = getHousehold();
    const second = getHousehold();
    const third = getHousehold();
    await settle();
    expect(server.asked.filter((a) => a.url.endsWith('/household'))).toHaveLength(1);
    server.asked[0]!.answer({ today: '2026-11-15' });
    expect((await first).today).toBe('2026-11-15');
    expect(await second).toBe(await third);
  });

  it('asks again for a read made after the last one finished', async () => {
    const first = getHousehold();
    await settle();
    server.asked[0]!.answer({ today: 'a' });
    await first;
    const later = getHousehold();
    await settle();
    expect(server.asked).toHaveLength(2);
    server.asked[1]!.answer({ today: 'b' });
    expect((await later).today).toBe('b');
  });

  it('never hands a read that began before a change to a read made after it', async () => {
    const before = getHousehold();
    await settle();
    const change = changePints('us');
    const after = getHousehold();
    await settle();
    const reads = server.asked.filter((a) => a.method === 'GET');
    expect(reads).toHaveLength(2); // the one made after the change is its own question
    server.asked.find((a) => a.method === 'PATCH')!.answer({ pints: 'us' });
    reads[0]!.answer({ pints: 'uk' });
    reads[1]!.answer({ pints: 'us' });
    await change;
    expect(((await before) as { pints: string }).pints).toBe('uk');
    expect(((await after) as { pints: string }).pints).toBe('us');
  });

  it('does not hand a read that began before a wipe, or a session end, to someone who asks after', async () => {
    for (const forget of [runWipeHooks, sessionEnded]) {
      server.asked.length = 0;
      const before = getHousehold();
      await settle();
      forget();
      const after = getHousehold();
      await settle();
      const reads = server.asked.filter((a) => a.method === 'GET');
      expect(reads).toHaveLength(2); // asked afresh, not joined to the first person's question
      reads[0]!.answer({ name: 'Sam’s household' });
      reads[1]!.answer({ name: 'Lorna’s household' });
      expect(((await before) as { name: string }).name).toBe('Sam’s household');
      expect(((await after) as { name: string }).name).toBe('Lorna’s household');
    }
  });
});

describe('the start asking the server', () => {
  it('asks who is signed in without waiting for the answer about setup', async () => {
    const server = slowServer();
    const answer = askServer(server.fetch);
    await settle();
    expect(server.asked.map((a) => a.url.replace(/.*\/api\/v1/, ''))).toEqual(['/setup', '/me']);
    server.asked[0]!.answer({ needs_setup: false });
    server.asked[1]!.answer({ id: 1, name: 'A', username: 'a', role: 'admin', theme: 'auto' });
    const got = await answer;
    expect('me' in got && got.me?.id).toBe(1);
  });

  it('is "needs setup, nobody signed in" even though the server says 401 to /me', async () => {
    const server = slowServer();
    const answer = askServer(server.fetch);
    await settle();
    server.asked[0]!.answer({ needs_setup: true });
    server.asked[1]!.answer({ detail: 'Sign in.' }, 401);
    const got = await answer;
    expect('setup' in got && got.setup.needs_setup).toBe(true);
    expect('me' in got && got.me).toBeNull();
  });

  it('is an error when the server can’t be reached', async () => {
    const answer = askServer((() => Promise.reject(new TypeError('Failed to fetch'))) as never);
    expect('error' in (await answer)).toBe(true);
  });
});
