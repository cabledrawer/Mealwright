import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import NewRecipeChoice from './NewRecipeChoice.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

describe('“+ New recipe” and its small choice (N1)', () => {
  let component: ReturnType<typeof mount> | null = null;
  let box: HTMLElement | null = null;

  afterEach(() => {
    if (component) unmount(component);
    box?.remove();
    component = null;
  });

  function render() {
    box = document.createElement('div');
    box.innerHTML =
      '<button id="before">Before</button><div id="mount"></div><button id="after">After</button><p id="elsewhere" style="position: fixed; right: 0; bottom: 0">Elsewhere</p>';
    document.body.append(box);
    component = mount(NewRecipeChoice, { target: box.querySelector('#mount')! });
    flushSync();
    return {
      button: page.getByRole('button', { name: 'New recipe' }),
      menu: () => page.getByRole('menu', { name: 'New recipe' })
    };
  }

  const names = () =>
    page
      .getByRole('menuitem')
      .elements()
      .map((e) => e.textContent?.trim());

  it('is a menu button, closed until opened', async () => {
    const { button, menu } = render();
    await expect.element(button).toHaveAttribute('aria-haspopup', 'menu');
    await expect.element(button).toHaveAttribute('aria-expanded', 'false');
    expect(menu().elements()).toHaveLength(0);
  });

  it('a tap opens Add by hand · Import from a link, as real links', async () => {
    const { button, menu } = render();
    await button.click();
    await expect.element(menu()).toBeVisible();
    await expect.element(button).toHaveAttribute('aria-expanded', 'true');
    expect(names()).toEqual(['Add by hand', 'Import from a link']);
    await expect
      .element(page.getByRole('menuitem', { name: 'Add by hand' }))
      .toHaveAttribute('href', '/recipes/new');
    await expect
      .element(page.getByRole('menuitem', { name: 'Import from a link' }))
      .toHaveAttribute('href', '/recipes/import');
    for (const item of page.getByRole('menuitem').elements()) {
      expect(item.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
  });

  it('Enter opens it with focus on the first choice; the arrows move round; Home and End jump', async () => {
    const { button } = render();
    (button.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    const item = (name: string) => page.getByRole('menuitem', { name });
    await expect.element(item('Add by hand')).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    await expect.element(item('Import from a link')).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    await expect.element(item('Add by hand')).toHaveFocus();
    await userEvent.keyboard('{End}');
    await expect.element(item('Import from a link')).toHaveFocus();
    await userEvent.keyboard('{Home}');
    await expect.element(item('Add by hand')).toHaveFocus();
  });

  it('the Up arrow on the button opens it at the last choice', async () => {
    const { button } = render();
    (button.element() as HTMLElement).focus();
    await userEvent.keyboard('{ArrowUp}');
    await expect.element(page.getByRole('menuitem', { name: 'Import from a link' })).toHaveFocus();
  });

  it('Esc closes it and focus goes back to the button', async () => {
    const { button, menu } = render();
    (button.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{ArrowDown}');
    await userEvent.keyboard('{Escape}');
    expect(menu().elements()).toHaveLength(0);
    await expect.element(button).toHaveFocus();
    await expect.element(button).toHaveAttribute('aria-expanded', 'false');
  });

  it('clicking elsewhere closes it, and so does the button again', async () => {
    const { button, menu } = render();
    await button.click();
    await expect.element(menu()).toBeVisible();
    await page.getByText('Elsewhere').click();
    expect(menu().elements()).toHaveLength(0);
    await button.click();
    await expect.element(menu()).toBeVisible();
    await button.click();
    expect(menu().elements()).toHaveLength(0);
  });

  it('Tab away closes it, and Shift+Tab goes back to the button', async () => {
    const { button, menu } = render();
    (button.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{Tab}');
    expect(menu().elements()).toHaveLength(0);
    await expect.element(page.getByRole('button', { name: 'After' })).toHaveFocus();
    (button.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(menu().elements()).toHaveLength(0);
    await expect.element(button).toHaveFocus();
  });
});
