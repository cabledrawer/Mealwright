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
