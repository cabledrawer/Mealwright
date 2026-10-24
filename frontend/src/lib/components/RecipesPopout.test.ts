import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import RecipesPopout from './RecipesPopout.svelte';
import '../styles/tokens.css';
import '../styles/base.css';

describe('the collapsed sidebar’s Recipes pop-out', () => {
  let component: ReturnType<typeof mount> | null = null;
  let box: HTMLElement | null = null;

  afterEach(() => {
    if (component) unmount(component);
    box?.remove();
    component = null;
  });

  function render(pathname = '/recipes/ingredients') {
    box = document.createElement('div');
    box.innerHTML =
      '<button id="before">Before</button><div id="mount"></div><button id="after">After</button><p id="elsewhere" style="position: fixed; right: 0; bottom: 0">Elsewhere</p>';
    document.body.append(box);
    component = mount(RecipesPopout, {
      target: box.querySelector('#mount')!,
      props: { pathname, current: pathname.startsWith('/recipes') }
    });
    flushSync();
    return {
      icon: page.getByRole('button', { name: 'Recipes' }),
      menu: () => page.getByRole('menu', { name: 'Recipes' })
    };
  }

  const names = () =>
    page
      .getByRole('menuitem')
      .elements()
      .map((e) => e.textContent?.trim());

  it('is a menu button, closed until opened', async () => {
    const { icon, menu } = render();
    await expect.element(icon).toHaveAttribute('aria-haspopup', 'menu');
    await expect.element(icon).toHaveAttribute('aria-expanded', 'false');
    expect(menu().elements()).toHaveLength(0);
  });

  it('Enter opens it: All recipes, Drafts and Ingredients, with the current page marked', async () => {
    const { icon, menu } = render('/recipes/ingredients');
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await expect.element(menu()).toBeVisible();
    await expect.element(icon).toHaveAttribute('aria-expanded', 'true');
    expect(names()).toEqual(['All recipes', 'Drafts', 'Ingredients']);
    const ingredients = page.getByRole('menuitem', { name: 'Ingredients' });
    await expect.element(ingredients).toHaveAttribute('aria-current', 'page');
    expect(
      page
        .getByRole('menuitem')
        .elements()
        .filter((e) => e.getAttribute('aria-current') === 'page')
    ).toHaveLength(1);
    // Focus lands on the current page.
    await expect.element(ingredients).toHaveFocus();
    // They are real links.
    await expect.element(ingredients).toHaveAttribute('href', '/recipes/ingredients');
  });

  it('Space opens it too, and a click', async () => {
    const { icon, menu } = render('/recipes');
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard(' ');
    await expect.element(menu()).toBeVisible();
    await userEvent.keyboard('{Escape}');
    expect(menu().elements()).toHaveLength(0);
    await icon.click();
    await expect.element(menu()).toBeVisible();
    await expect
      .element(page.getByRole('menuitem', { name: 'All recipes' }))
      .toHaveAttribute('aria-current', 'page');
  });

  it('the arrow keys move between the three, round the ends; Home and End jump', async () => {
    const { icon } = render('/recipes');
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    const item = (name: string) => page.getByRole('menuitem', { name });
    await expect.element(item('All recipes')).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    await expect.element(item('Drafts')).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    await expect.element(item('Ingredients')).toHaveFocus();
    await userEvent.keyboard('{ArrowDown}');
    await expect.element(item('All recipes')).toHaveFocus();
    await userEvent.keyboard('{ArrowUp}');
    await expect.element(item('Ingredients')).toHaveFocus();
    await userEvent.keyboard('{Home}');
    await expect.element(item('All recipes')).toHaveFocus();
    await userEvent.keyboard('{End}');
    await expect.element(item('Ingredients')).toHaveFocus();
  });

  it('the Down arrow on the icon opens it at the first page, Up at the last', async () => {
    const { icon, menu } = render('/recipes/ingredients');
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard('{ArrowDown}');
    await expect.element(page.getByRole('menuitem', { name: 'All recipes' })).toHaveFocus();
    await userEvent.keyboard('{Escape}');
    expect(menu().elements()).toHaveLength(0);
    await userEvent.keyboard('{ArrowUp}');
    await expect.element(page.getByRole('menuitem', { name: 'Ingredients' })).toHaveFocus();
  });

  it('Esc closes it and focus goes back to the icon', async () => {
    const { icon, menu } = render();
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{ArrowDown}');
    await userEvent.keyboard('{Escape}');
    expect(menu().elements()).toHaveLength(0);
    await expect.element(icon).toHaveFocus();
    await expect.element(icon).toHaveAttribute('aria-expanded', 'false');
  });

  it('clicking elsewhere closes it and focus goes back to the icon', async () => {
    const { icon, menu } = render();
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await expect.element(menu()).toBeVisible();
    await page.getByText('Elsewhere').click();
    expect(menu().elements()).toHaveLength(0);
    await expect.element(icon).toHaveFocus();
  });

  it('clicking the icon again closes it', async () => {
    const { icon, menu } = render();
    await icon.click();
    await expect.element(menu()).toBeVisible();
    await icon.click();
    expect(menu().elements()).toHaveLength(0);
    await expect.element(icon).toHaveFocus();
  });

  it('Tab away closes it, and focus goes on to the next thing', async () => {
    const { icon, menu } = render();
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await expect.element(menu()).toBeVisible();
    await userEvent.keyboard('{Tab}');
    expect(menu().elements()).toHaveLength(0);
    await expect.element(page.getByRole('button', { name: 'After' })).toHaveFocus();
  });

  it('Shift+Tab closes it and goes back to the icon', async () => {
    const { icon, menu } = render();
    (icon.element() as HTMLElement).focus();
    await userEvent.keyboard('{Enter}');
    await expect.element(menu()).toBeVisible();
    await userEvent.keyboard('{Shift>}{Tab}{/Shift}');
    expect(menu().elements()).toHaveLength(0);
    await expect.element(icon).toHaveFocus();
  });

  it('sits beside the icon, inside the window, wide enough to tap', async () => {
    const { icon } = render();
    await icon.click();
    const menu = page.getByRole('menu', { name: 'Recipes' }).element().getBoundingClientRect();
    const trigger = (icon.element() as HTMLElement).getBoundingClientRect();
    expect(menu.left).toBeGreaterThanOrEqual(trigger.right);
    expect(menu.bottom).toBeLessThanOrEqual(innerHeight);
    for (const item of page.getByRole('menuitem').elements()) {
      expect(item.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
  });
});
