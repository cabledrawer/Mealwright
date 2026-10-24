import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { DraftBrief, DraftOut } from '$lib/client/drafts';
import { drafts } from '$lib/drafts.svelte';
import { network } from '$lib/network.svelte';
import { fakeApi, changeOf } from '$lib/testing/fakeApi';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
import DraftsScreen from './DraftsScreen.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

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

  async function open(routes: Parameters<typeof fakeApi>[0], width = 390) {
    await page.viewport(width, 844);
    const requests = fakeApi(routes);
    component = mount(DraftsScreen, { target: document.body });
    flushSync();
    return requests;
  }

  beforeEach(() => {
    network.reset();
    drafts.forget();
    undoHistory.clear();
    toasts.dismiss();
    nav.goto.mockReset();
  });

  afterEach(() => {
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
      await expect
        .element(page.getByText('From bbcgoodfood.com · started by Tess'))
        .toBeVisible();
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
});
