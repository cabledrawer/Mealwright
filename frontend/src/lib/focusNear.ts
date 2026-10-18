// When a row moves or goes (ticked into the trolley, unticked, removed, cleared), the control
// that had keyboard focus is destroyed and focus would drop to the page. keepFocus() notes
// where to go before the change (the next row's tick box, else the one before, else the
// shop's heading) and the function it returns puts focus there once the page has updated.

import { tick } from 'svelte';

export function keepFocus(from: HTMLElement): () => void {
  const scope = from.closest<HTMLElement>('section.shop') ?? document.body;
  const boxes = [...scope.querySelectorAll<HTMLElement>('.tick input')];
  // The row's own tick box (when the button pressed is inside a row), else no neighbour.
  const own = from.matches('.tick input')
    ? from
    : (from.closest('li')?.querySelector<HTMLElement>('.tick input') ?? null);
  const here = own ? boxes.indexOf(own) : -1;
  const next = here === -1 ? null : (boxes[here + 1] ?? boxes[here - 1] ?? null);
  const heading = scope.querySelector<HTMLElement>('h2');
  return () => {
    void tick().then(() => {
      const target = next?.isConnected ? next : heading;
      if (target?.isConnected) target.focus();
    });
  };
}
