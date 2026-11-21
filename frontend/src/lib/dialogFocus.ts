// Focus goes into a dialog when it opens (F271, cabledrawer 21 Nov). The browser usually does
// it itself when `showModal()` runs; where it leaves the focus on the page behind (the Plan it
// sheet did), the first button or box in the dialog gets it. A caller that sets the focus itself
// still wins: nothing moves when the focus is already inside the dialog.
import { tick } from 'svelte';

/** What can take the focus first: a button, link or box that isn't off or out of the Tab order. */
const FIRST_STOP =
  'button:not(:disabled), a[href], input:not([type="hidden"]):not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])';

/** Call right after `dialog.showModal()`; it looks again a moment later, once the dialog is drawn. */
export function focusIntoDialog(dialog: HTMLDialogElement | undefined): void {
  void tick().then(() => {
    if (!dialog?.open || dialog.contains(document.activeElement)) return;
    dialog.querySelector<HTMLElement>(FIRST_STOP)?.focus({ preventScroll: true });
  });
}
