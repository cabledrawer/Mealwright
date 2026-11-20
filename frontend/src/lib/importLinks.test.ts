import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ImportReview } from '#lib/client/imports.js';
import { changeOf, fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { PINTS_REVIEW, SAMPLE_REVIEW } from '#lib/testing/importSamples.js';
import { toasts } from './toast.svelte';
import { undoHistory } from './undo.svelte';
import { drafts } from './drafts.svelte';
import {
  ImportLinks,
  type LinkRow,
  MAX_LINKS,
  STOPPED_DRAFTS_FULL,
  STOPPED_SWITCHED_OFF,
  canPaste,
  noneReadWords,
  importLinks,
  sameLink
} from './importLinks.svelte';
import { runWipeHooks } from './offline/wipeHooks';

const review = (name: string): ImportReview => ({ ...PINTS_REVIEW, name });

afterEach(() => {
  vi.unstubAllGlobals();
  drafts.forget();
  undoHistory.clear();
  toasts.dismiss();
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
    expect(reader.rows).toHaveLength(MAX_LINKS);
    expect(reader.leftOut).toBe(5);
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(MAX_LINKS);
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

  it('keeps nothing from a read that was still going when the session ended', async () => {
    const reader = new ImportLinks();
    const requests = fakeApi({
      'POST /recipes/import': () => {
        reader.forget();
        return [200, review('Dal')];
      },
      'POST /recipes/drafts': keepsDrafts,
      'GET /recipes/drafts': noDrafts
    });
    await reader.run(many(2));
    expect(requests.filter((r) => r.path === '/recipes/drafts' && r.method === 'POST')).toEqual([]);
  });

  it('says so when Drafts has no room and nothing was read', async () => {
    const reader = new ImportLinks();
    const full = Array.from({ length: 50 }, (_, i) => ({ id: i }));
    const requests = fakeApi({ 'GET /recipes/drafts': [200, { drafts: full, count: 50 }] });
    await reader.run(many(3));
    expect(reader.rows).toEqual([]);
    expect(reader.leftOut).toBe(3);
    expect(requests.filter((r) => r.path === '/recipes/import')).toEqual([]);
    expect(noneReadWords(3)).toBe(
      'Drafts is full: none of the 3 links were read. Finish or delete a draft first.'
    );
  });

  it('two quick pastes start one run, at most 20 reads', async () => {
    const reader = new ImportLinks();
    const requests = fakeApi({
      'POST /recipes/import': [200, review('Dal')],
      'POST /recipes/drafts': keepsDrafts,
      'GET /recipes/drafts': noDrafts
    });
    const first = reader.run(many(30));
    const second = reader.run(many(30)); // not awaited first
    await Promise.all([first, second]);
    expect(requests.filter((r) => r.path === '/recipes/import').length).toBeLessThanOrEqual(
      MAX_LINKS
    );
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

// Each read link opens its draft (F209) and the ones whose ingredients all matched can be saved in
// one go (F216, quick import).
describe('opening a result, and quick import (F209, F216; cabledrawer 10 Nov)', () => {
  const bodies = new Map<number, Record<string, unknown>>();
  /** Drafts taken away behind this screen's back (saved or discarded from Check, or elsewhere). */
  const gone = new Set<number>();
  let next = 40;

  /** A server with drafts that remember what was kept, and the save for the matched one. */
  function server(
    extra: Record<string, [number, unknown] | ((r: FakeRequest) => [number, unknown])> = {}
  ) {
    bodies.clear();
    gone.clear();
    next = 40;
    return fakeApi({
      'POST /recipes/import': (request: FakeRequest) =>
        (request.body as { text: string }).text.includes('ready')
          ? [200, review('Ready dal')]
          : [200, { ...SAMPLE_REVIEW, name: 'Needs you' }],
      'POST /recipes/drafts': (request: FakeRequest) => {
        const id = next++;
        const body = request.body as Record<string, unknown>;
        bodies.set(id, body);
        return [201, { id, ...body }];
      },
      // The household's drafts, as kept so far (so a draft that is gone can be told from one that is not).
      'GET /recipes/drafts': () => [
        200,
        {
          drafts: [...bodies.keys()].filter((id) => !gone.has(id)).map((id) => ({ id, name: 'x' })),
          count: bodies.size
        }
      ],
      ...extra
    });
  }
  const draftOut = (request: FakeRequest): [number, unknown] => {
    const id = Number(request.path.split('/').pop());
    return [200, { id, name: 'x', ...bodies.get(id) }];
  };
  const links = ['https://a.example/ready-dal', 'https://b.example/other'];

  it('keeps the draft each read link was kept as, and which ones matched completely', async () => {
    server();
    const reader = new ImportLinks();
    await reader.run(links);
    expect(reader.rows.map((r) => [r.title, r.draftId, r.allMatched])).toEqual([
      ['Ready dal', 40, true],
      ['Needs you', 41, false]
    ]);
    expect(reader.ready.map((r) => r.title)).toEqual(['Ready dal']);
  });

  it('saves only the drafts that matched completely, with one toast and one Undo for them all', async () => {
    const requests = server({
      'GET /recipes/drafts/40': draftOut,
      'POST /recipes/import/save': [
        201,
        {
          recipe: { id: 55, name: 'Ready dal' },
          change: changeOf(60, 'Imported Ready dal'),
          new_foods: [],
          learned: 0
        }
      ],
      'POST /changes/60/undo': [200, { result: 'done', message: 'back', change: changeOf(61, 'x') }]
    });
    const reader = new ImportLinks();
    await reader.run(links);
    await reader.saveReady();
    const saves = requests.filter((r) => r.path === '/recipes/import/save');
    expect(saves).toHaveLength(1);
    expect((saves[0]!.body as { draft_id: number }).draft_id).toBe(40);
    // The one that needs checking was never opened for saving, and stays a draft.
    expect(requests.some((r) => r.path === '/recipes/drafts/41' && r.method !== 'GET')).toBe(false);
    expect(reader.rows.map((r) => r.savedId)).toEqual([55, null]);
    expect(toasts.current?.message).toBe('Saved 1 recipe');
    expect(undoHistory.size).toBe(1);
    // One Undo takes every save back (the server's own Undo of an import brings the draft back).
    await undoHistory.undoLast();
    expect(requests.some((r) => r.path === '/changes/60/undo')).toBe(true);
    expect(reader.rows.map((r) => r.savedId)).toEqual([null, null]);
    expect(reader.ready).toHaveLength(1);
  });

  it('a draft that can’t be saved stays in Drafts with its sentence, and the toast counts the rest', async () => {
    server({
      'GET /recipes/drafts/40': draftOut,
      'GET /recipes/drafts/41': draftOut,
      'POST /recipes/import': [200, review('Ready dal')],
      'POST /recipes/import/save': (request: FakeRequest) =>
        (request.body as { draft_id: number }).draft_id === 40
          ? [
              201,
              {
                recipe: { id: 55, name: 'Ready dal' },
                change: changeOf(60, 'Imported Ready dal'),
                new_foods: [],
                learned: 0
              }
            ]
          : [409, { detail: 'There’s already an ingredient called Paprika.' }]
    });
    const reader = new ImportLinks();
    await reader.run(['https://a.example/one', 'https://b.example/two']);
    await reader.saveReady();
    expect(reader.rows.map((r) => r.savedId)).toEqual([55, null]);
    expect(reader.rows[1]!.message).toBe('There’s already an ingredient called Paprika.');
    expect(toasts.current?.message).toBe('Saved 1 recipe. 1 stays in Drafts');
  });

  it('with nothing matched completely there is nothing to save, and nothing is sent', async () => {
    const requests = server({
      'POST /recipes/import': [200, { ...SAMPLE_REVIEW, name: 'Needs you' }]
    });
    const reader = new ImportLinks();
    await reader.run(links);
    expect(reader.ready).toEqual([]);
    const before = requests.length;
    await reader.saveReady();
    expect(requests).toHaveLength(before);
    expect(undoHistory.size).toBe(0);
  });

  it('one Undo that fails for one save carries on with the rest, and says how many were undone', async () => {
    const requests = server({
      'GET /recipes/drafts/40': draftOut,
      'GET /recipes/drafts/41': draftOut,
      'GET /recipes/drafts/42': draftOut,
      'POST /recipes/import': [200, review('Ready dal')],
      'POST /recipes/import/save': (request: FakeRequest) => {
        const id = (request.body as { draft_id: number }).draft_id;
        return [
          201,
          {
            recipe: { id: id + 15, name: 'Ready dal' },
            change: changeOf(id + 20, 'Imported Ready dal'),
            new_foods: [],
            learned: 0
          }
        ];
      },
      'POST /changes/60/undo': [
        200,
        { result: 'done', message: 'back', change: changeOf(70, 'x') }
      ],
      'POST /changes/61/undo': [500, { detail: 'Something went wrong.' }],
      'POST /changes/62/undo': [200, { result: 'done', message: 'back', change: changeOf(71, 'x') }]
    });
    const reader = new ImportLinks();
    await reader.run(['https://a.example/1', 'https://a.example/2', 'https://a.example/3']);
    await reader.saveReady();
    expect(reader.rows.map((r) => r.savedId)).toEqual([55, 56, 57]);
    await undoHistory.undoLast();
    // The second failed; the third was still taken back, and only the undone ones are unsaved.
    expect(requests.filter((r) => r.path.endsWith('/undo')).map((r) => r.path)).toEqual([
      '/changes/60/undo',
      '/changes/61/undo',
      '/changes/62/undo'
    ]);
    expect(reader.rows.map((r) => r.savedId)).toEqual([null, 56, null]);
    expect(toasts.current?.message).toBe('Undid 2 of 3');
  });

  it('a draft that is gone from Drafts is not offered for saving, and its Check link goes', async () => {
    server({
      'GET /recipes/drafts/40': draftOut,
      'POST /recipes/import': [200, review('Ready dal')],
      'POST /recipes/import/save': [
        201,
        {
          recipe: { id: 55, name: 'Ready dal' },
          change: changeOf(60, 'Imported Ready dal'),
          new_foods: [],
          learned: 0
        }
      ]
    });
    const reader = new ImportLinks();
    await reader.run(['https://a.example/1', 'https://a.example/2']);
    await drafts.load();
    expect(reader.ready).toHaveLength(2);
    gone.add(41); // the second was discarded from Check
    await drafts.load();
    expect(reader.gone(reader.rows[1]!)).toBe(true);
    expect(reader.gone(reader.rows[0]!)).toBe(false);
    expect(reader.ready.map((r) => r.draftId)).toEqual([40]);
  });

  it('a 404 while saving means already gone: no failure toast, no draft left to open', async () => {
    server({
      'GET /recipes/drafts/40': [404, { detail: 'That draft isn’t here any more.' }],
      'POST /recipes/import': [200, review('Ready dal')]
    });
    const reader = new ImportLinks();
    await reader.run(['https://a.example/1']);
    await reader.saveReady();
    expect(reader.rows[0]!.draftId).toBeNull();
    expect(reader.rows[0]!.message).toBe('That draft isn’t here any more.');
    expect(toasts.current?.message ?? '').not.toMatch(/stay/);
    expect(undoHistory.size).toBe(0);
  });
});

describe('after one link fails (RF4 I3)', () => {
  const links = ['https://a.example/dal', 'https://b.example/slow', 'https://c.example/rice'];

  function api(slow: { fails: boolean }) {
    let kept = 0;
    return fakeApi({
      'POST /recipes/import': (request: FakeRequest) => {
        const text = (request.body as { text: string }).text;
        return text.includes('slow') && slow.fails
          ? [422, { detail: 'That took too long. Try again later.', code: 'timeout' }]
          : [200, review(text)];
      },
      'POST /recipes/drafts': (request: FakeRequest) => [
        201,
        { id: ++kept, ...(request.body as object) }
      ],
      'GET /recipes/drafts': () => [
        200,
        { drafts: Array.from({ length: kept }, (_, i) => ({ id: i + 1 })), count: kept }
      ]
    });
  }

  it('Read the recipes again reads only the links not read yet: no second draft of one that worked', async () => {
    const slow = { fails: true };
    const requests = api(slow);
    const reader = new ImportLinks();
    await reader.run(links);
    expect(reader.rows.map((r) => r.state)).toEqual(['ready', 'failed', 'ready']);
    slow.fails = false;
    await reader.run(links);
    const kept = requests.filter((r) => r.method === 'POST' && r.path === '/recipes/drafts');
    expect(kept).toHaveLength(3);
    expect(reader.rows.map((r) => r.state)).toEqual(['ready', 'ready', 'ready']);
    expect(new Set(reader.rows.map((r) => r.draftId)).size).toBe(3);
    const reads = requests.filter((r) => r.method === 'POST' && r.path === '/recipes/import');
    expect(reads).toHaveLength(4);
  });

  it('a link whose draft is gone from Drafts is read again', async () => {
    const slow = { fails: false };
    const requests = api(slow);
    const reader = new ImportLinks();
    await reader.run(links);
    drafts.drafts = drafts.drafts.filter((draft) => draft.id !== 1); // discarded elsewhere
    await reader.run(links);
    const kept = requests.filter((r) => r.method === 'POST' && r.path === '/recipes/drafts');
    expect(kept.length).toBeGreaterThan(3);
  });

  it('Try again reads just that link and leaves the other rows alone', async () => {
    const slow = { fails: true };
    const requests = api(slow);
    const reader = new ImportLinks();
    await reader.run(links);
    const [first, failed] = reader.rows as [LinkRow, LinkRow];
    slow.fails = false;
    await reader.retry(failed);
    expect(reader.rows[0]).toBe(first);
    expect(reader.rows.map((r) => r.state)).toEqual(['ready', 'ready', 'ready']);
    expect(failed.message).toBeNull();
    const reads = requests.filter((r) => r.method === 'POST' && r.path === '/recipes/import');
    expect(reads).toHaveLength(4);
  });

  it('Try again does nothing on a row that is not failed', async () => {
    const requests = api({ fails: false });
    const reader = new ImportLinks();
    await reader.run(links.slice(0, 1));
    await reader.retry(reader.rows[0]!);
    expect(requests.filter((r) => r.path === '/recipes/import')).toHaveLength(1);
  });
});
