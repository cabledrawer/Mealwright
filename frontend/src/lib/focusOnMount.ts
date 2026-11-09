// A Svelte action: put the cursor in a text box the moment it appears (a "+ New shop" box, a
// rename box), so typing goes into it, not onto the page behind (F178). It selects what is
// already there, so a rename is typed over.

export function focusOnMount(node: HTMLInputElement): void {
  node.focus();
  node.select();
}
