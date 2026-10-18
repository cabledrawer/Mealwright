// Arrow keys inside a radio group (WAI-ARIA): Right/Down go to the next one, Left/Up to the
// previous, wrapping round; Home and End jump to the ends. Only the checked one (or the
// first) is in the Tab order, so Tab passes the group in one stop.
//
// `select: true` (the default) also chooses the one you land on, as radio buttons do.
// `select: false` only moves focus; Space or Enter then chooses. Use that where choosing
// saves something on the server (the ¼ ½ ¾ Full marks), so arrowing past doesn't save.

import type { Action } from 'svelte/action';

export const radioKeys: Action<HTMLElement, { select?: boolean } | undefined> = (node, options) => {
  let select = options?.select ?? true;

  const radios = () =>
    [...node.querySelectorAll<HTMLElement>('[role="radio"]')].filter(
      (r) => !(r as HTMLButtonElement).disabled
    );

  function sync() {
    const all = radios();
    const stop = all.find((r) => r.getAttribute('aria-checked') === 'true') ?? all[0];
    for (const r of all) r.tabIndex = r === stop ? 0 : -1;
  }

  function onKeydown(event: KeyboardEvent) {
    const all = radios();
    const here = all.indexOf(event.target as HTMLElement);
    if (here === -1 || event.altKey || event.ctrlKey || event.metaKey) return;
    let to: number;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        to = (here + 1) % all.length;
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        to = (here - 1 + all.length) % all.length;
        break;
      case 'Home':
        to = 0;
        break;
      case 'End':
        to = all.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const target = all[to]!;
    for (const r of all) r.tabIndex = r === target ? 0 : -1;
    target.focus();
    if (select) target.click();
  }

  const observer = new MutationObserver(sync);
  observer.observe(node, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ['aria-checked']
  });
  node.addEventListener('keydown', onKeydown);
  sync();

  return {
    update(next) {
      select = next?.select ?? true;
    },
    destroy() {
      observer.disconnect();
      node.removeEventListener('keydown', onKeydown);
    }
  };
};
