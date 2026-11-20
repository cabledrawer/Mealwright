import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import { network } from '#lib/network.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import RecipeEditor from './RecipeEditor.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const navigation = vi.hoisted(() => ({ go: vi.fn(async () => {}), beforeNavigate: vi.fn() }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: navigation.beforeNavigate }));
vi.mock('#lib/recipes/paths.js', async (original) => ({
  ...(await original<typeof import('#lib/recipes/paths.js')>()),
  go: navigation.go
}));

let component: ReturnType<typeof mount> | null = null;

beforeEach(() => {
  sessionStorage.clear();
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
  sessionStorage.clear();
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

  it('says under Source that a web address is a link you open yourself', async () => {
    fakeApi({});
    open();
    const source = page.getByRole('textbox', { name: /Source/ });
    await expect
      .element(
        page.getByText(
          'A web address shows as a link you can open yourself. Mealwright never visits it.'
        )
      )
      .toBeVisible();
    // The hint is read out with the box.
    await expect.element(source).toHaveAccessibleDescription(/Mealwright never visits it/);
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
    network.deviceOffline = true;
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

  it('a double click on Save sends one request', async () => {
    const requests = fakeApi({ 'POST /recipes': [201, saved()] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await userEvent.dblClick(page.getByRole('button', { name: /^Save/ }));
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    expect(requests.filter((r) => r.method === 'POST')).toHaveLength(1);
  });

  /**
   * Like the server: the first request with a key is made but its answer is lost on the way;
   * the same key again answers with what was made then, whatever the body (history.py
   * `replayed` compares only the method and path). A new key makes another recipe.
   */
  function lostOnce() {
    const made = new Map<string, Record<string, unknown>>();
    let next = 12;
    const keyOf = (r: FakeRequest) => r.headers['idempotency-key']!;
    return fakeApi({
      'POST /recipes': (r) => {
        const earlier = made.get(keyOf(r));
        if (earlier) return [200, earlier];
        made.set(keyOf(r), saved({ id: next++, ...(r.body as object) }));
        return made.size === 1
          ? [503, { detail: 'The answer got lost.' }]
          : [201, made.get(keyOf(r))];
      },
      'PUT /recipes/12': (r) => [200, saved({ ...(r.body as object), version: 2 })]
    });
  }

  it('"Try again" after a lost answer sends the same request key, so it is made once', async () => {
    const requests = lostOnce();
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await page.getByRole('button', { name: /^Save/ }).click();
    await page.getByRole('button', { name: 'Try again' }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    const posts = requests.filter((r) => r.method === 'POST');
    expect(posts).toHaveLength(2);
    expect(posts[1]!.headers['idempotency-key']).toBe(posts[0]!.headers['idempotency-key']);
    expect(requests.some((r) => r.method === 'PUT')).toBe(false);
  });

  it('an edit after a lost answer is never saved as a second recipe, and is never lost', async () => {
    const requests = lostOnce();
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await page.getByRole('button', { name: /^Save/ }).click();
    await expect.element(page.getByText('Couldn’t save. Try again.')).toBeVisible();
    await page.getByRole('textbox', { name: 'Name' }).fill('Tomato rasam');
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    const posts = requests.filter((r) => r.method === 'POST');
    // The same request again (same key, same body): the server answers with recipe 12 ...
    expect(posts).toHaveLength(2);
    expect(posts[1]!.headers['idempotency-key']).toBe(posts[0]!.headers['idempotency-key']);
    expect(posts[1]!.body).toEqual(posts[0]!.body);
    // ... and the edit is saved on top of it, as its own change.
    const put = requests.find((r) => r.method === 'PUT')!;
    expect(put.path).toBe('/recipes/12');
    expect(put.body).toMatchObject({ name: 'Tomato rasam', version: 1, overwrite: false });
    expect(put.headers['idempotency-key']).not.toBe(posts[0]!.headers['idempotency-key']);
  });

  it('a clear refusal is not a lost answer: after it, an edit is sent as a new request', async () => {
    let first = true;
    const requests = fakeApi({
      'POST /recipes': () => {
        if (!first) return [201, saved()];
        first = false;
        return [422, { code: 'too_long', detail: 'That name is too long.' }];
      }
    });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await page.getByRole('button', { name: /^Save/ }).click();
    await expect.element(page.getByText('That name is too long.')).toBeVisible();
    await page.getByRole('textbox', { name: 'Name' }).fill('Tomato rasam');
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    const posts = requests.filter((r) => r.method === 'POST');
    expect(posts[1]!.body).toMatchObject({ name: 'Tomato rasam' });
    expect(posts[1]!.headers['idempotency-key']).not.toBe(posts[0]!.headers['idempotency-key']);
  });

  it('greys out "Try again" while offline, as Save is', async () => {
    fakeApi({ 'POST /recipes': [503, { detail: 'down' }] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await page.getByRole('button', { name: /^Save/ }).click();
    const again = page.getByRole('button', { name: 'Try again' });
    await expect.element(again).toBeEnabled();
    network.offline = true;
    network.deviceOffline = true;
    await expect.element(again).toBeDisabled();
    await expect.element(page.getByRole('button', { name: /^Save/ })).toBeDisabled();
    network.offline = false;
    await expect.element(again).toBeEnabled();
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

describe('carrying on where you left off', () => {
  const reopen = () => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    open();
  };

  it('a reload keeps a new recipe’s edits, with the line and Start over', async () => {
    fakeApi({});
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Half done');
    reopen();
    await expect.element(page.getByText('Carrying on where you left off')).toBeVisible();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Half done');
    await page.getByRole('button', { name: 'Start over' }).click();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('');
    expect(page.getByText('Carrying on where you left off').query()).toBeNull();
    reopen();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('');
    expect(page.getByText('Carrying on where you left off').query()).toBeNull();
  });

  it('Cancel clears it', async () => {
    fakeApi({});
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Half done');
    await page.getByRole('button', { name: 'Cancel' }).click();
    expect(sessionStorage.length).toBe(0);
  });

  it('Save clears it', async () => {
    fakeApi({ 'POST /recipes': [201, saved()] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    expect(sessionStorage.length).toBe(1);
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    expect(sessionStorage.length).toBe(0);
  });

  it('keeps nothing when nothing was changed', async () => {
    fakeApi({});
    open();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toBeVisible();
    expect(sessionStorage.length).toBe(0);
  });

  it('works when the tab cannot keep anything', async () => {
    fakeApi({});
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Still works');
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Still works');
    vi.restoreAllMocks();
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

  it('Enter on the last box adds a line once: a blank last line gets the focus instead of another', async () => {
    fakeApi({});
    open();
    const boxes = () => document.querySelectorAll('[aria-label^="Ingredient "][data-words]').length;
    await userEvent.click(page.getByRole('button', { name: '+ Add line' }));
    const added = boxes();
    expect(added).toBeGreaterThanOrEqual(1);
    const note = page.getByRole('textbox', { name: `Note for ingredient ${added}` });
    await userEvent.click(note);
    await userEvent.keyboard('{Enter}{Enter}');
    await userEvent.click(page.getByRole('button', { name: '+ Add line' }));
    expect(boxes()).toBe(added);
    await expect.element(page.getByRole('combobox', { name: `Ingredient ${added}` })).toHaveFocus();
  });

  it('a line reads Ingredient, Amount, Unit, Note, and Tab goes the same way (F36)', async () => {
    fakeApi({});
    open();
    await userEvent.click(page.getByRole('button', { name: '+ Add line' }));
    const first = document.querySelector('[data-line]')!;
    const labels = [...first.querySelectorAll('input, select')].map((e) =>
      e.getAttribute('aria-label')
    );
    expect(labels).toEqual([
      'Ingredient 1',
      'Amount for ingredient 1',
      'Unit for ingredient 1',
      'Note for ingredient 1'
    ]);
    // On the screen too: each box starts to the right of, or below, the one before.
    const boxes = labels.map((label) => first.querySelector(`[aria-label="${label}"]`)!);
    const at = boxes.map((box) => box.getBoundingClientRect());
    for (let i = 1; i < at.length; i++) {
      expect(at[i]!.left > at[i - 1]!.left || at[i]!.top > at[i - 1]!.top - 1).toBe(true);
    }
    await userEvent.click(page.getByRole('combobox', { name: 'Ingredient 1' }));
    for (const next of [
      'Amount for ingredient 1',
      'Unit for ingredient 1',
      'Note for ingredient 1'
    ]) {
      await userEvent.tab();
      expect(document.activeElement?.getAttribute('aria-label')).toBe(next);
    }
  });

  it('has an Optional switch on each line and each step, and Save sends them (R3)', async () => {
    const requests = fakeApi({ 'POST /recipes': [201, saved()] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await userEvent.click(page.getByRole('button', { name: '+ Add line' }));
    await page.getByRole('combobox', { name: 'Ingredient 1' }).fill('kewra water');
    await userEvent.click(page.getByRole('switch', { name: 'Optional: ingredient 1' }));
    await expect
      .element(page.getByRole('switch', { name: 'Optional: ingredient 1' }))
      .toBeChecked();
    await page.getByRole('textbox', { name: 'Step 1' }).fill('Top it.');
    await userEvent.click(page.getByRole('switch', { name: 'Optional: step 1' }));
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(bodyOf(requests, 'POST')).toBeDefined());
    const sent = bodyOf(requests, 'POST') as { lines: { optional: boolean }[]; steps: unknown[] };
    expect(sent.lines.map((l) => l.optional)).toEqual([true]);
    expect(sent.steps).toEqual([
      { kind: 'step', text: 'Top it.', optional: true, wait: null, timing: null }
    ]);
    expect('nutrition_checked' in sent).toBe(false);
  });

  it('has a Waits field on each step: add one, change it, Save sends it, take it off (M1)', async () => {
    const requests = fakeApi({ 'POST /recipes': [201, saved()] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Tandoori');
    await page.getByRole('textbox', { name: 'Step 1' }).fill('Rub it and leave to marinate.');
    await userEvent.click(page.getByRole('button', { name: 'Add a wait to step 1' }));
    await page.getByLabelText('Length, step 1', { exact: false }).fill('4');
    await page.getByLabelText('Longest (if it varies), step 1', { exact: false }).fill('12');
    await page.getByRole('combobox', { name: /^In\b.*step 1/ }).selectOptions('h');
    await page.getByRole('switch', { name: /^Ends overnight/ }).click();
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(bodyOf(requests, 'POST')).toBeDefined());
    const sent = bodyOf(requests, 'POST') as { steps: { wait: unknown }[] };
    expect(sent.steps[0]!.wait).toEqual({
      kind: 'marinate',
      min_minutes: 240,
      max_minutes: 720,
      overnight: true
    });
  });

  it('a step with no wait sends none, and Take off the wait clears it (M1)', async () => {
    const requests = fakeApi({ 'POST /recipes': [201, saved()] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Tandoori');
    await page.getByRole('textbox', { name: 'Step 1' }).fill('Rub it.');
    await userEvent.click(page.getByRole('button', { name: 'Add a wait to step 1' }));
    await userEvent.click(page.getByRole('button', { name: 'Take off the wait' }));
    await expect.element(page.getByRole('button', { name: 'Add a wait to step 1' })).toBeVisible();
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(bodyOf(requests, 'POST')).toBeDefined());
    const sent = bodyOf(requests, 'POST') as { steps: { wait: unknown }[] };
    expect(sent.steps[0]!.wait).toBeNull();
  });

  it('says a new step’s timing is guessed when it is saved, and sends none (Batch cook, B1)', async () => {
    const requests = fakeApi({ 'POST /recipes': [201, saved()] });
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Rasam');
    await page.getByRole('textbox', { name: 'Step 1' }).fill('Simmer for 10 minutes.');
    await expect.element(page.getByText('Guessed when you save')).toBeVisible();
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(bodyOf(requests, 'POST')).toBeDefined());
    const sent = bodyOf(requests, 'POST') as { steps: { timing: unknown }[] };
    expect(sent.steps[0]!.timing).toBeNull();
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

  it('asks what a count makes, "like dosas", only when the unit is count', async () => {
    fakeApi({});
    open();
    const word = page.getByRole('textbox', { name: 'What it makes' });
    await expect.element(word).not.toBeInTheDocument();
    await page.getByRole('combobox', { name: 'Makes unit' }).selectOptions('count');
    await expect.element(word).toHaveAttribute('placeholder', 'What it makes, like dosas');
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

describe('leaving while a photo is going up', () => {
  it('Cancel with nothing else typed still deletes the upload when it lands', async () => {
    const sent: string[] = [];
    let land: (answer: Response) => void = () => {};
    vi.stubGlobal('fetch', (input: string, init: RequestInit = {}) => {
      const call = `${init.method ?? 'GET'} ${String(input).replace('/api/v1', '')}`;
      sent.push(call);
      if (call === 'POST /recipes/photos') {
        return new Promise<Response>((resolve) => (land = resolve));
      }
      return Promise.resolve(
        new Response(call.startsWith('DELETE') ? null : '{}', {
          status: call.startsWith('DELETE') ? 204 : 404
        })
      );
    });
    open();
    const file = new File([new Uint8Array([1, 2, 3])], 'dish.png', { type: 'image/png' });
    await userEvent.upload(document.querySelector<HTMLInputElement>('input[type=file]')!, file);
    await expect.element(page.getByText('Uploading photo…')).toBeVisible();
    await page.getByRole('button', { name: 'Cancel' }).click();
    expect(navigation.go).toHaveBeenCalledWith('/recipes');
    land(
      new Response(
        JSON.stringify({
          id: 9,
          width: 2,
          height: 2,
          url: '/api/v1/recipes/photos/9/large',
          list_width: 2,
          list_height: 2,
          list_url: '/api/v1/recipes/photos/9/list'
        }),
        { status: 201 }
      )
    );
    await vi.waitFor(() => expect(sent).toContain('DELETE /recipes/photos/9'));
  });
});

describe('Undo after Cancel with a photo uploaded', () => {
  function server() {
    const sent: { call: string; body: unknown }[] = [];
    vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
      const call = `${init.method ?? 'GET'} ${String(input).replace('/api/v1', '')}`;
      sent.push({ call, body: init.body });
      if (call === 'POST /recipes/photos') {
        return new Response(
          JSON.stringify({
            id: 9,
            width: 2,
            height: 2,
            url: '/api/v1/recipes/photos/9/large',
            list_width: 2,
            list_height: 2,
            list_url: '/api/v1/recipes/photos/9/list'
          }),
          { status: 201 }
        );
      }
      if (call === 'DELETE /recipes/photos/9') return new Response(null, { status: 204 });
      if (call === 'POST /recipes')
        return new Response(JSON.stringify({ id: 12 }), { status: 201 });
      return new Response('{}', { status: 404 });
    });
    return sent;
  }

  async function cancelWithPhoto() {
    open();
    await page.getByRole('textbox', { name: 'Name' }).fill('Photo');
    const file = new File([new Uint8Array([1, 2, 3])], 'dish.png', { type: 'image/png' });
    await userEvent.upload(document.querySelector<HTMLInputElement>('input[type=file]')!, file);
    await expect.element(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
    await page.getByRole('button', { name: 'Cancel' }).click();
    expect(toasts.current?.message).toBe('Changes not saved');
  }

  const reopened = () => {
    unmount(component!);
    component = null;
    open();
  };

  it('keeps the upload while Undo can be used; after Undo, Save sends its id', async () => {
    const sent = server();
    await cancelWithPhoto();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(sent.some((r) => r.call.startsWith('DELETE'))).toBe(false);
    toasts.act(); // Undo
    reopened();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Photo');
    await expect.element(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    const created = sent.find((r) => r.call === 'POST /recipes')!;
    expect(JSON.parse(String(created.body))).toMatchObject({ photo_id: 9 });
    expect(sent.some((r) => r.call.startsWith('DELETE'))).toBe(false);
  });

  it('deletes the upload when the toast goes; a late Undo brings the editor back without it', async () => {
    const sent = server();
    await cancelWithPhoto();
    toasts.dismiss(); // timed out
    await vi.waitFor(() =>
      expect(sent.filter((r) => r.call.startsWith('DELETE')).map((r) => r.call)).toEqual([
        'DELETE /recipes/photos/9'
      ])
    );
    await undoHistory.undoLast(); // Ctrl+Z, long after
    reopened();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Photo');
    await expect.element(page.getByText('Add a photo')).toBeVisible();
    await page.getByRole('button', { name: /^Save/ }).click();
    await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/12'));
    const created = sent.find((r) => r.call === 'POST /recipes')!;
    expect('photo_id' in JSON.parse(String(created.body))).toBe(false);
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

  describe('the timing of a step, for Batch cook (B1; mockup Dark-BatchSteps08)', () => {
    const timed = (over: Record<string, unknown> = {}) => ({
      ...sambar,
      steps: [
        {
          id: 1,
          kind: 'step',
          text: 'Wash the toor dal and pressure cook it for 3 whistles.',
          optional: false,
          wait: null,
          timing: {
            hands: 'waiting',
            minutes: 15,
            equipment: 'pressure',
            hands_guessed: true,
            minutes_guessed: true,
            equipment_guessed: true
          },
          lines: []
        },
        {
          id: 2,
          kind: 'step',
          text: 'Chop the onion, tomato and drumsticks.',
          optional: false,
          wait: null,
          timing: {
            hands: 'hands',
            minutes: 8,
            equipment: 'none',
            hands_guessed: false,
            minutes_guessed: false,
            equipment_guessed: false
          },
          lines: []
        }
      ],
      ...over
    });
    const routes = (recipe = timed()) => ({
      'GET /recipes/2': [200, recipe] as [number, unknown],
      'GET /recipes/2/cannot-use': [200, { recipes: [] }] as [number, unknown],
      'PUT /recipes/2': [200, { ...recipe, version: 4 }] as [number, unknown]
    });

    it('shows each step’s tags: guessed in pink until set by hand, then "set by you"', async () => {
      fakeApi(routes());
      open({ recipeId: 2 });
      await expect.element(page.getByText('Waiting · 15\u00a0min')).toBeVisible();
      await expect.element(page.getByText('Pressure cooker', { exact: true })).toBeVisible();
      await expect.element(page.getByText('guessed', { exact: true })).toBeVisible();
      await expect.element(page.getByText('Hands-on · 8\u00a0min')).toBeVisible();
      await expect.element(page.getByText('set by you', { exact: true })).toBeVisible();
      // No tag for Nothing.
      expect(page.getByText('Nothing', { exact: true }).elements()).toHaveLength(0);
    });

    it('the "Waiting · 15 min" tag is a chip as wide as its words, like "Hands-on", never the full width (RF5)', async () => {
      fakeApi(routes());
      open({ recipeId: 2 });
      await expect.element(page.getByText('Waiting · 15\u00a0min')).toBeVisible();
      const waiting = page.getByText('Waiting · 15\u00a0min').element().getBoundingClientRect();
      const hands = page.getByText('Hands-on · 8\u00a0min').element().getBoundingClientRect();
      const step = page.getByText('Waiting · 15\u00a0min').element().closest('[data-timing]')!;
      expect(waiting.width).toBeLessThan(step.getBoundingClientRect().width * 0.6);
      expect(waiting.height).toBeLessThan(hands.height * 1.5);
    });

    it('a change takes all three as yours, and Save sends them; Guess again gives them back', async () => {
      const requests = fakeApi(routes());
      open({ recipeId: 2 });
      await page.getByRole('button', { name: 'Change the timing of step 1' }).click();
      await page.getByRole('radio', { name: 'Hands-on' }).click();
      await expect.element(page.getByText('Hands-on · 15\u00a0min')).toBeVisible();
      // Both steps are the person's now; none is a guess any more.
      expect(page.getByText('set by you', { exact: true }).elements()).toHaveLength(2);
      expect(page.getByText('guessed', { exact: true }).elements()).toHaveLength(0);
      await page.getByRole('textbox', { name: /^Minutes/ }).fill('12');
      await page.getByRole('radio', { name: 'Oven' }).click();
      await page.getByRole('button', { name: /^Save/ }).click();
      await vi.waitFor(() => expect(bodyOf(requests, 'PUT')).toBeDefined());
      const sent = bodyOf(requests, 'PUT') as { steps: { timing: unknown }[] };
      expect(sent.steps[0]!.timing).toEqual({ hands: 'hands', minutes: 12, equipment: 'oven' });
      // Step 2 was set by hand already and is sent as it was.
      expect(sent.steps[1]!.timing).toEqual({ hands: 'hands', minutes: 8, equipment: 'none' });
    });

    it('Guess again clears what was set by hand', async () => {
      const requests = fakeApi(routes());
      open({ recipeId: 2 });
      await page.getByRole('button', { name: 'Change the timing of step 2' }).click();
      await page.getByRole('button', { name: 'Guess again' }).click();
      await page.getByRole('button', { name: /^Save/ }).click();
      await vi.waitFor(() => expect(bodyOf(requests, 'PUT')).toBeDefined());
      const sent = bodyOf(requests, 'PUT') as { steps: { timing: unknown }[] };
      expect(sent.steps[1]!.timing).toBeNull();
    });

    it('a minutes box that is not a whole number blocks Save and says so', async () => {
      fakeApi(routes());
      open({ recipeId: 2 });
      await page.getByRole('button', { name: 'Change the timing of step 1' }).click();
      await page.getByRole('textbox', { name: /^Minutes/ }).fill('ten');
      await expect
        .element(page.getByText('Type the minutes as a whole number, such as 10.').first())
        .toBeVisible();
      await page.getByRole('button', { name: /^Save/ }).click();
      expect(navigation.go).not.toHaveBeenCalled();
    });

    it('a step whose words change says its guess is made again when saved', async () => {
      fakeApi(routes());
      open({ recipeId: 2 });
      await page.getByRole('textbox', { name: 'Step 1' }).fill('Simmer the dal.');
      await expect.element(page.getByText('Guessed when you save')).toBeVisible();
    });
  });

  it('opened from "Update nutrition" it starts in the nutrition boxes, and Save says they were looked at (R3)', async () => {
    const stale = { ...sambar, nutrition: { ...sambar.nutrition, possibly_out_of_date: true } };
    const requests = fakeApi({
      'GET /recipes/2': [200, stale],
      'GET /recipes/2/cannot-use': [200, { recipes: [] }],
      'PUT /recipes/2': [200, { ...sambar, version: 4 }]
    });
    history.replaceState(null, '', `${location.pathname}?nutrition=1`);
    try {
      open({ recipeId: 2 });
      await expect.element(page.getByRole('textbox', { name: 'kcal' })).toHaveFocus();
      await expect
        .element(page.getByText(/The ingredients changed after these were worked out/))
        .toBeVisible();
      await page.getByRole('button', { name: /^Save/ }).click();
      await vi.waitFor(() => expect(navigation.go).toHaveBeenCalledWith('/recipes/2'));
      expect(bodyOf(requests, 'PUT')).toMatchObject({ nutrition_checked: true });
    } finally {
      history.replaceState(null, '', location.pathname);
    }
  });

  it('a ?nutrition=1 link on a recipe whose figures are fine says nothing about them (R3)', async () => {
    fakeApi({
      'GET /recipes/2': [200, sambar],
      'GET /recipes/2/cannot-use': [200, { recipes: [] }]
    });
    history.replaceState(null, '', `${location.pathname}?nutrition=1`);
    try {
      open({ recipeId: 2 });
      await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Sambar');
      expect(document.body.textContent).not.toContain('The ingredients changed after these');
    } finally {
      history.replaceState(null, '', location.pathname);
    }
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

  describe('"Save mine anyway" waits for the same things Save waits for', () => {
    const changed = [
      409,
      {
        detail: 'Wren changed this recipe after you opened it.',
        code: 'recipe_changed',
        version: 5,
        changed_by: { login_id: 2, name: 'Wren' }
      }
    ] as [number, unknown];

    async function openInConflict() {
      const requests = fakeApi({
        'GET /recipes/2': [200, sambar],
        'GET /recipes/2/cannot-use': [200, { recipes: [] }],
        'PUT /recipes/2': changed
      });
      open({ recipeId: 2 });
      await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Sambar');
      await page.getByRole('textbox', { name: /^Short description/ }).fill('Mine');
      await page.getByRole('button', { name: /^Save/ }).click();
      await expect.element(page.getByRole('button', { name: 'Save mine anyway' })).toBeEnabled();
      return requests;
    }

    it('is greyed out while offline, in the note and in the sheet, and sends nothing', async () => {
      const requests = await openInConflict();
      await page.getByRole('button', { name: 'See Wren’s version' }).click();
      const sheet = page.getByRole('dialog');
      await expect.element(sheet.getByRole('button', { name: 'Save mine anyway' })).toBeEnabled();
      network.offline = true;
      network.deviceOffline = true;
      await expect.element(sheet.getByRole('button', { name: 'Save mine anyway' })).toBeDisabled();
      await expect
        .element(sheet.getByText('You’re offline. Save when you’re back online.'))
        .toBeVisible();
      await page.getByRole('button', { name: 'Back to my edit' }).click();
      await expect.element(page.getByRole('button', { name: 'Save mine anyway' })).toBeDisabled();
      page
        .getByRole('button', { name: 'Save mine anyway' })
        .element()
        .dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(requests.filter((r) => r.method === 'PUT')).toHaveLength(1);
    });

    it('is greyed out while a photo is still uploading', async () => {
      const requests = await openInConflict();
      const answer = globalThis.fetch;
      vi.stubGlobal('fetch', (input: string, init?: RequestInit) =>
        init?.method === 'POST' && String(input).endsWith('/recipes/photos')
          ? new Promise<Response>(() => {})
          : answer(input, init)
      );
      const file = new File([new Uint8Array([1, 2, 3])], 'dish.png', { type: 'image/png' });
      await userEvent.upload(document.querySelector<HTMLInputElement>('input[type=file]')!, file);
      await expect.element(page.getByText('Uploading photo…')).toBeVisible();
      await expect.element(page.getByRole('button', { name: 'Save mine anyway' })).toBeDisabled();
      page
        .getByRole('button', { name: 'Save mine anyway' })
        .element()
        .dispatchEvent(new MouseEvent('click', { bubbles: true }));
      await new Promise((resolve) => setTimeout(resolve, 50));
      expect(requests.filter((r) => r.method === 'PUT')).toHaveLength(1);
    });
  });

  it('a recipe deleted meanwhile, saved with a new photo: keeps what was typed, and Cancel still frees the upload', async () => {
    // cabledrawer 20 Oct: "your placement agreed, as long as nothing typed is lost and the unsaved
    // photo is released."
    const sent: string[] = [];
    vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
      const call = `${init.method ?? 'GET'} ${String(input).replace('/api/v1', '')}`;
      sent.push(call);
      const json = (status: number, body: unknown) =>
        new Response(JSON.stringify(body), { status });
      if (call === 'GET /recipes/2') return json(200, sambar);
      if (call === 'GET /recipes/2/cannot-use') return json(200, { recipes: [] });
      if (call === 'POST /recipes/photos') {
        return json(201, {
          id: 9,
          width: 2,
          height: 2,
          url: '/api/v1/recipes/photos/9/large',
          list_width: 2,
          list_height: 2,
          list_url: '/api/v1/recipes/photos/9/list'
        });
      }
      if (call === 'PUT /recipes/2') {
        return json(404, { code: 'not_found', detail: 'That recipe isn’t here any more.' });
      }
      if (call === 'DELETE /recipes/photos/9') return new Response(null, { status: 204 });
      return json(404, {});
    });
    open({ recipeId: 2 });
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Sambar');
    await page.getByRole('textbox', { name: /^Short description/ }).fill('Stew');
    const file = new File([new Uint8Array([1, 2, 3])], 'dish.png', { type: 'image/png' });
    await userEvent.upload(document.querySelector<HTMLInputElement>('input[type=file]')!, file);
    await expect.element(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
    await page.getByRole('button', { name: /^Save/ }).click();
    await expect.element(page.getByText('That recipe isn’t here any more.')).toBeVisible();
    // Nothing typed is lost, and the editor stays open with the new photo.
    expect(navigation.go).not.toHaveBeenCalled();
    await expect.element(page.getByRole('textbox', { name: 'Name' })).toHaveValue('Sambar');
    await expect
      .element(page.getByRole('textbox', { name: /^Short description/ }))
      .toHaveValue('Stew');
    await expect.element(page.getByRole('button', { name: 'Change photo' })).toBeVisible();
    expect(sent).not.toContain('DELETE /recipes/photos/9');
    // The unsaved photo is released: Cancel, then the "Changes not saved" toast goes.
    await page.getByRole('button', { name: 'Cancel' }).click();
    expect(toasts.current?.message).toBe('Changes not saved');
    toasts.dismiss();
    await vi.waitFor(() => expect(sent).toContain('DELETE /recipes/photos/9'));
  });

  it('says so when the recipe is not there', async () => {
    fakeApi({ 'GET /recipes/9': [404, { detail: 'That recipe isn’t here.' }] });
    open({ recipeId: 9 });
    await expect.element(page.getByText('That recipe isn’t here any more.')).toBeVisible();
  });
});
