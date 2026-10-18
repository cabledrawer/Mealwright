import { afterEach, describe, expect, it } from 'vitest';
import { userEvent } from 'vitest/browser';
import { radioKeys } from './radioKeys';

let cleanup: (() => void) | null = null;
afterEach(() => {
  cleanup?.();
  cleanup = null;
  document.body.innerHTML = '';
});

function group(select: boolean) {
  document.body.innerHTML = `<div id="g" role="radiogroup" aria-label="Pick">
    <button role="radio" aria-checked="true">A</button>
    <button role="radio" aria-checked="false">B</button>
    <button role="radio" aria-checked="false">C</button></div>`;
  const node = document.getElementById('g')!;
  const radios = [...node.querySelectorAll<HTMLElement>('[role=radio]')];
  // What a component does: choosing sets aria-checked.
  radios.forEach((r) =>
    r.addEventListener('click', () =>
      radios.forEach((o) => o.setAttribute('aria-checked', String(o === r)))
    )
  );
  const action = radioKeys(node, { select });
  cleanup = () => action?.destroy?.();
  return radios;
}

describe('radioKeys', () => {
  it('select: arrows move to the next radio and choose it, wrapping round', async () => {
    const [a, b, c] = group(true) as [HTMLElement, HTMLElement, HTMLElement];
    a.focus();
    await userEvent.keyboard('{ArrowDown}');
    expect(document.activeElement).toBe(b);
    expect(b.getAttribute('aria-checked')).toBe('true');
    await userEvent.keyboard('{End}');
    expect(document.activeElement).toBe(c);
    await userEvent.keyboard('{ArrowRight}');
    expect(document.activeElement).toBe(a);
    await userEvent.keyboard('{ArrowUp}');
    expect(document.activeElement).toBe(c);
    expect(c.getAttribute('aria-checked')).toBe('true');
  });

  it('the checked radio is the only Tab stop, and it follows the choice', async () => {
    const radios = group(true);
    expect(radios.map((r) => r.tabIndex)).toEqual([0, -1, -1]);
    radios[2]!.click();
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(radios.map((r) => r.tabIndex)).toEqual([-1, -1, 0]);
  });
});

describe('radioKeys: data-no-arrow-select', () => {
  it('arrowing onto it only moves focus; Space and Enter still choose it', async () => {
    const [a, b, c] = group(true) as [HTMLElement, HTMLElement, HTMLElement];
    c.setAttribute('data-no-arrow-select', '');
    let clicks = 0;
    c.addEventListener('click', () => clicks++);
    a.focus();
    await userEvent.keyboard('{ArrowDown}'); // B: chosen as usual
    expect(b.getAttribute('aria-checked')).toBe('true');
    await userEvent.keyboard('{ArrowDown}'); // C: focus only
    expect(document.activeElement).toBe(c);
    expect(clicks).toBe(0);
    expect(b.getAttribute('aria-checked')).toBe('true');
    expect(c.getAttribute('aria-checked')).toBe('false');
    expect([a, b, c].map((r) => r.tabIndex)).toEqual([-1, -1, 0]);
    // Arrowing on from it chooses the next one again.
    await userEvent.keyboard('{ArrowDown}');
    expect(document.activeElement).toBe(a);
    expect(a.getAttribute('aria-checked')).toBe('true');
    // Space and Enter on it still choose it.
    await userEvent.keyboard('{End}');
    expect(clicks).toBe(0);
    await userEvent.keyboard(' ');
    expect(clicks).toBe(1);
    expect(c.getAttribute('aria-checked')).toBe('true');
    await userEvent.keyboard('{Enter}');
    expect(clicks).toBe(2);
  });
});
