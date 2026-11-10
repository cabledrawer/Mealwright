import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ImportReview } from '#lib/client/imports.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { PINTS_REVIEW } from '#lib/testing/importSamples.js';
import { ImportLinks, canPaste } from './importLinks.svelte';

const review = (name: string): ImportReview => ({ ...PINTS_REVIEW, name });

afterEach(() => vi.unstubAllGlobals());

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
});
