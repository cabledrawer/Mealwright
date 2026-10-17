import { afterEach, describe, expect, it } from 'vitest';
import { ApiError, api, detailOf, getMe, setUnauthorizedHandler } from './api';

afterEach(() => setUnauthorizedHandler(null));

function fakeFetch(status: number, body?: unknown) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const fetch = async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return new Response(body === undefined ? null : JSON.stringify(body), { status });
  };
  return { fetch: fetch as typeof globalThis.fetch, calls };
}

describe('detailOf', () => {
  it("uses the server's sentence", () => {
    expect(detailOf({ detail: "That username and password don't match." })).toBe(
      "That username and password don't match."
    );
  });

  it('reads the first validation message, without the technical prefix', () => {
    const body = {
      detail: [{ loc: ['body', 'username'], msg: 'Value error, Use up to 50 lowercase letters.' }]
    };
    expect(detailOf(body)).toBe('Use up to 50 lowercase letters.');
  });

  it('falls back to a plain sentence', () => {
    expect(detailOf(null)).toBe('Something went wrong. Please try again.');
    expect(detailOf({ detail: [] })).toBe('Something went wrong. Please try again.');
  });
});

describe('api', () => {
  it('calls /api/v1 with JSON, on the same origin', async () => {
    const { fetch, calls } = fakeFetch(200, { ok: true });
    expect(await api('PUT', '/me/preferences', { theme: 'dark' }, { fetch })).toEqual({ ok: true });
    expect(calls[0]!.url).toBe('/api/v1/me/preferences');
    expect(calls[0]!.init).toMatchObject({
      method: 'PUT',
      credentials: 'same-origin',
      body: '{"theme":"dark"}'
    });
  });

  it('turns refusals into ApiError with the reason', async () => {
    const { fetch } = fakeFetch(429, { detail: 'Too many tries. Please wait 1 minute.' });
    await expect(api('POST', '/session', {}, { fetch, signingIn: true })).rejects.toEqual(
      new ApiError(429, 'Too many tries. Please wait 1 minute.')
    );
  });

  it('sends people to sign in when their session has ended', async () => {
    let ended = 0;
    setUnauthorizedHandler(() => ended++);
    const { fetch } = fakeFetch(401, { detail: 'Please sign in.' });
    await expect(api('PUT', '/me/preferences', {}, { fetch })).rejects.toBeInstanceOf(ApiError);
    expect(ended).toBe(1);
    // A wrong password isn't an ended session.
    await expect(api('POST', '/session', {}, { fetch, signingIn: true })).rejects.toBeInstanceOf(
      ApiError
    );
    expect(ended).toBe(1);
  });

  it("says plainly when the server can't be reached", async () => {
    const fetch = (async () => {
      throw new TypeError('Failed to fetch');
    }) as typeof globalThis.fetch;
    await expect(api('GET', '/me', undefined, { fetch })).rejects.toMatchObject({
      status: 0,
      detail: "Can't reach your Mealwright server. Check your connection."
    });
  });
});

describe('getMe', () => {
  it('is null when nobody is signed in', async () => {
    expect(await getMe(fakeFetch(401, { detail: 'Please sign in.' }).fetch)).toBeNull();
  });

  it('is the person when signed in', async () => {
    const me = { id: 1, name: 'Tess', username: 'tess', role: 'admin', theme: 'dark' };
    expect(await getMe(fakeFetch(200, me).fetch)).toEqual(me);
  });
});
