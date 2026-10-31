import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import {
  PLACES,
  SHOPS,
  changeOf,
  fakeApi,
  rowOf,
  toorDal,
  type FakeRequest
} from '#lib/testing/fakeApi.js';
import { kitchen } from '#lib/freshness.svelte.js';
import { network } from '#lib/network.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import NewIngredient from '#lib/components/NewIngredient.svelte';
import { newIngredient } from '#lib/newIngredient.svelte.js';
import Ingredients from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

// The page's address: "Edit staples" on Pantry opens it with ?filter=staples.
const route = vi.hoisted(() => ({ search: '' }));
vi.mock('$app/state', () => ({
  page: {
    get url() {
      return new URL(`http://mealwright.test/recipes/ingredients${route.search}`);
    }
  }
}));

const dal = toorDal({ used_in_recipes: 5 });
const sticks = toorDal({
  id: 40,
  name: 'Drumsticks (moringa)',
  other_names: [],
  counted_as: 'count',
  maybe_same: [{ id: 12, name: 'Drumsticks', merge_into: 12, merge_this: true }]
});

describe('the Ingredients page', () => {
  let component: ReturnType<typeof mount> | null = null;
  let dialog: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[];

  beforeEach(() => {
    undoHistory.clear();
    toasts.dismiss();
    requests = fakeApi({
      'GET /foods': (request) => {
        const params = new URLSearchParams(request.url.split('?')[1]);
        const q = params.get('q');
        // Every ingredient is in a recipe, so “Not in any recipe” finds none.
        const foods = (params.get('filter') === 'unused' ? [] : [rowOf(sticks), rowOf(dal)]).filter(
          (f) => !q || f.name.toLowerCase().includes(q) || f.other_names.some((n) => n.includes(q))
        );
        return [
          200,
          {
            total: 2,
            counts: { all: 2, staples: 0, unused: 9, maybe_same: 2, maybe_same_pairs: 1 },
            foods,
            next: null
          }
        ];
      },
      'GET /foods/7': [200, dal],
      'GET /foods/50': [200, toorDal({ id: 50, name: 'Tahini', counted_as: 'count' })],
      'POST /foods': [
        201,
        {
          food: toorDal({ id: 50, name: 'Tahini', counted_as: 'count' }),
          change: changeOf(960, 'Added Tahini')
        }
      ],
      'GET /changes?limit=10&area=ingredients': [
        200,
        {
          changes: [
            changeOf(961, 'Toor dal is now a staple'),
            {
              ...changeOf(960, 'Added Tahini'),
              kind: 'food_created',
              can_undo: false,
              undone: { at: 'x', who: {} }
            },
            {
              ...changeOf(959, 'Merged Moong dal into Mung dal'),
              kind: 'merged',
              who: { login_id: 2, name: 'Wren' }
            }
          ],
          next: null
        }
      ],
      'POST /changes/961/undo': [
        200,
        {
          result: 'done',
          message: 'Undone.',
          change: changeOf(962, 'Undid: Toor dal is now a staple'),
          undone: changeOf(961, 'Toor dal is now a staple'),
          food: null,
          groups: [],
          brought_back: []
        }
      ],
      'GET /places': [200, PLACES],
      'GET /shops': [200, SHOPS],
      'POST /foods/40/merge': [
        200,
        {
          food: toorDal({ id: 12, name: 'Drumsticks' }),
          change: changeOf(950, 'Merged Drumsticks (moringa) into Drumsticks')
        }
      ]
    });
    component = mount(Ingredients, { target: document.body });
    dialog = mount(NewIngredient, { target: document.body });
    flushSync();
  });

  afterEach(() => {
    newIngredient.cancel();
    if (dialog) unmount(dialog);
    dialog = null;
    if (component) unmount(component);
    component = null;
    vi.unstubAllGlobals();
    network.reset();
  });

  it('a search that fails once the list has loaded keeps the list: no server note (F67 review)', async () => {
    await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
    vi.stubGlobal('fetch', () => Promise.resolve(new Response('', { status: 502 })));
    await page.getByRole('searchbox', { name: 'Search ingredients' }).fill('arhar');
    await vi.waitFor(() => expect(network.down).toBe(true));
    flushSync();
    await expect.element(page.getByRole('searchbox', { name: 'Search ingredients' })).toBeVisible();
    expect(document.body.textContent).not.toContain('Can’t reach your Mealwright server.');
  });

  it('lists every ingredient from the server, with its counts', async () => {
    await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
    await expect.element(page.getByText(/^2 ingredients · shared by/)).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Maybe the same · 1' })).toBeVisible();
  });

  it('searches by any name on the server', async () => {
    await page.getByRole('searchbox', { name: 'Search ingredients' }).fill('arhar');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?q=arhar&limit=50')).toBe(true)
    );
    await expect.element(page.getByRole('button', { name: /^Drumsticks/ })).not.toBeInTheDocument();
  });

  it('filters', async () => {
    await page.getByRole('button', { name: 'Staples' }).click();
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?filter=staples&limit=50')).toBe(true)
    );
  });

  it('says how many recipes use each ingredient, where there are any', async () => {
    // “5 recipes” on a phone row; a screen reader hears “Used in 5 recipes”.
    const row = page.getByRole('listitem').filter({ hasText: 'Toor dal' });
    await expect.element(row).toBeVisible();
    expect(row.element().textContent).toMatch(/Used in 5 recipes$/);
    const used = row.element().querySelector('.used')!.cloneNode(true) as HTMLElement;
    used.querySelector('.visually-hidden')!.remove();
    expect(used.textContent!.replace(/\s+/g, ' ').trim()).toBe('5 recipes');
    // A Maybe-the-same row has its Merge button there instead, as in the mockups; nothing is
    // said about an ingredient no recipe uses.
    const maybe = page.getByRole('listitem').filter({ hasText: 'Drumsticks (moringa)' });
    expect(maybe.getByText(/recipe/).elements()).toHaveLength(0);
  });

  it('“Not in any recipe · 9” is a filter beside Staples, and asks the server for it', async () => {
    const chip = page.getByRole('button', { name: 'Not in any recipe · 9' });
    await expect.element(chip).toBeVisible();
    const chips = Array.from(document.querySelectorAll('.filters button')).map((b) =>
      b.textContent?.trim()
    );
    expect(chips.slice(0, 3)).toEqual(['All', 'Staples', 'Not in any recipe · 9']);
    await expect.element(chip).toHaveAttribute('aria-pressed', 'false');
    await chip.click();
    await expect.element(chip).toHaveAttribute('aria-pressed', 'true');
    await vi.waitFor(() =>
      expect(requests.some((r) => r.url === '/foods?filter=unused&limit=50')).toBe(true)
    );
  });

  it('says so calmly when every ingredient is in a recipe', async () => {
    await page.getByRole('button', { name: 'Not in any recipe · 9' }).click();
    await expect.element(page.getByText('Every ingredient is in a recipe.')).toBeVisible();
  });

  it('Merge is greyed out while the server can’t be reached', async () => {
    const merge = page.getByRole('button', { name: 'Merge', exact: true });
    await expect.element(merge).toBeEnabled();
    network.offline = true;
    flushSync();
    try {
      await expect.element(merge).toBeDisabled();
    } finally {
      network.reset();
    }
  });

  it('Merge on a Maybe-the-same row merges straight away, with Undo', async () => {
    await page.getByRole('button', { name: 'Merge', exact: true }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.path === '/foods/40/merge')?.body).toMatchObject({
        into_id: 12
      })
    );
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Merged Drumsticks (moringa) into Drumsticks')
    );
    expect(toasts.current?.action?.label).toBe('Undo');
  });

  it('New ingredient asks How do you count it?, makes it and opens it', async () => {
    requests.length = 0;
    // A phone shows the round + (the words would squeeze the title); a computer the words.
    await expect
      .element(page.getByRole('button', { name: '+ New ingredient' }))
      .not.toBeInTheDocument();
    await page.getByRole('button', { name: 'New ingredient', exact: true }).click();
    await expect.element(page.getByRole('heading', { name: 'How do you count it?' })).toBeVisible();
    await page.getByRole('textbox', { name: 'Name' }).fill('Tahini');
    await page.getByRole('radio', { name: /One by one/ }).click();
    await page.getByRole('button', { name: 'Add', exact: true }).click();
    await vi.waitFor(() =>
      expect(requests.find((r) => r.method === 'POST' && r.path === '/foods')?.body).toEqual({
        name: 'Tahini',
        staple: false,
        counted_as: 'count'
      })
    );
  });

  describe('“+ New ingredient: …” in the search box (F97)', () => {
    const search = () => page.getByRole('searchbox', { name: 'Search ingredients' });
    const offer = (name: string) =>
      page.getByRole('button', { name: `+ New ingredient: “${name}”` });

    it('is offered when nothing has the typed name, and asks with the name filled in', async () => {
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
      await search().fill('tahini');
      await expect.element(offer('tahini')).toBeVisible();
      requests.length = 0;
      await offer('tahini').click();
      await expect
        .element(page.getByRole('heading', { name: 'How do you count it?' }))
        .toBeVisible();
      await expect.element(page.getByText('tahini', { exact: true }).last()).toBeVisible();
      await page.getByRole('radio', { name: /One by one/ }).click();
      await page.getByRole('button', { name: 'Add', exact: true }).click();
      await vi.waitFor(() =>
        expect(
          requests.find((r) => r.method === 'POST' && r.path === '/foods')?.body
        ).toMatchObject({
          name: 'tahini',
          counted_as: 'count'
        })
      );
      // The new ingredient is opened (as the button by the title does), and the search is cleared.
      await expect.element(search()).toHaveValue('');
    });

    it('is offered at the end of partial matches, but not for an exact name or other name', async () => {
      await search().fill('toor');
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect.element(offer('toor')).toBeVisible();
      await search().fill('  TOOR   dal ');
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
      await search().fill('arhar dal');
      await expect.element(page.getByRole('button', { name: /^Toor dal/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
    });

    it('offers nothing for a name the server found by folding accents and spaces', async () => {
      const pepper = toorDal({ id: 60, name: 'Jalapeño', other_names: [], counted_as: 'count' });
      const flakes = toorDal({
        id: 61,
        name: 'Chilli flakes',
        other_names: [],
        counted_as: 'count'
      });
      fakeApi({
        'GET /foods': (request) => {
          const q = new URLSearchParams(request.url.split('?')[1]).get('q') ?? '';
          const foods = q.includes('jalapeno') ? [rowOf(pepper)] : [rowOf(flakes)];
          return [
            200,
            {
              total: 2,
              counts: { all: 2, staples: 0, unused: 0, maybe_same: 0, maybe_same_pairs: 0 },
              foods,
              next: null
            }
          ];
        },
        'GET /places': [200, PLACES],
        'GET /shops': [200, SHOPS]
      });
      await search().fill('jalapeno');
      await expect.element(page.getByRole('button', { name: /^Jalapeño/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
      await search().fill('chilli  flakes');
      await expect.element(page.getByRole('button', { name: /^Chilli flakes/ })).toBeVisible();
      await expect
        .element(page.getByRole('button', { name: /^\+ New ingredient: / }))
        .not.toBeInTheDocument();
    });

    it('is hidden while the server can’t be reached, and with another filter', async () => {
      await search().fill('tahini');
      await expect.element(offer('tahini')).toBeVisible();
      network.offline = true;
      flushSync();
      try {
        await expect.element(offer('tahini')).not.toBeInTheDocument();
      } finally {
        network.reset();
      }
      await expect.element(offer('tahini')).toBeVisible();
      await page.getByRole('button', { name: 'Staples' }).click();
      await expect.element(offer('tahini')).not.toBeInTheDocument();
    });

    it('Enter with nothing found asks for the name, as Enter does in Shopping', async () => {
      await search().fill('tahini');
      await expect.element(offer('tahini')).toBeVisible();
      await search().click();
      await userEvent.keyboard('{Enter}');
      await expect
        .element(page.getByRole('heading', { name: 'How do you count it?' }))
        .toBeVisible();
      await expect.element(page.getByText('tahini', { exact: true }).last()).toBeVisible();
    });
  });

  it('a computer shows the words “+ New ingredient”, not the round +', async () => {
    await page.viewport(1300, 900);
    await expect.element(page.getByRole('button', { name: '+ New ingredient' })).toBeVisible();
    expect(
      page.getByRole('button', { name: 'New ingredient', exact: true }).elements()
    ).toHaveLength(0);
  });

  /** Desktop: the one-line bar above the editor, and what it opens. */
  const bar = () => page.getByRole('button', { name: /^Recent changes( · \d+\+?)?$/ });
  async function openList() {
    await page.viewport(1300, 900);
    await bar().click();
    return page.getByRole('region', { name: 'Recent changes' });
  }

  it('desktop: a “Recent changes · N” bar above the editor opens the list, and Close brings the editor back', async () => {
    await page.viewport(1300, 900);
    // Closed: the bar shows how many there are; the first ingredient's editor is open.
    await expect.element(bar()).toHaveTextContent('Recent changes · 3');
    await expect.element(page.getByRole('complementary', { name: /^Edit/ })).toBeVisible();
    expect(page.getByRole('region', { name: 'Recent changes' }).elements()).toHaveLength(0);
    // Open: the side column shows the list instead of the editor; focus goes to Close.
    await bar().click();
    const recent = page.getByRole('region', { name: 'Recent changes' });
    await expect.element(recent).toBeVisible();
    expect(page.getByRole('complementary', { name: /^Edit/ }).elements()).toHaveLength(0);
    await expect.element(recent.getByRole('button', { name: 'Close' })).toHaveFocus();
    // Close: the editor is back, and focus returns to the bar.
    await recent.getByRole('button', { name: 'Close' }).click();
    await expect.element(page.getByRole('complementary', { name: /^Edit/ })).toBeVisible();
    expect(page.getByRole('region', { name: 'Recent changes' }).elements()).toHaveLength(0);
    await expect.element(bar()).toHaveFocus();
  });

  it('desktop: opening an ingredient from the table while the list is open shows its editor', async () => {
    const recent = await openList();
    await expect.element(recent).toBeVisible();
    await page.getByRole('button', { name: /^Drumsticks \(moringa\)/ }).click();
    await expect.element(page.getByRole('complementary', { name: /^Edit/ })).toBeVisible();
    expect(page.getByRole('region', { name: 'Recent changes' }).elements()).toHaveLength(0);
  });

  it('desktop: Recent changes sits beside the list, with Undo for what can be undone', async () => {
    const recent = await openList();
    await expect.element(recent.getByRole('listitem').first()).toBeVisible();
    expect(recent.getByRole('listitem').elements()).toHaveLength(3);
    // "Toor dal is now a staple" starts with the ingredient, so nothing in it is bold; the
    // verbs of "Added …" and "Merged …" are, decided by the kind of change.
    expect(recent.getByRole('listitem').first().element().querySelector('b')).toBeNull();
    await expect.element(recent.getByText('Merged', { exact: true })).toBeVisible();
    await expect.element(recent.getByText('· Wren')).toBeVisible();
    // The phone's button isn't here: desktop has the bar.
    expect(
      page.getByRole('button', { name: 'Recent changes', exact: true }).elements()
    ).toHaveLength(0);
    // Undone already, so no Undo; the others have one.
    expect(recent.getByRole('button', { name: 'Undo: Added Tahini' }).elements()).toHaveLength(0);
    await recent.getByRole('button', { name: 'Undo: Toor dal is now a staple' }).click();
    await vi.waitFor(() => expect(requests.some((r) => r.path === '/changes/961/undo')).toBe(true));
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Undone: Toor dal is now a staple')
    );
    // And the list is fetched again, as after any change.
    const asked = () => requests.filter((r) => r.path === '/changes').length;
    await vi.waitFor(() => expect(asked()).toBeGreaterThan(1));
  });

  it('bold is decided by the kind of change, so “Added sugar” is never half bold', async () => {
    await page.viewport(1300, 900);
    fakeApi({
      'GET /changes?limit=10&area=ingredients': [
        200,
        {
          changes: [
            changeOf(971, 'Added sugar is now a staple'),
            { ...changeOf(970, 'Added Added sugar'), kind: 'food_created' },
            changeOf(969, 'Renamed Rice to Basmati rice'),
            changeOf(968, 'Renamed rice is now a staple')
          ],
          next: null
        }
      ]
    });
    kitchen.changed();
    const recent = await openList();
    await expect.element(recent.getByText('Added', { exact: true })).toBeVisible();
    const [staple, created, renamed, renamedSugar] = recent.getByRole('listitem').elements();
    // The ingredient is called "Added sugar": nothing of it is bold…
    expect(staple!.querySelector('b')).toBeNull();
    // …and in "Added Added sugar" only the verb is.
    expect(created!.querySelector('b')?.textContent).toBe('Added');
    // A rename starts with its verb; an ingredient called "Renamed rice" doesn't count.
    expect(renamed!.querySelector('b')?.textContent).toBe('Renamed');
    expect(renamedSugar!.querySelector('b')).toBeNull();
  });

  describe('the bar’s count', () => {
    const rows = (n: number) =>
      Array.from({ length: n }, (_, i) => changeOf(900 + i, `Added Thing ${i}`));
    async function withChanges(count: number, next: string | null, extra = {}) {
      await page.viewport(1300, 900);
      fakeApi({
        'GET /changes?limit=10&area=ingredients': [200, { changes: rows(count), next }],
        ...extra
      });
      kitchen.changed();
    }

    it('is the exact number up to 10', async () => {
      await withChanges(9, null);
      await expect.element(bar()).toHaveTextContent('Recent changes · 9');
      await withChanges(10, null);
      await expect.element(bar()).toHaveTextContent('Recent changes · 10');
      expect(bar().element().textContent).not.toContain('+');
    });

    it('reads 10+ when there are more than the list holds', async () => {
      await withChanges(10, '890');
      await expect.element(bar()).toHaveTextContent('Recent changes · 10+');
    });

    it('has no number when there is nothing yet', async () => {
      await withChanges(0, null);
      await vi.waitFor(() => expect(bar().element().textContent?.trim()).toBe('Recent changes'));
    });

    it('has no number while loading, or when the list could not be fetched', async () => {
      await page.viewport(1300, 900);
      fakeApi({ 'GET /changes?limit=10&area=ingredients': [500, { detail: 'Nope' }] });
      kitchen.changed();
      await vi.waitFor(() => expect(bar().element().textContent?.trim()).toBe('Recent changes'));
    });
  });

  it('desktop: Undo that the server refuses puts Undo back and says why', async () => {
    await page.viewport(1300, 900);
    fakeApi({
      'GET /changes?limit=10&area=ingredients': [
        200,
        { changes: [changeOf(961, 'Toor dal is now a staple')], next: null }
      ],
      'POST /changes/961/undo': [
        409,
        { detail: 'That is too old to undo.', code: 'too_old', title: 'Too old' }
      ]
    });
    kitchen.changed();
    const recent = await openList();
    await recent.getByRole('button', { name: 'Undo: Toor dal is now a staple' }).click();
    await vi.waitFor(() => expect(toasts.current?.tone).toBe('problem'));
    await expect
      .element(recent.getByRole('button', { name: 'Undo: Toor dal is now a staple' }))
      .toBeVisible();
  });

  it('phone: a Recent changes button opens a sheet with the same list', async () => {
    await page.viewport(390, 900);
    expect(page.getByRole('region', { name: 'Recent changes' }).elements()).toHaveLength(0);
    await page.getByRole('button', { name: 'Recent changes' }).click();
    const sheet = page.getByRole('dialog', { name: 'Recent changes' });
    expect(sheet.getByRole('listitem').elements()).toHaveLength(3);
    await sheet.getByRole('button', { name: 'Undo: Toor dal is now a staple' }).click();
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Undone: Toor dal is now a staple')
    );
    await sheet.getByRole('button', { name: 'Close' }).click();
    await vi.waitFor(() =>
      expect(
        [...document.querySelectorAll('dialog')].find(
          (d) => d.querySelector('h2')?.textContent === 'Recent changes'
        )?.open
      ).toBe(false)
    );
  });

  it('Recent changes is fetched again when something changed', async () => {
    const asked = () => requests.filter((r) => r.path === '/changes').length;
    const before = asked();
    kitchen.changed();
    await vi.waitFor(() => expect(asked()).toBeGreaterThan(before));
  });

  it('opens with the Staples filter when Pantry’s Edit staples link asked for it', async () => {
    unmount(component!);
    document.body.innerHTML = '';
    requests.length = 0;
    route.search = '?filter=staples';
    try {
      component = mount(Ingredients, { target: document.body });
      flushSync();
      await vi.waitFor(() =>
        expect(requests.some((r) => r.url === '/foods?filter=staples&limit=50')).toBe(true)
      );
      await expect
        .element(page.getByRole('button', { name: 'Staples', exact: true }))
        .toHaveAttribute('aria-pressed', 'true');
    } finally {
      route.search = '';
    }
  });
});
