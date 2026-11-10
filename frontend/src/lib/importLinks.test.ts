import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ImportReview } from '#lib/client/imports.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { PINTS_REVIEW } from '#lib/testing/importSamples.js';
import { drafts } from './drafts.svelte';
import {
  ImportLinks,
  MOST_LINKS,
  STOPPED_DRAFTS_FULL,
  STOPPED_SWITCHED_OFF,
  canPaste,
  importLinks,
  sameLink
} from './importLinks.svelte';
import { runWipeHooks } from './offline/wipeHooks';

const review = (name: string): ImportReview => ({ ...PINTS_REVIEW, name });

afterEach(() => {
  vi.unstubAllGlobals();
  drafts.forget();
});

const keepsDrafts = (request: FakeRequest): [number, unknown] => [
  201,
  { id: 1, ...(request.body as object) }
];
const noDrafts = [200, { drafts: [], count: 0 }] as [number, unknown];

describe('several links at once (F110)', () => {
  it('reads one after another, each into its own draft; a failing one in the middle stops nothing', async () => {
    const links = ['https://a.example/dal', 'https://b.example/blocked', 'https://c.example/rice'];
    const requests = fakeApi({
      'POST /recipes/import': (request: FakeRequest) => {
        const text = (request.body as { text: string }).text;
        return text.includes('blocked')
          ? [
              422,
              {
                detail:
                  'That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead.',
                code: 'site_refused'
              }
            ]
          : [200, review(text.includes('dal') ? 'Dal' : 'Rice')];
      },
      'POST /recipes/drafts': (request: FakeRequest) => [
        201,
        { id: 1, ...(request.body as object) }
      ],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    const reader = new ImportLinks();
    await reader.run(links);

    // One link per request, in order, one at a time.
    const sent = requests
      .filter((r) => r.path === '/recipes/import')
      .map((r) => (r.body as { text: string }).text);
    expect(sent).toEqual(links);
    // Two drafts, one per good link; the failed one made none.
    expect(
      requests.filter((r) => r.method === 'POST' && r.path === '/recipes/drafts')
    ).toHaveLength(2);
    expect(reader.rows.map((r) => [r.title, r.state])).toEqual([
      ['Dal', 'ready'],
      ['blocked', 'failed'],
      ['Rice', 'ready']
    ]);
    const failed = reader.rows[1]!;
    expect(failed.message).toContain('Paste the recipe’s text instead');
    expect(canPaste(failed)).toBe(true);
    expect(reader.running).toBe(false);
  });

  it('shows each row as waiting until its turn, and reads a repeated link once', async () => {
    const seen: string[][] = [];
    const reader = new ImportLinks();
    fakeApi({
      'POST /recipes/import': () => {
        seen.push(reader.rows.map((r) => r.state));
        return [200, review('Dal')];
      },
      'POST /recipes/drafts': (request: FakeRequest) => [
        201,
        { id: 1, ...(request.body as object) }
      ],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    await reader.run(['https://a.example/x', 'https://a.example/x', 'https://b.example/y']);
    expect(reader.rows).toHaveLength(2);
    expect(seen).toEqual([
      ['reading', 'waiting'],
      ['ready', 'reading']
    ]);
  });

  it('a link already imported is said, not read again, and the rest carry on', async () => {
    fakeApi({
      'POST /recipes/import': (request: FakeRequest) =>
        (request.body as { text: string }).text.includes('have')
          ? [
              409,
              {
                detail: 'You already have this recipe',
                code: 'already_imported',
                recipe: { id: 3, name: 'Dal' },
                site: 'a.example',
                imported_at: '2026-11-01'
              }
            ]
          : [200, review('Rice')],
      'POST /recipes/drafts': (request: FakeRequest) => [
        201,
        { id: 1, ...(request.body as object) }
      ],
      'GET /recipes/drafts': [200, { drafts: [], count: 0 }]
    });
    const reader = new ImportLinks();
    await reader.run(['https://a.example/have', 'https://b.example/new']);
    expect(reader.rows.map((r) => r.state)).toEqual(['failed', 'ready']);
    expect(canPaste(reader.rows[0]!)).toBe(false);
  });

  const many = (n: number) => Array.from({ length: n }, (_, i) => `https://a.example/r${i}`);

  it('reads at most 20 links in one paste, and says how many were left out', async () => {
    const requests = fakeApi({
      'POST /recipes/import': [200, review('Dal')],
      'POST /recipes/drafts': keepsDrafts,
      'GET /recipes/drafts': noDrafts
    });
    const reader = new ImportLinks();
    await reader.run(many(25));
    expect(reader.rows).toHaveLength(MOST_LINKS);
    expect(reader.leftOut).toBe(5);
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(MOST_LINKS);
  });

  it('reads no more than the room Drafts has left', async () => {
    const full = Array.from({ length: 48 }, (_, i) => ({ id: i }));
    const requests = fakeApi({
      'POST /recipes/import': [200, review('Dal')],
      'POST /recipes/drafts': keepsDrafts,
      'GET /recipes/drafts': [200, { drafts: full, count: 48 }]
    });
    const reader = new ImportLinks();
    await reader.run(many(5));
    expect(reader.rows).toHaveLength(2);
    expect([reader.leftOut, reader.room]).toEqual([3, 2]);
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(2);
  });

  it('reads the same page typed two ways once', async () => {
    expect(sameLink('https://A.example/x/')).toBe(sameLink('a.example/x#top'));
    expect(sameLink('https://a.example/x?a=1')).not.toBe(sameLink('https://a.example/x'));
    const requests = fakeApi({
      'POST /recipes/import': [200, review('Dal')],
      'POST /recipes/drafts': keepsDrafts,
      'GET /recipes/drafts': noDrafts
    });
    const reader = new ImportLinks();
    await reader.run(['https://A.example/x/', 'a.example/x#top', 'https://b.example/y']);
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(2);
  });

  it('stops when Drafts is full, and the rows left say why', async () => {
    let kept = 0;
    const requests = fakeApi({
      'POST /recipes/import': [200, review('Dal')],
      'POST /recipes/drafts': (request: FakeRequest) =>
        ++kept === 2
          ? [
              409,
              { detail: 'You have 50 drafts. Finish or delete one first.', code: 'too_many_drafts' }
            ]
          : keepsDrafts(request),
      'GET /recipes/drafts': noDrafts
    });
    const reader = new ImportLinks();
    await reader.run(many(5));
    expect(reader.rows.map((r) => r.state)).toEqual([
      'ready',
      'failed',
      'failed',
      'failed',
      'failed'
    ]);
    expect(reader.rows[2]!.message).toBe(STOPPED_DRAFTS_FULL);
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(2);
  });

  it('stops when importing from links is switched off', async () => {
    const requests = fakeApi({
      'POST /recipes/import': [
        403,
        { detail: 'Importing from links is switched off', code: 'import_switched_off' }
      ],
      'GET /recipes/drafts': noDrafts
    });
    const reader = new ImportLinks();
    await reader.run(many(3));
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(1);
    expect(reader.rows.map((r) => r.code)).toEqual(['import_switched_off', 'stopped', 'stopped']);
    expect(reader.rows[1]!.message).toBe(STOPPED_SWITCHED_OFF);
  });

  it('stops and forgets its list when the session ends', async () => {
    const reader = new ImportLinks();
    const requests = fakeApi({
      'POST /recipes/import': () => {
        reader.forget(); // signed out while the first link was being read
        return [200, review('Dal')];
      },
      'POST /recipes/drafts': keepsDrafts,
      'GET /recipes/drafts': noDrafts
    });
    await reader.run(many(4));
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(1);
    expect(reader.rows).toEqual([]);
    expect(reader.running).toBe(false);
  });

  it('is forgotten when this browser is wiped at sign-out', async () => {
    fakeApi({
      'POST /recipes/import': [200, review('Dal')],
      'POST /recipes/drafts': keepsDrafts,
      'GET /recipes/drafts': noDrafts
    });
    await importLinks.run(['https://a.example/x']);
    expect(importLinks.rows).toHaveLength(1);
    runWipeHooks();
    expect(importLinks.rows).toEqual([]);
  });
});
