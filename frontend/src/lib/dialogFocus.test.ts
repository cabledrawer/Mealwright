// F271: the focus goes into a dialog that opened with it left on the page behind.
import { tick } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { focusIntoDialog } from '#lib/dialogFocus.js';

afterEach(() => {
  document.body.innerHTML = '';
});

function opened(inner: string) {
  document.body.innerHTML = `<button id="opener">Plan it</button><dialog>${inner}</dialog>`;
  const dialog = document.querySelector('dialog')!;
  document.getElementById('opener')!.focus();
  dialog.showModal();
  // As the Plan it sheet had it: the focus is back on the page, not in the dialog.
  (document.activeElement as HTMLElement).blur();
  return dialog;
}

describe('focusIntoDialog', () => {
  it('moves the focus to the first button that is on, skipping a disabled one', async () => {
    const dialog = opened('<h2>t</h2><button disabled>Go</button><button id="back">Back</button>');
    expect(dialog.contains(document.activeElement)).toBe(false);
    focusIntoDialog(dialog);
    await tick();
    expect(document.activeElement?.id).toBe('back');
  });

  it('leaves the focus where it is when it is already inside', async () => {
    const dialog = opened('<button>First</button><input id="box" aria-label="Box" />');
    dialog.querySelector<HTMLElement>('#box')!.focus();
    focusIntoDialog(dialog);
    await tick();
    expect(document.activeElement?.id).toBe('box');
  });

  it('does nothing for a dialog that is closed or missing', async () => {
    focusIntoDialog(undefined);
    const dialog = opened('<button>First</button>');
    dialog.close();
    focusIntoDialog(dialog);
    await tick();
    expect(dialog.contains(document.activeElement)).toBe(false);
  });
});
