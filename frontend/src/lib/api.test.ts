import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, detailOf, getMe, setUnauthorizedHandler } from './api';
import { OFFLINE_AFTER_MS, network } from './network.svelte';

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
    const body = { detail: 'Too many tries. Please wait 1 minute.' };
    const { fetch } = fakeFetch(429, body);
    await expect(api('POST', '/session', {}, { fetch, signingIn: true })).rejects.toEqual(
      new ApiError(429, 'Too many tries. Please wait 1 minute.', null, body)
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

describe('api for changes (0.2)', () => {
  it('sends the change ID as the Idempotency-Key header', async () => {
    const { fetch, calls } = fakeFetch(200, {});
    await api('PATCH', '/foods/7', { staple: true }, { fetch, idempotencyKey: 'abc-123' });
    const headers = calls[0]!.init!.headers as Record<string, string>;
    expect(headers['idempotency-key']).toBe('abc-123');
    expect(headers['content-type']).toBe('application/json');
    expect(calls[0]!.init!.method).toBe('PATCH');
  });

  it('sends no headers at all for a plain read', async () => {
    const { fetch, calls } = fakeFetch(200, {});
    await api('GET', '/foods', undefined, { fetch });
    expect(calls[0]!.init!.headers).toBeUndefined();
  });

  it('keeps the error code and the whole answer', async () => {
    const answer = {
      detail: 'There’s already an ingredient called Toor dal.',
      code: 'name_taken',
      food_id: 7
    };
    const { fetch } = fakeFetch(409, answer);
    const error = await api('POST', '/foods', { name: 'Toor dal' }, { fetch }).catch(
      (e: unknown) => e
    );
    expect(error).toBeInstanceOf(ApiError);
    if (!(error instanceof ApiError)) return;
    expect(error.code).toBe('name_taken');
    expect(error.body).toEqual(answer);
    expect(error.detail).toBe(answer.detail);
  });
});

describe('api and the connection bar', () => {
  afterEach(() => {
    network.reset();
    vi.useRealTimers();
  });

  it('a network failure is a failure; any answer, even a refusal, is a success', async () => {
    vi.useFakeTimers();
    const down = (async () => {
      throw new TypeError('Failed to fetch');
    }) as typeof globalThis.fetch;
    await expect(api('GET', '/version', undefined, { fetch: down })).rejects.toMatchObject({
      status: 0
    });
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    expect(network.offline).toBe(true);
    // The server answers (even "no"): it is there.
    await expect(
      api('GET', '/version', undefined, { fetch: fakeFetch(403, { detail: 'No.' }).fetch })
    ).rejects.toBeInstanceOf(ApiError);
    expect(network.offline).toBe(false);
  });

  it('a 502, 503 or 504 from the reverse proxy means the server is not reachable', async () => {
    vi.useFakeTimers();
    for (const status of [502, 503, 504]) {
      network.reset();
      await expect(
        api('GET', '/version', undefined, {
          fetch: fakeFetch(status, { detail: 'Bad gateway' }).fetch
        })
      ).rejects.toMatchObject({ status });
      vi.advanceTimersByTime(OFFLINE_AFTER_MS);
      expect(network.offline, `status ${status}`).toBe(true);
    }
    // A real server error (500) is still an answer from Mealwright.
    network.reset();
    await expect(
      api('GET', '/version', undefined, { fetch: fakeFetch(500, { detail: 'Oops' }).fetch })
    ).rejects.toMatchObject({ status: 500 });
    vi.advanceTimersByTime(OFFLINE_AFTER_MS);
    expect(network.offline).toBe(false);
  });

  it('gives every request a time limit', async () => {
    const { fetch, calls } = fakeFetch(200, {});
    await api('GET', '/version', undefined, { fetch });
    expect(calls[0]?.init?.signal).toBeInstanceOf(AbortSignal);
  });
});
