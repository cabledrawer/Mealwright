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
});
