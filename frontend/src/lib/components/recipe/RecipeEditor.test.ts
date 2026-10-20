import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { network } from '$lib/network.svelte';
import { fakeApi, type FakeRequest } from '$lib/testing/fakeApi';
import { toasts } from '$lib/toast.svelte';
import { undoHistory } from '$lib/undo.svelte';
import RecipeEditor from './RecipeEditor.svelte';
import '$lib/styles/tokens.css';
import '$lib/styles/base.css';

const navigation = vi.hoisted(() => ({ go: vi.fn(async () => {}), beforeNavigate: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: navigation.beforeNavigate }));
vi.mock('$lib/recipes/paths', async (original) => ({
  ...(await original<typeof import('$lib/recipes/paths')>()),
  go: navigation.go
}));

let component: ReturnType<typeof mount> | null = null;

beforeEach(() => {
  navigation.go.mockClear();
  toasts.dismiss();
  undoHistory.clear();
  network.reset();
});

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
});

function open(props: { recipeId?: number } = {}) {
  component = mount(RecipeEditor, { target: document.body, props });
  flushSync();
}

const saved = (over: Record<string, unknown> = {}) => ({
  id: 12,
  name: 'Rasam',
  version: 1,
  lines: [],
  steps: [],
  ...over
});

const bodyOf = (requests: FakeRequest[], method: string) =>
  requests.find((r) => r.method === method && r.path.startsWith('/recipes'))?.body as Record<
    string,
    unknown
  >;

describe('a new recipe', () => {
  it('starts at Serves 4, saves only with a name, then says Saved and goes to the recipe', async () => {
    const requests = fakeApi({
      'POST /recipes': [201, saved()]
    });
    open();
    const save = page.getByRole('button', { name: /^Save/ });
    await expect.element(save).toBeDisabled();
    await expect.element(page.getByRole('group', { name: 'Serves' })).toHaveTextContent('− 4 +');
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await expect.element(save).toBeEnabled();
    await save.click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    expect(toasts.current?.message).toBe('Saved');
    const body = bodyOf(requests, 'POST');
    expect(body).toMatchObject({ name: 'Rasam', serves: 4, lines: [], steps: [] });
    expect('photo_id' in body).toBe(false);
  });

  it('Cancel with a typed name closes at once, with "Changes not saved" and Undo', async () => {
    fakeApi({});
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Half');
    await page.getByRole('button', { name: 'Cancel' }).click();
    expect(navigation.go).toHaveBeenCalledWith('/recipes');
    expect(undoHistory.size).toBe(1);
    expect(toasts.current).toMatchObject({
      message: 'Changes not saved',
      action: { label: 'Undo' }
    });
  });

  it('Cancel with nothing typed just closes', async () => {
    fakeApi({});
    open();
    await page.getByRole('button', { name: 'Cancel' }).click();
    expect(navigation.go).toHaveBeenCalledWith('/recipes');
    expect(toasts.current).toBeNull();
  });

  it('keeps what was typed when offline, and greys out Save with the reason', async () => {
    fakeApi({});
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Typed offline');
    network.offline = true;
    await expect
      .element(page.getByText('You’re offline. Save when you’re back online.'))
      .toBeVisible();
    await expect.element(page.getByRole('button', { name: /^Save/ })).toBeDisabled();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Typed offline');
  });

  it('says "Couldn’t save. Try again." when the server can’t be reached', async () => {
    fakeApi({ 'POST /recipes': [503, { detail: 'down' }] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await page.getByRole('button', { name: /^Save/ }).click();
    await expect.element(page.getByText('Couldn’t save. Try again.')).toBeVisible();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Rasam');
  });

  it('turns Made ahead on with the name that is already an ingredient: says it will be linked', async () => {
    fakeApi({
      'GET /foods': [200, { foods: [{ id: 4, name: 'Dosa batter', other_names: [] }] }]
    });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('dosa batter');
    await page.getByRole('switch', { name: 'Made ahead (keeps in the pantry)' }).click();
    await expect
      .element(
        page.getByText(
          'Dosa batter is already in Ingredients. It will be linked to this recipe, and its pantry stock stays.'
        ),
        { timeout: 4000 }
      )
      .toBeVisible();
  });
});

describe('the boxes', () => {
  it('adds tags with Enter or a comma, suggests used ones, and takes one off', async () => {
    fakeApi({ 'GET /recipes/tags': [200, { tags: [{ name: 'Batch-friendly', recipes: 3 }] }] });
    open();
    const box = page.getByRole('textbox', { name: /^Tags/ });
    await box.fill('Quick');
    await userEvent.keyboard('{Enter}');
    await box.fill('Kids,');
    await userEvent.keyboard('{Enter}');
    await expect.element(page.getByRole('button', { name: 'Remove tag Quick' })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Remove tag Kids' })).toBeVisible();
    await box.click();
    await page.getByRole('button', { name: 'Batch-friendly' }).click();
    await expect
      .element(page.getByRole('button', { name: 'Remove tag Batch-friendly' }))
      .toBeVisible();
    await page.getByRole('button', { name: 'Remove tag Quick' }).click();
    await expect
      .element(page.getByRole('button', { name: 'Remove tag Quick' }))
      .not.toBeInTheDocument();
  });

  it('keeps Serves between 1 and 99, and can clear it', async () => {
    fakeApi({});
    open();
    const group = page.getByRole('group', { name: 'Serves' });
    await page.getByRole('button', { name: 'More servings' }).click();
    await expect.element(group).toHaveTextContent('− 5 +');
    await page.getByRole('button', { name: 'Clear (for a batter or a powder)' }).click();
    await expect.element(group).toHaveTextContent('− – +');
    await expect.element(page.getByRole('button', { name: 'Fewer servings' })).toBeDisabled();
    await page.getByRole('button', { name: 'More servings' }).click();
    await expect.element(group).toHaveTextContent('− 4 +');
  });

  it('uploads a picked photo at once, shows it, and sends its id', async () => {
    const sent: { method: string; url: string; body: unknown; type: string | null }[] = [];
    vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
      const url = String(input).replace('/api/v1', '');
      const headers = init.headers as Record<string, string> | undefined;
      sent.push({
        method: init.method ?? 'GET',
        url,
        body: init.body,
        type: headers?.['content-type'] ?? null
      });
      if (url === '/recipes/photos' && init.method === 'POST') {
        return new Response(
          JSON.stringify({
            id: 5,
            width: 2,
            height: 2,
            url: '/api/v1/recipes/photos/5/large',
            list_width: 2,
            list_height: 2,
            list_url: '/api/v1/recipes/photos/5/list'
          }),
          { status: 201 }
        );
      }
      if (url === '/recipes' && init.method === 'POST') {
        return new Response(JSON.stringify({ id: 12 }), { status: 201 });
      }
      return new Response('{}', { status: 404 });
    });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Photo');
    const file = new File([new Uint8Array([1, 2, 3])], 'dish.png', { type: 'image/png' });
    await userEvent.upload(document.querySelector<HTMLInputElement>('input[type=file]')!, file);
    await expect.element(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
    const upload = sent.find((r) => r.url === '/recipes/photos')!;
    expect(upload.body).toBeInstanceOf(File); // the file itself, not a form
    expect(upload.type).toBe('image/png');
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalled());
    const created = sent.find((r) => r.url === '/recipes' && r.method === 'POST')!;
    expect(JSON.parse(String(created.body))).toMatchObject({ photo_id: 5 });
  });
});

describe('an existing recipe', () => {
  const sambar = {
    id: 2,
    name: 'Sambar',
    description: null,
    time_minutes: null,
    serves: 6,
    makes: null,
    made_ahead: false,
    homemade: null,
    tags: [],
    nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
    lines: [],
    steps: [],
    source_note: null,
    photo: null,
    used_by: [],
    version: 3,
    updated_at: '2026-10-19T18:04:11+00:00',
    updated_by: { login_id: 1, name: 'Tess' }
  };

  it('opens filled in; Save sends the version it opened, and Remove photo is not sent when the photo is untouched', async () => {
    const requests = fakeApi({
      'GET /recipes/2': [200, sambar],
      'GET /recipes/2/cannot-use': [200, { recipes: [] }],
      'PUT /recipes/2': [200, { ...sambar, version: 4 }]
    });
    open({ recipeId: 2 });
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Sambar');
    await page.getByRole('textbox', { name: /^Short description/ }).fill('Stew');
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/2'));
    expect(bodyOf(requests, 'PUT')).toMatchObject({
      version: 3,
      overwrite: false,
      description: 'Stew'
    });
    expect('photo_id' in bodyOf(requests, 'PUT')).toBe(false);
  });

  it('stops a second Save with the server’s sentence, and "Save mine anyway" sends the newer version', async () => {
    let tries = 0;
    const requests = fakeApi({
      'GET /recipes/2': [200, sambar],
      'GET /recipes/2/cannot-use': [200, { recipes: [] }],
      'PUT /recipes/2': () => {
        tries++;
        return tries === 1
          ? [
              409,
              {
                detail: 'Wren changed this recipe after you opened it.',
                code: 'recipe_changed',
                version: 5,
                changed_by: { login_id: 2, name: 'Wren' }
              }
            ]
          : [200, { ...sambar, version: 6 }];
      }
    });
    open({ recipeId: 2 });
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Sambar');
    await page.getByRole('textbox', { name: /^Short description/ }).fill('Mine');
    await page.getByRole('button', { name: /^Save/ }).click();
    await expect
      .element(page.getByText('Wren changed this recipe after you opened it.'))
      .toBeVisible();
    await expect.element(page.getByRole('button', { name: 'See Wren’s version' })).toBeVisible();
    expect(navigation.go).not.toHaveBeenCalled();
    await page.getByRole('button', { name: 'Save mine anyway' }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/2'));
    const puts = requests.filter((r) => r.method === 'PUT');
    expect(puts[1]!.body).toMatchObject({ version: 5, overwrite: true, description: 'Mine' });
  });

  it('says so when the recipe is not there', async () => {
    fakeApi({ 'GET /recipes/9': [404, { detail: 'That recipe isn’t here.' }] });
    open({ recipeId: 9 });
    await expect.element(page.getByText('That recipe isn’t here any more.')).toBeVisible();
  });
});
