import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, api, detailOf, getMe, setUnauthorizedHandler } from './api';
import { OFFLINE_AFTER_MS, network } from './network.svelte';
import { toasts } from './toast.svelte';

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
  it('uses the server’s sentence', () => {
    expect(detailOf({ detail: 'That username and password don’t match.' })).toBe(
      'That username and password don’t match.'
    );
  });

  it('reads the first validation message, without the technical prefix', () => {
    const body = {
      detail: [{ loc: ['body', 'username'], msg: 'Value error, Use up to 50 lowercase letters.' }]
    };
    expect(detailOf(body)).toBe('Use up to 50 lowercase letters.');
  });

  it('falls back to a plain sentence', () => {
    expect(detailOf(null)).toBe('Something went wrong. Try again.');
    expect(detailOf({ detail: [] })).toBe('Something went wrong. Try again.');
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

  it('sends a file as it is, with its own type (a recipe photo), not as JSON', async () => {
    const { fetch, calls } = fakeFetch(201, { id: 5 });
    const photo = new File([new Uint8Array([1, 2, 3])], 'dish.webp', { type: 'image/webp' });
    await api('POST', '/recipes/photos', photo, { fetch });
    expect(calls[0]!.init?.body).toBe(photo);
    expect(calls[0]!.init?.headers).toEqual({ 'content-type': 'image/webp' });
  });

  it('turns refusals into ApiError with the reason', async () => {
    const body = { detail: 'Too many tries. Wait 1 minute.' };
    const { fetch } = fakeFetch(429, body);
    await expect(api('POST', '/session', {}, { fetch, signingIn: true })).rejects.toEqual(
      new ApiError(429, 'Too many tries. Wait 1 minute.', null, body)
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

  it('says plainly when the server can’t be reached', async () => {
    const fetch = (async () => {
      throw new TypeError('Failed to fetch');
    }) as typeof globalThis.fetch;
    await expect(api('GET', '/me', undefined, { fetch })).rejects.toMatchObject({
      status: 0,
      detail: 'Can’t reach your Mealwright server. Check your connection.'
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

describe('a late answer while the server is down (follow-up 10)', () => {
  afterEach(() => {
    network.reset();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('an answer to a request sent before the server went down doesn’t clear the bar or say “Back online — all saved”', async () => {
    vi.useFakeTimers();
    network.reset();
    // The online check and every new request: Caddy's 502, the server is stopped.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('', { status: 502 }))
    );
    const shown = vi.spyOn(toasts, 'show');
    const stop = network.start(() => {});
    try {
      // A slow request (an import, say) went out while the server was still up…
      let answer: (r: Response) => void = () => {};
      const slow = api('GET', '/recipes', undefined, {
        fetch: () => new Promise<Response>((done) => (answer = done))
      });
      // …then the server stopped: the next request gets the proxy's 502, and the bar shows.
      await expect(api('GET', '/pantry')).rejects.toBeInstanceOf(ApiError);
      await vi.advanceTimersByTimeAsync(OFFLINE_AFTER_MS);
      expect(network.offline).toBe(true);
      // The server finishes the slow request on its way down; the answer comes in late.
      answer(new Response('{"recipes":[]}', { status: 200 }));
      await slow;
      await vi.advanceTimersByTimeAsync(0);
      expect(network.offline).toBe(true);
      // Still down a minute later, with no toast at any point.
      await vi.advanceTimersByTimeAsync(60_000);
      expect(network.offline).toBe(true);
      expect(shown).not.toHaveBeenCalled();
    } finally {
      stop();
    }
  });

  it('a late answer still counts when the server really is back: it checks at once', async () => {
    vi.useFakeTimers();
    network.reset();
    let up = false;
    const check = vi.fn(async () => (up ? new Response('{}') : new Response('', { status: 502 })));
    vi.stubGlobal('fetch', check);
    const stop = network.start(() => {});
    try {
      let answer: (r: Response) => void = () => {};
      const slow = api('GET', '/recipes', undefined, {
        fetch: () => new Promise<Response>((done) => (answer = done))
      });
      await expect(api('GET', '/pantry')).rejects.toBeInstanceOf(ApiError);
      await vi.advanceTimersByTimeAsync(OFFLINE_AFTER_MS);
      up = true;
      const before = check.mock.calls.length;
      answer(new Response('{"recipes":[]}', { status: 200 }));
      await slow;
      await vi.advanceTimersByTimeAsync(0);
      expect(check.mock.calls.length).toBe(before + 1);
      expect(network.offline).toBe(false);
    } finally {
      stop();
    }
  });
});
