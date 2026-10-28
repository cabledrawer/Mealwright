import { createRawSnippet, flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import '#lib/styles/tokens.css';
import SwipeRow, { type SwipeAction } from './SwipeRow.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

const children = createRawSnippet(() => ({
  render: () => '<div style="min-height: 60px"><button type="button">Spinach</button></div>'
}));

function action(label: string, run: () => void, tone: SwipeAction['tone'] = 'used'): SwipeAction {
  return { label, describe: 'Spinach', icon: 'check', tone, run };
}

function render(props: Record<string, unknown>) {
  component = mount(SwipeRow, { target: document.body, props: { children, ...props } });
  flushSync();
}

/** A finger sliding sideways over the row: down, two moves, up. */
function swipe(dx: number, dy = 0) {
  const row = document.querySelector('.slide') as HTMLElement;
  const base = { pointerId: 3, pointerType: 'touch', isPrimary: true, bubbles: true };
  const at = (x: number, y: number) => ({ ...base, clientX: x, clientY: y });
  row.dispatchEvent(new PointerEvent('pointerdown', at(200, 300)));
  row.dispatchEvent(new PointerEvent('pointermove', at(200 + dx / 2, 300 + dy / 2)));
  row.dispatchEvent(new PointerEvent('pointermove', at(200 + dx, 300 + dy)));
  row.dispatchEvent(new PointerEvent('pointerup', at(200 + dx, 300 + dy)));
  flushSync();
}

describe('SwipeRow', () => {
  it('shows nothing until the row is swiped', () => {
    render({ right: action('Used…', () => {}), left: action('Binned', () => {}, 'danger') });
    expect(page.getByRole('button', { name: /Used|Binned/ }).elements()).toEqual([]);
  });

  it('swiping right shows the right button on the left edge; swiping left shows the other', async () => {
    const done: string[] = [];
    render({
      right: action('Used…', () => done.push('used')),
      left: action('Binned', () => done.push('binned'), 'danger')
    });
    swipe(100);
    const used = page.getByRole('button', { name: 'Used… Spinach' });
    await expect.element(used).toBeVisible();
    expect(page.getByRole('button', { name: /Binned/ }).elements()).toEqual([]);
    // F73: the row gets narrower by the button's width; it is not slid out of sight.
    const slide = document.querySelector('.slide') as HTMLElement;
    expect(slide.style.marginLeft).toBe('104px');
    expect(slide.style.transform).toBe('');
    swipe(-208); // from a slid-right row: past the middle, to the other side
    await expect.element(page.getByRole('button', { name: 'Binned Spinach' })).toBeVisible();
    expect(page.getByRole('button', { name: /Used/ }).elements()).toEqual([]);
    expect(done).toEqual([]); // a swipe alone does nothing
  });

  it('the button does the thing once, and the row closes', async () => {
    const done: string[] = [];
    render({ left: action('Binned', () => done.push('binned'), 'danger') });
    swipe(-100);
    await page.getByRole('button', { name: 'Binned Spinach' }).click();
    expect(done).toEqual(['binned']);
    expect(page.getByRole('button', { name: /Binned/ }).elements()).toEqual([]);
  });

  it('a side with no action does not slide', () => {
    render({ left: action('Binned', () => {}, 'danger') });
    swipe(100);
    const slide = document.querySelector('.slide') as HTMLElement;
    expect(slide.style.marginLeft).toBe('');
    expect(slide.style.marginRight).toBe('');
    expect(page.getByRole('button', { name: /Binned/ }).elements()).toEqual([]);
  });

  it('a mostly-up-and-down drag scrolls the page and shows no button', () => {
    render({ right: action('Used…', () => {}) });
    swipe(20, 80);
    expect(page.getByRole('button', { name: /Used/ }).elements()).toEqual([]);
  });

  it('a short slide springs back', () => {
    render({ right: action('Used…', () => {}) });
    swipe(30);
    expect(page.getByRole('button', { name: /Used/ }).elements()).toEqual([]);
  });

  it('a tap on a swiped row closes it instead of pressing what is under the finger', async () => {
    render({ right: action('Used…', () => {}) });
    swipe(100);
    await expect.element(page.getByRole('button', { name: 'Used… Spinach' })).toBeVisible();
    await page.getByRole('button', { name: 'Spinach', exact: true }).click();
    expect(page.getByRole('button', { name: /Used/ }).elements()).toEqual([]);
  });

  it('is not swipeable when it is switched off (a computer layout)', () => {
    render({ right: action('Used…', () => {}), enabled: false });
    swipe(100);
    expect(page.getByRole('button', { name: /Used/ }).elements()).toEqual([]);
  });

  it('a mouse does not swipe (it has the row’s own buttons)', () => {
    render({ right: action('Used…', () => {}) });
    const row = document.querySelector('.slide') as HTMLElement;
    const base = { pointerId: 4, pointerType: 'mouse', isPrimary: true, bubbles: true };
    row.dispatchEvent(new PointerEvent('pointerdown', { ...base, clientX: 200, clientY: 300 }));
    row.dispatchEvent(new PointerEvent('pointermove', { ...base, clientX: 300, clientY: 300 }));
    row.dispatchEvent(new PointerEvent('pointerup', { ...base, clientX: 300, clientY: 300 }));
    flushSync();
    expect(page.getByRole('button', { name: /Used/ }).elements()).toEqual([]);
  });

  it('each button has a colour of its own and a name a screen reader can use', async () => {
    render({ right: action('Move…', () => {}, 'move') });
    swipe(100);
    const button = page.getByRole('button', { name: 'Move… Spinach' });
    await expect.element(button).toHaveAttribute('data-tone', 'move');
    expect(getComputedStyle(button.element()).backgroundColor).toBe('rgb(43, 92, 138)');
  });

  it('does not slide on its own under reduced motion', () => {
    render({ right: action('Used…', () => {}) });
    const slide = document.querySelector('.slide') as HTMLElement;
    expect(slide.className).toContain('slide');
    const rules = [...document.styleSheets].flatMap((sheet) => [...sheet.cssRules]);
    const media = rules.filter(
      (rule) =>
        rule instanceof CSSMediaRule && rule.conditionText.includes('prefers-reduced-motion')
    ) as CSSMediaRule[];
    const text = media.map((m) => m.cssText).join(' ');
    expect(text).toContain('transition: none');
  });
});
