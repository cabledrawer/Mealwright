<script lang="ts">
  // "Remove Onion from the shopping list?" (mockups ShopRows-confirm; cabledrawer 20 Oct): the
  // one place on the shopping list that asks first, because a swipe can be an accident. A sheet
  // from the bottom on a phone, a dialog on a computer. "Keep it" has the focus when it opens,
  // Escape and a tap outside also keep it. Removing still offers Undo in a toast afterwards.
  // Show it only while asking: {#if asking}<RemoveConfirm …/>{/if}.
  import { onMount } from 'svelte';

  let {
    name,
    onremove,
    onkeep
  }: {
    /** The ingredient's name: "Remove Onion from the shopping list?". */
    name: string;
    onremove: (event: MouseEvent) => void;
    onkeep: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let keep: HTMLButtonElement;

  onMount(() => {
    dialog.showModal();
    keep.focus();
  });

  function closeOnBackdrop(event: MouseEvent) {
    // The dialog itself is only "hit" outside its contents, i.e. on the backdrop.
    if (event.target === dialog) onkeep();
  }
</script>

<dialog
  bind:this={dialog}
  class="remove-confirm"
  role="alertdialog"
  aria-labelledby="{uid}-t"
  aria-describedby="{uid}-d"
  oncancel={(event) => {
    event.preventDefault();
    onkeep();
  }}
  onclick={closeOnBackdrop}
>
  <div class="body">
    <span class="handle" aria-hidden="true"></span>
    <h2 id="{uid}-t">Remove {name} from the shopping list?</h2>
    <p id="{uid}-d">Nothing goes into the pantry.</p>
    <div class="buttons">
      <button type="button" class="keep" bind:this={keep} onclick={onkeep}>Keep it</button>
      <button type="button" class="remove" onclick={onremove}>Remove</button>
    </div>
  </div>
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    overscroll-behavior: contain;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    line-height: 1.3;
    overflow-wrap: anywhere;
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .buttons {
    display: flex;
    gap: var(--space-4);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 18px;
    border-radius: var(--radius-lg);
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }

  .keep {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .remove {
    border: none;
    background: var(--color-danger);
    color: var(--color-danger-text);
  }

  /* Phone: a sheet from the bottom, Remove on top and big. */
  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      margin: 0;
      padding: var(--space-5) var(--space-8) max(32px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    }

    .buttons {
      flex-direction: column-reverse;
    }

    button {
      min-height: 52px;
      font-size: var(--text-xl);
    }
  }

  /* Computer: a dialog in the middle, Keep it then Remove on the right. */
  @media (min-width: 768px) {
    dialog {
      width: min(420px, calc(100vw - 2 * var(--space-7)));
      padding: var(--space-9);
      border-radius: var(--radius-panel);
    }

    .handle {
      display: none;
    }

    .buttons {
      justify-content: flex-end;
    }
  }
</style>
