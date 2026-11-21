import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { DraftBrief, DraftOut } from '#lib/client/drafts.js';
import { drafts } from '#lib/drafts.svelte.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi, changeOf } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import DraftsScreen from './DraftsScreen.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const nav = vi.hoisted(() => ({ goto: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: nav.goto, beforeNavigate: vi.fn() }));

const draft = (over: Partial<DraftBrief>): DraftBrief => ({
  id: 1,
  name: 'Chettinad kuzhambu',
  source: { kind: 'link', site: 'bbcgoodfood.com' },
  started_by: 'Tess',
  started_at: '2026-10-20T10:00:00Z',
  updated_at: '2026-10-22T10:00:00Z',
  expires_at: '2026-11-06T10:00:00Z',
  days_left: 13,
  lines_total: 9,
  lines_checked: 6,
  ...over
});

const THREE = [
  draft({}),
  draft({
    id: 2,
    name: 'Rava dosa',
    source: { kind: 'text', site: null },
    started_by: 'Wren',
    days_left: 15,
    lines_total: 10,
    lines_checked: 2
  }),
  draft({
    id: 3,
    name: 'Aloo paratha',
    source: { kind: 'link', site: 'www.example.com' },
    started_by: 'Wren',
    days_left: 3,
    lines_total: 4,
    lines_checked: 4
  })
];
const list = (items: DraftBrief[]): [number, unknown] => [
  200,
  { drafts: items, count: items.length }
];

describe('the Drafts screen', () => {
  let component: ReturnType<typeof mount> | null = null;

  async function open(routes: Parameters<typeof fakeApi>[0], width = 390, fromMealie = false) {
    await page.viewport(width, 844);
    const requests = fakeApi(routes);
    component = mount(DraftsScreen, { target: document.body, props: { fromMealie } });
    flushSync();
    return requests;
  }

  beforeEach(() => {
    session.me = { ...ME, role: 'admin' };
    network.reset();
    drafts.forget();
    undoHistory.clear();
    toasts.dismiss();
    nav.goto.mockReset();
  });

  afterEach(() => {
    session.me = null;
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
  });

  describe('on a phone', () => {
    it('lists each draft as the mockup does, with its days and how far it has got', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByRole('heading', { name: 'Drafts', level: 1 })).toBeVisible();
      await expect
        .element(page.getByText('Imports your household hasn’t finished · kept for 15 days'))
        .toBeVisible();
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      await expect.element(page.getByText('From bbcgoodfood.com · started by Tess')).toBeVisible();
      await expect.element(page.getByText('13 days left')).toBeVisible();
      await expect.element(page.getByText('6 of 9 ingredients checked · 3 need you')).toBeVisible();
      await expect.element(page.getByText('Pasted text · started by Wren')).toBeVisible();
      await expect.element(page.getByText('15 days left')).toBeVisible();
      await expect.element(page.getByText('3 days left')).toBeVisible();
      await expect.element(page.getByText('All checked · ready to save')).toBeVisible();
      await expect
        .element(
          page.getByText(
            'Nothing here is in your recipes yet. Drafts are deleted quietly after 15 days.'
          )
        )
        .toBeVisible();
    });

    it('has a visible Carry on and Delete on every draft, and Save recipe only when all is checked', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      expect(page.getByRole('link', { name: /^Carry on/ }).elements()).toHaveLength(3);
      expect(page.getByRole('button', { name: /^Delete/ }).elements()).toHaveLength(3);
      await expect
        .element(page.getByRole('link', { name: 'Carry on Rava dosa' }))
        .toHaveAttribute('href', '/recipes/drafts/2');
      expect(page.getByRole('button', { name: /^Save recipe/ }).elements()).toHaveLength(1);
      await expect
        .element(page.getByRole('button', { name: 'Save recipe Aloo paratha' }))
        .toBeVisible();
      // A swipe shows a button only when swiped: none of its buttons is there until then.
      expect(document.body.textContent).not.toMatch(/[Ss]wipe/);
    });

    it('Delete hides the draft at once, with an Undo toast; Undo brings it back', async () => {
      const requests = await open({
        'GET /recipes/drafts': list(THREE),
        'DELETE /recipes/drafts/2': [200, { change: changeOf(40, 'Deleted the Rava dosa draft') }],
        'POST /changes/40/undo': [
          200,
          { result: 'done', message: 'back', change: changeOf(41, 'x') }
        ]
      });
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
      await page.getByRole('button', { name: 'Delete Rava dosa' }).click();
      await expect.element(page.getByText('Rava dosa')).not.toBeInTheDocument();
      expect(requests.some((r) => r.method === 'DELETE' && r.path === '/recipes/drafts/2')).toBe(
        true
      );
      expect(toasts.current?.message).toBe('Deleted the Rava dosa draft');
      expect(toasts.current?.action?.label).toBe('Undo');
      expect(undoHistory.size).toBe(1);
      // Ctrl+Z (the same Undo as the toast's button).
      fakeApi({
        'POST /changes/40/undo': [
          200,
          { result: 'done', message: 'back', change: changeOf(41, 'x') }
        ],
        'GET /recipes/drafts': list(THREE)
      });
      await undoHistory.undoLast();
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
    });

    it('Undo pressed at once, before the delete has answered, still brings the draft back', async () => {
      let release: () => void = () => {};
      const held = new Promise<void>((resolve) => (release = resolve));
      const sent: string[] = [];
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
      vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
        const route = `${init.method ?? 'GET'} ${String(input).replace('/api/v1', '')}`;
        sent.push(route);
        if (route === 'DELETE /recipes/drafts/2') await held; // the server hasn't answered yet
        const body =
          route === 'GET /recipes/drafts'
            ? { drafts: THREE, count: 3 }
            : route.startsWith('DELETE')
              ? { change: changeOf(40, 'Deleted the Rava dosa draft') }
              : { result: 'done', message: 'back', change: changeOf(41, 'x') };
        return new Response(JSON.stringify(body), { status: 200 });
      });
      await page.getByRole('button', { name: 'Delete Rava dosa' }).click();
      await expect.element(page.getByText('Rava dosa')).not.toBeInTheDocument();
      expect(undoHistory.size).toBe(1); // there is something to undo before the answer comes
      const undone = undoHistory.undoLast();
      release();
      expect(await undone).toBe(true);
      expect(sent).toContain('POST /changes/40/undo');
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
    });

    /** A finger sliding sideways over a card: down, two moves, up. */
    function swipe(slide: Element, dx: number) {
      const base = { pointerId: 9, pointerType: 'touch', isPrimary: true, bubbles: true };
      const at = (x: number) => ({ ...base, clientX: x, clientY: 300 });
      slide.dispatchEvent(new PointerEvent('pointerdown', at(200)));
      slide.dispatchEvent(new PointerEvent('pointermove', at(200 + dx / 2)));
      slide.dispatchEvent(new PointerEvent('pointermove', at(200 + dx)));
      slide.dispatchEvent(new PointerEvent('pointerup', at(200 + dx)));
      flushSync();
    }
    const slideOf = (name: string) =>
      page.getByText(name, { exact: true }).first().element().closest('.slide') as HTMLElement;

    it('swipe right shows Carry on, which opens the draft; a swipe alone goes nowhere', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
      swipe(slideOf('Rava dosa'), 110);
      const carry = page.getByRole('button', { name: 'Carry on Rava dosa' });
      await expect.element(carry).toBeVisible();
      expect(nav.goto).not.toHaveBeenCalled();
      await carry.click();
      expect(nav.goto).toHaveBeenCalledWith('/recipes/drafts/2');
    });

    it('swipe left shows Delete, which deletes at once with an Undo toast and asks nothing', async () => {
      const requests = await open({
        'GET /recipes/drafts': list(THREE),
        'DELETE /recipes/drafts/2': [200, { change: changeOf(40, 'Deleted the Rava dosa draft') }]
      });
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
      swipe(slideOf('Rava dosa'), -110);
      expect(requests.some((r) => r.method === 'DELETE')).toBe(false);
      await page.getByRole('button', { name: 'Delete Rava dosa' }).first().click();
      await expect.element(page.getByText('Rava dosa')).not.toBeInTheDocument();
      expect(requests.some((r) => r.method === 'DELETE' && r.path === '/recipes/drafts/2')).toBe(
        true
      );
      expect(toasts.current?.message).toBe('Deleted the Rava dosa draft');
      expect(toasts.current?.action?.label).toBe('Undo');
      expect(page.getByRole('dialog').elements()).toHaveLength(0);
    });

    it('offline there is no swipe-to-delete, as Delete is off too', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
      network.offline = true;
      network.deviceOffline = true;
      flushSync();
      swipe(slideOf('Rava dosa'), -110);
      expect(page.getByRole('button', { name: 'Delete Rava dosa' }).elements()).toHaveLength(1);
      await expect.element(page.getByRole('button', { name: 'Delete Rava dosa' })).toBeDisabled();
    });

    it('puts a draft back and says so when the delete did not go through', async () => {
      await open({
        'GET /recipes/drafts': list(THREE),
        'DELETE /recipes/drafts/2': [500, { detail: 'Something went wrong.' }]
      });
      await page.getByRole('button', { name: 'Delete Rava dosa' }).click();
      await expect.element(page.getByText('Something went wrong.')).toBeVisible();
      await expect.element(page.getByText('Rava dosa')).toBeVisible();
      expect(undoHistory.size).toBe(0);
    });

    it('Save recipe makes the recipe from the draft and opens it', async () => {
      const full: DraftOut = {
        ...THREE[2]!,
        text: 'Aloo paratha\n1 potato',
        review: {
          source: { kind: 'text', url: null, site: null },
          name: 'Aloo paratha',
          description: null,
          author: null,
          time_minutes: null,
          serves: 4,
          makes: null,
          tags: [],
          nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
          photo: { state: 'none', photo: null, message: null },
          lines: [
            {
              kind: 'ingredient',
              written: '1 potato',
              words: 'potato',
              amount: 1,
              amount_text: '1',
              unit: null,
              size: null,
              note: null,
              readable: true,
              label: 'matched',
              food: { id: 4, name: 'Potatoes' },
              place: null,
              matched_by: 'potato',
              counts: true,
              new_ingredient: null,
              learn_name: null
            }
          ],
          steps: [{ kind: 'step', text: 'Cook.' }],
          counts: { matched: 1, to_confirm: 0, needs_you: 0, staple: 0 },
          lines_cut: false,
          steps_cut: false,
          steps_shortened: 0,
          left_out: []
        },
        choices: { name: null, serves: null, minutes: null, lines: {} }
      };
      const requests = await open({
        'GET /recipes/drafts': list(THREE),
        'GET /recipes/drafts/3': [200, full],
        'POST /recipes/import/save': [
          201,
          {
            recipe: { id: 55, name: 'Aloo paratha' },
            change: changeOf(60, 'Imported Aloo paratha'),
            new_ingredients: [],
            learned: 0
          }
        ]
      });
      await page.getByRole('button', { name: 'Save recipe Aloo paratha' }).click();
      await vi.waitFor(() => expect(nav.goto).toHaveBeenCalled());
      const saved = requests.find((r) => r.path === '/recipes/import/save')!;
      expect((saved.body as Record<string, unknown>).draft_id).toBe(3);
      expect(String(nav.goto.mock.calls[0]![0])).toBe('/recipes/55');
    });

    it('never saves a draft from the list that still has an ingredient that needs a choice', async () => {
      // The list said all checked, but an ingredient has gone since (the draft comes back with a line that needs you).
      const stale = { ...THREE[2]! };
      const requests = await open({
        'GET /recipes/drafts': list([stale]),
        'GET /recipes/drafts/3': [
          200,
          {
            ...stale,
            text: 'x',
            review: {
              source: { kind: 'text', url: null, site: null },
              name: 'Aloo paratha',
              description: null,
              author: null,
              time_minutes: null,
              serves: 4,
              makes: null,
              tags: [],
              nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
              photo: { state: 'none', photo: null, message: null },
              lines: [
                {
                  kind: 'ingredient',
                  written: '1 potato',
                  words: 'potato',
                  amount: 1,
                  amount_text: '1',
                  unit: null,
                  size: null,
                  note: null,
                  readable: true,
                  label: 'needs_you',
                  food: null,
                  place: null,
                  matched_by: null,
                  counts: true,
                  new_ingredient: null,
                  learn_name: null
                }
              ],
              steps: [],
              counts: { matched: 0, to_confirm: 0, needs_you: 1, staple: 0 },
              lines_cut: false,
              steps_cut: false,
              steps_shortened: 0,
              left_out: []
            },
            choices: { name: null, serves: null, minutes: null, lines: {} }
          }
        ]
      });
      await page.getByRole('button', { name: 'Save recipe Aloo paratha' }).click();
      await expect
        .element(
          page.getByText('That draft has ingredients that still need you. Carry on to finish it.')
        )
        .toBeVisible();
      expect(requests.some((r) => r.path === '/recipes/import/save')).toBe(false);
      expect(nav.goto).not.toHaveBeenCalled();
    });
  });

  describe('on a computer', () => {
    it('is a table with the mockup’s columns, and the same buttons', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) }, 1280);
      await expect.element(page.getByRole('table', { name: 'Drafts' })).toBeVisible();
      const headers = page
        .getByRole('columnheader')
        .elements()
        .map((h) => h.textContent?.trim());
      expect(headers).toEqual(['Recipe', 'From', 'Started by', 'Checked', 'Left', 'Actions']);
      await expect.element(page.getByText('bbcgoodfood.com')).toBeVisible();
      await expect.element(page.getByText('Pasted text')).toBeVisible();
      await expect.element(page.getByText('6 of 9 · 3 need you')).toBeVisible();
      await expect.element(page.getByText('13 days', { exact: true })).toBeVisible();
      await expect
        .element(page.getByRole('link', { name: 'Import a recipe' }))
        .toHaveAttribute('href', '/recipes/import');
      expect(page.getByRole('link', { name: /^Carry on/ }).elements()).toHaveLength(3);
      await expect
        .element(
          page.getByText(
            'Anyone in your household can carry on with a draft. Nothing here is in your recipes or ingredients until it’s saved.'
          )
        )
        .toBeVisible();
      await expect
        .element(
          page.getByText(
            'Imports your household hasn’t finished · kept for 15 days, then deleted quietly'
          )
        )
        .toBeVisible();
    });
  });

  describe('when there is nothing, or no connection', () => {
    it('says there are no drafts', async () => {
      await open({ 'GET /recipes/drafts': list([]) });
      await expect.element(page.getByRole('heading', { name: 'No drafts' })).toBeVisible();
      await expect
        .element(
          page.getByText(
            'When you import a recipe and leave before saving it, it waits here for 15 days.'
          )
        )
        .toBeVisible();
    });

    it('says it needs the server when it is offline and nothing was loaded', async () => {
      network.offline = true;
      network.deviceOffline = true;
      await open({});
      await expect.element(page.getByText(/Drafts needs your Mealwright server/)).toBeVisible();
    });

    it('says what went wrong, with Try again', async () => {
      const requests = await open({
        'GET /recipes/drafts': [500, { detail: 'Something went wrong.' }]
      });
      await expect.element(page.getByText('Something went wrong.')).toBeVisible();
      fakeApi({ 'GET /recipes/drafts': list(THREE) });
      await page.getByRole('button', { name: 'Try again' }).click();
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      expect(requests.length).toBeGreaterThan(0);
    });

    it('goes offline after loading: what was loaded stays, with a note that it can’t be changed', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      network.offline = true;
      network.deviceOffline = true;
      flushSync();
      await expect.element(page.getByText(/This is as it was when you last looked/)).toBeVisible();
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      // It can't be changed until the connection is back.
      await expect.element(page.getByRole('button', { name: 'Delete Rava dosa' })).toBeDisabled();
      await expect
        .element(page.getByRole('button', { name: 'Save recipe Aloo paratha' }))
        .toBeDisabled();
    });
  });
  describe('from Mealie (0.9.5)', () => {
    const MEALIE = [
      draft({
        id: 11,
        name: 'Green curry',
        source: { kind: 'mealie', site: null },
        started_by: 'Sam',
        lines_total: 8,
        lines_checked: 6,
        waiting: ['1 tin coconut milk (optional)', 'salt to taste']
      }),
      draft({
        id: 12,
        name: 'Shakshuka',
        source: { kind: 'mealie', site: null },
        started_by: 'Sam',
        lines_total: 7,
        lines_checked: 4,
        waiting: ['2 tins tomatoes or 6 fresh', 'a pinch of chilli', 'feta, to serve']
      })
    ];

    it('has no chips when no draft came from Mealie', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      expect(page.getByRole('group', { name: 'Show' }).elements()).toEqual([]);
    });

    it('From Mealie shows only those, the lines each waits on, and Save all', async () => {
      await open({ 'GET /recipes/drafts': list([...THREE, ...MEALIE]) }, 390, true);
      await expect.element(page.getByRole('button', { name: 'All 5' })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'From Mealie 2' }))
        .toHaveAttribute('aria-pressed', 'true');
      await expect.element(page.getByText('Green curry')).toBeVisible();
      await expect.element(page.getByText('Chettinad kuzhambu')).not.toBeInTheDocument();
      // The phone quotes two lines, then "…".
      await expect
        .element(page.getByText('“1 tin coconut milk (optional)”, “salt to taste”'))
        .toBeVisible();
      await expect
        .element(page.getByText('“2 tins tomatoes or 6 fresh”, “a pinch of chilli”, …'))
        .toBeVisible();
      await expect.element(page.getByText(/Open one to check its lines/)).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Save all 2 as they are' }))
        .toBeVisible();

      await page.getByRole('button', { name: 'All 5' }).click();
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Save all 2 as they are' }))
        .not.toBeInTheDocument();
    });

    it('From Mealie gives a member no Save all (the server refuses them), but the drafts open', async () => {
      session.me = { ...ME, role: 'member' };
      await open({ 'GET /recipes/drafts': list([...THREE, ...MEALIE]) }, 390, true);
      await expect.element(page.getByText('Green curry')).toBeVisible();
      await expect.element(page.getByText(/Open one to check its lines/)).toBeVisible();
      expect(page.getByRole('button', { name: /^Save all/ }).elements()).toEqual([]);
    });

    it('the From Mealie chip and Save all write a count over a thousand with its comma', async () => {
      const many = Array.from({ length: 1250 }, (_, i) => ({ ...MEALIE[0]!, id: 1000 + i }));
      await open({ 'GET /recipes/drafts': list(many) }, 390, true);
      await expect.element(page.getByRole('button', { name: 'From Mealie 1,250' })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: 'Save all 1,250 as they are' }))
        .toBeVisible();
    });

    it('Links shows only the drafts from a link (mockup Dark-MealieCheck095-Phone)', async () => {
      await open({ 'GET /recipes/drafts': list([...THREE, ...MEALIE]) });
      await expect.element(page.getByRole('button', { name: 'All 5' })).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'From Mealie 2' })).toBeVisible();
      await page.getByRole('button', { name: 'Links 2' }).click();
      await expect
        .element(page.getByRole('button', { name: 'Links 2' }))
        .toHaveAttribute('aria-pressed', 'true');
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      await expect.element(page.getByText('Aloo paratha')).toBeVisible();
      // Pasted text and Mealie drafts are under All, not Links.
      await expect.element(page.getByText('Rava dosa')).not.toBeInTheDocument();
      await expect.element(page.getByText('Green curry')).not.toBeInTheDocument();
      await expect
        .element(page.getByRole('button', { name: 'Save all 2 as they are' }))
        .not.toBeInTheDocument();
    });

    it('has no Links chip when no draft came from a link', async () => {
      await open({ 'GET /recipes/drafts': list(MEALIE) });
      await expect.element(page.getByRole('button', { name: 'From Mealie 2' })).toBeVisible();
      expect(page.getByRole('button', { name: /^Links/ }).elements()).toEqual([]);
    });

    it('Save all saves them on the server, then shows what is left', async () => {
      let saved = false;
      const requests = await open(
        {
          'GET /recipes/drafts': () => list(saved ? THREE : [...THREE, ...MEALIE]),
          'POST /mealie-imports/drafts/save-all': () => {
            saved = true;
            return [200, { saved: 2 }];
          }
        },
        390,
        true
      );
      await page.getByRole('button', { name: 'Save all 2 as they are' }).click();
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      await expect.element(page.getByText('Green curry')).not.toBeInTheDocument();
      expect(page.getByRole('group', { name: 'Show' }).elements()).toEqual([]);
      expect(requests.filter((r) => r.path === '/mealie-imports/drafts/save-all').length).toBe(1);
    });

    it('Save all says why the server refused, and keeps the drafts', async () => {
      await open(
        {
          'GET /recipes/drafts': list(MEALIE),
          'POST /mealie-imports/drafts/save-all': [409, { detail: 'Not now.' }]
        },
        390,
        true
      );
      await page.getByRole('button', { name: 'Save all 2 as they are' }).click();
      await expect.element(page.getByRole('alert')).toHaveTextContent('Not now.');
      await expect.element(page.getByText('Green curry')).toBeVisible();
    });

    it('on a computer the From cell says Mealie, a line and how many more', async () => {
      await open({ 'GET /recipes/drafts': list(MEALIE) }, 1300, true);
      await expect.element(page.getByText('Shakshuka')).toBeVisible();
      await expect
        .element(page.getByText(/“2 tins tomatoes or 6 fresh”, “a pinch of chilli”, and 1 more/))
        .toBeVisible();
    });

    it('keeps a recipe name’s words whole when the From lines are long (narrow computer)', async () => {
      const long = draft({
        id: 13,
        name: 'Minestrone',
        source: { kind: 'mealie', site: null },
        started_by: 'Sam',
        lines_total: 10,
        lines_checked: 6,
        waiting: [
          'a handful of whatever is in the garden',
          'parmesan rind',
          'olive oil, a good glug',
          'bread, to serve'
        ]
      });
      await open({ 'GET /recipes/drafts': list([...MEALIE, long]) }, 800, true);
      const name = page.getByRole('rowheader', { name: 'Minestrone' });
      await expect.element(name).toBeVisible();
      // One line box for the one word: it isn't broken mid-word.
      const range = document.createRange();
      range.selectNodeContents(name.element());
      const lines = new Set([...range.getClientRects()].map((rect) => Math.round(rect.top)));
      expect(lines.size).toBe(1);
    });

    // F267, F270 (hand test 20 Nov): at 1019 px with the menu folded the table ran past the
    // window's edge and Delete was cut off; with it open From was squeezed to "Meali / e" in rows
    // 445 px tall. Each room the app gives the list (the window, less the 248 px menu or the
    // 72 px folded one, less 2 × 40 px margins) now fits: cards below 48rem, the table above.
    // F253 still holds: a button's words stay on one line.
    for (const [width, where, shown] of [
      [440, '768 px, menu open', 'cards'],
      [616, '768 px, menu folded', 'cards'],
      [691, '1019 px, menu open', 'cards'],
      [867, '1019 px, menu folded', 'table'],
      [896, '1224 px, menu open', 'table'],
      [944, '1272 px, menu open', 'table'],
      [952, '1280 px, menu open', 'table'],
      [1088, '1240 px, menu folded', 'table']
    ] as const) {
      it(`F267, F270, F253: at ${where} (${width} px of room) the ${shown} fit, Delete shows and the buttons keep their words whole`, async () => {
        await page.viewport(1440, 844);
        const long = draft({
          id: 15,
          name: 'Slow-cooker chicken tikka masala',
          source: { kind: 'mealie', site: null },
          started_by: 'Samantha',
          lines_total: 14,
          lines_checked: 3,
          waiting: ['2 tablespoons garam masala, or to taste', 'a thumb of ginger, grated']
        });
        fakeApi({ 'GET /recipes/drafts': list([...MEALIE, long, ...THREE]) });
        const room = document.body.appendChild(document.createElement('div'));
        room.style.width = `${width}px`;
        component = mount(DraftsScreen, { target: room, props: { fromMealie: false } });
        flushSync();
        await expect
          .element(page.getByRole('button', { name: /^Delete Slow-cooker/ }))
          .toBeVisible();
        const table = page.getByRole('table', { name: 'Drafts' }).elements();
        const cards = page.getByRole('list', { name: 'Drafts' }).elements();
        expect(shown === 'table' ? table : cards).toHaveLength(1);
        expect(shown === 'table' ? cards : table).toHaveLength(0);
        // On a computer the cards have no swipes: those are a phone's.
        expect(room.querySelectorAll('.swipe')).toHaveLength(0);
        const box = document.querySelector<HTMLElement>(
          shown === 'table' ? '.tablebox' : '.cards'
        )!;
        expect(box.scrollWidth, 'nothing scrolls sideways').toBeLessThanOrEqual(box.clientWidth);
        const edge = room.getBoundingClientRect().right + 0.5;
        const buttons = [...room.querySelectorAll<HTMLElement>('.carry, .delete, .save')].filter(
          (button) => !button.closest('.act')
        );
        expect(buttons.length).toBe(13);
        for (const button of buttons) {
          expect(
            button.getBoundingClientRect().right,
            `${button.textContent} inside`
          ).toBeLessThanOrEqual(edge);
          const range = document.createRange();
          range.selectNodeContents(button);
          const lines = new Set([...range.getClientRects()].map((rect) => Math.round(rect.top)));
          expect(lines.size, `${button.textContent} on one line`).toBe(1);
        }
        // "Mealie" under From is never broken in two, and no row is hundreds of pixels tall.
        const mealie = [...room.querySelectorAll<HTMLElement>('td.from')].filter(
          (cell) => cell.firstChild?.textContent === 'Mealie'
        );
        expect(mealie).toHaveLength(shown === 'table' ? 3 : 0);
        for (const from of mealie) {
          const range = document.createRange();
          range.setStart(from.firstChild!, 0);
          range.setEnd(from.firstChild!, from.firstChild!.textContent!.length);
          const lines = new Set([...range.getClientRects()].map((rect) => Math.round(rect.top)));
          expect(lines.size, `${from.firstChild!.textContent} on one line`).toBe(1);
        }
        for (const row of room.querySelectorAll<HTMLElement>('tbody tr')) {
          // The hand test's rows were 445 px tall; a Mealie row's From lines now take a few lines.
          expect(row.getBoundingClientRect().height).toBeLessThan(260);
          // F246: with room for them a row's buttons sit on one line (with these long From
          // lines, from 1088 px; with short ones from 1280 px with the menu open, drafts.spec.ts).
          if (width < 1088) continue;
          const tops = [...row.querySelectorAll<HTMLElement>('.carry, .delete, .save')].map((b) =>
            Math.round(b.getBoundingClientRect().top)
          );
          expect(new Set(tops).size, `${row.querySelector('th')!.textContent} buttons`).toBe(1);
        }
      });
    }

    it('F246, F267: at 1280 px with the menu open the buttons sit on one line; with the text at 200% the drafts become cards', async () => {
      await page.viewport(1440, 844);
      fakeApi({
        'GET /recipes/drafts': list([{ ...THREE[0]!, lines_checked: 9, lines_total: 9 }, THREE[1]!])
      });
      const room = document.body.appendChild(document.createElement('div'));
      room.style.width = '952px';
      component = mount(DraftsScreen, { target: room, props: { fromMealie: false } });
      flushSync();
      const save = page.getByRole('button', { name: /^Save recipe/ });
      await expect.element(save).toBeVisible();
      const tops = [
        ...room.querySelectorAll<HTMLElement>('tbody tr:first-child :is(.carry, .delete, .save)')
      ].map((button) => Math.round(button.getBoundingClientRect().top));
      expect(tops).toHaveLength(3);
      expect(new Set(tops).size).toBe(1);
      expect(room.querySelector('tbody th')!.getBoundingClientRect().width).toBeGreaterThanOrEqual(
        190
      );
      try {
        document.documentElement.style.fontSize = '200%';
        await expect.element(page.getByRole('list', { name: 'Drafts' })).toBeVisible();
        expect(page.getByRole('table', { name: 'Drafts' }).elements()).toHaveLength(0);
        const box = room.querySelector<HTMLElement>('.cards')!;
        expect(box.scrollWidth).toBeLessThanOrEqual(box.clientWidth);
      } finally {
        document.documentElement.style.fontSize = '';
      }
      await expect.element(page.getByRole('table', { name: 'Drafts' })).toBeVisible();
    });
  });

  describe('the By recipe | By ingredient switch', () => {
    it('shows only while Mealie drafts wait, and opens By ingredient', async () => {
      await open({ 'GET /recipes/drafts': list(THREE) });
      await expect.element(page.getByText('Chettinad kuzhambu')).toBeVisible();
      expect(page.getByRole('button', { name: 'By ingredient' }).elements()).toHaveLength(0);
      unmount(component!);
      component = null;
      document.body.innerHTML = '';
      const requests = await open({
        'GET /recipes/drafts': list([
          draft({ id: 50, name: 'Minestrone', source: { kind: 'mealie', site: null } })
        ]),
        'GET /recipes/drafts/by-food': [
          200,
          { groups: [], total: 0, drafts: 0, recipes_ready: 0, places: [] }
        ]
      });
      await page.getByRole('button', { name: 'By ingredient' }).click();
      await expect.element(page.getByText('Every ingredient is answered')).toBeVisible();
      expect(requests.some((r) => r.path === '/recipes/drafts/by-food')).toBe(true);
      await page.getByRole('button', { name: 'By recipe' }).click();
      await expect.element(page.getByRole('button', { name: 'By ingredient' })).toBeVisible();
    });
  });
});
