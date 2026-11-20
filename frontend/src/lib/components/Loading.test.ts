import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import '#lib/styles/tokens.css';
import Loading from './Loading.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function render(props: Record<string, unknown> = {}) {
  component = mount(Loading, { target: document.body, props });
  flushSync();
  return page.getByRole('status');
}

describe('Loading', () => {
  it('says "Loading…" in a status region', async () => {
    await expect.element(render()).toHaveTextContent('Loading…');
  });

  it('can name what is loading', async () => {
    await expect
      .element(render({ what: 'Loading the plan…' }))
      .toHaveTextContent('Loading the plan…');
  });

  it('has no turning ring unless asked', async () => {
    const status = render();
    await expect.element(status).toBeVisible();
    expect(status.element().querySelector('[data-spinner]')).toBeNull();
  });

  // F258: a long wait (Import from Mealie) also shows a turning ring before the words. Screen
  // readers hear only the words.
  it('with spin, a turning ring sits before the words, hidden from screen readers', async () => {
    const status = render({ what: 'Reading the file…', spin: true });
    await expect.element(status).toHaveTextContent('Reading the file…');
    const ring = status.element().querySelector<HTMLElement>('[data-spinner]')!;
    expect(ring).not.toBeNull();
    expect(ring.getAttribute('aria-hidden')).toBe('true');
    expect(getComputedStyle(ring).animationName).not.toBe('none');
    expect(ring.getBoundingClientRect().width).toBeGreaterThan(0);
  });
});
