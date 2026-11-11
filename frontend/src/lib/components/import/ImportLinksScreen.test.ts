// The import screen after several links (F209, F216; cabledrawer 10 Nov): each result opens its draft's
// Check, and one button saves the drafts whose ingredients all matched, with one toast and Undo.
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { drafts } from '#lib/drafts.svelte.js';
import { ImportFlow } from '#lib/import.svelte.js';
import { importLinks } from '#lib/importLinks.svelte.js';
import { network } from '#lib/network.svelte.js';
import { changeOf, fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { PINTS_REVIEW, SAMPLE_REVIEW } from '#lib/testing/importSamples.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import Toast from '#lib/components/Toast.svelte';
import ImportStart from './ImportStart.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

let component: ReturnType<typeof mount> | null = null;
let toast: ReturnType<typeof mount> | null = null;
const bodies = new Map<number, Record<string, unknown>>();

beforeEach(async () => {
  await page.viewport(390, 844);
  network.reset();
  bodies.clear();
  let next = 40;
  fakeApi({
    'POST /recipes/import': (request: FakeRequest) =>
      (request.body as { text: string }).text.includes('ready')
        ? [200, { ...PINTS_REVIEW, name: 'Ready dal' }]
        : [200, { ...SAMPLE_REVIEW, name: 'Needs you' }],
    'POST /recipes/drafts': (request: FakeRequest) => {
      const id = next++;
      const body = request.body as Record<string, unknown>;
      bodies.set(id, body);
      return [201, { id, ...body }];
    },
    'GET /recipes/drafts': [200, { drafts: [], count: 0 }],
    'GET /recipes/drafts/40': () => [200, { id: 40, name: 'Ready dal', ...bodies.get(40) }],
    'POST /recipes/import/save': [
      201,
      {
        recipe: { id: 55, name: 'Ready dal' },
        change: changeOf(60, 'Imported Ready dal'),
        new_ingredients: [],
        learned: 0
      }
    ],
    'POST /changes/60/undo': [200, { result: 'done', message: 'back', change: changeOf(61, 'x') }]
  });
  const flow = new ImportFlow();
  component = mount(ImportStart, { target: document.body, props: { flow } });
  toast = mount(Toast, { target: document.body.appendChild(document.createElement('div')) });
  flushSync();
  await importLinks.run(['https://a.example/ready-dal', 'https://b.example/other']);
  flushSync();
});

afterEach(() => {
  if (component) unmount(component);
  if (toast) unmount(toast);
  component = toast = null;
  document.body.innerHTML = '';
  importLinks.forget();
  drafts.forget();
  undoHistory.clear();
  toasts.dismiss();
  vi.unstubAllGlobals();
});

describe('after several links', () => {
  it('each read result opens its draft’s Check straight away (F209)', async () => {
    await expect
      .element(page.getByRole('link', { name: 'Check Ready dal' }))
      .toHaveAttribute('href', '/recipes/drafts/40');
    await expect
      .element(page.getByRole('link', { name: 'Check Needs you' }))
      .toHaveAttribute('href', '/recipes/drafts/41');
  });

  it('one button saves only the ready drafts, and the row then opens the recipe (F216)', async () => {
    const button = page.getByRole('button', { name: 'Save 1 ready recipe' });
    await expect.element(button).toBeVisible();
    await expect
      .element(
        page.getByText(
          'Ready means every ingredient matched. The others stay in Drafts for you to check.'
        )
      )
      .toBeVisible();
    await button.click();
    await expect.element(page.getByText('Saved 1 recipe')).toBeVisible();
    await expect
      .element(page.getByRole('link', { name: 'Open Ready dal' }))
      .toHaveAttribute('href', '/recipes/55');
    // The one that needs checking is still a draft to check.
    await expect.element(page.getByRole('link', { name: 'Check Needs you' })).toBeVisible();
    expect(page.getByRole('button', { name: /^Save \d+ ready/ }).elements()).toEqual([]);
    // Undo, in the toast, takes it back: the draft is there to check again.
    await page.getByRole('button', { name: 'Undo', exact: true }).click();
    await expect.element(page.getByRole('link', { name: 'Check Ready dal' })).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Save 1 ready recipe' })).toBeVisible();
  });
});
