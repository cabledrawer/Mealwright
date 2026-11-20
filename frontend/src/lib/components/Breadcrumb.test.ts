import { mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import Breadcrumb from './Breadcrumb.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

describe('Breadcrumb', () => {
  it('has the way up twice (back link, crumbs) and names the current page', () => {
    component = mount(Breadcrumb, {
      target: document.body,
      props: { href: '/recipes', label: 'Recipes', current: 'Sambar' }
    });
    expect(document.body.querySelectorAll('a[href="/recipes"]').length).toBe(2);
    expect(document.body.querySelector('[aria-current="page"]')?.textContent).toBe('Sambar');
    expect(document.body.querySelector('nav')?.getAttribute('aria-label')).toBe('Breadcrumb');
  });
});
