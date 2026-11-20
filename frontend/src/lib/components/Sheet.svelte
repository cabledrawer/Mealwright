<script lang="ts">
  // The one sheet or dialog (FE9, FE10, FE17). Show it only while it is wanted:
  //   {#if asking}<Sheet title="Remove Onion?" onclose={keep}>…</Sheet>{/if}
  //
  // - A real modal <dialog>: the page behind can't be reached, Tab stays inside, Escape closes.
  // - Escape and a tap outside both do `onclose`, which is the Cancel choice (nothing changes).
  //   A short must-answer list sets `outside={false}`: a tap outside then does nothing, so it
  //   can't be dismissed by accident; Escape still cancels (it is a deliberate key).
  // - `locked` (saving, say) stops both until the work is done.
  // - When it goes, focus goes back to what opened it.
  // - Phone (under 768 px): a sheet from the bottom edge with a grip; computer: a dialog in the
  //   middle. The phone layout is proposed, for cabledrawer.
  // - `size` is a name, not a number: small 420, medium 460, large 520, wide 1040 px.
  // - The title is the one heading, level 2.
  import { onMount, type Snippet } from 'svelte';

  let {
    title,
    onclose,
    size = 'medium',
    outside = true,
    locked = false,
    role = 'dialog',
    describedby,
    element = $bindable(),
    children
  }: {
    title: string;
    onclose: () => void;
    size?: 'small' | 'medium' | 'large' | 'wide';
    outside?: boolean;
    locked?: boolean;
    role?: 'dialog' | 'alertdialog';
    /** The id of the paragraph that explains it, for a screen reader. */
    describedby?: string;
    /** The <dialog>, for a caller that needs to move the focus. */
    element?: HTMLDialogElement;
    children: Snippet;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  onMount(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    element = dialog;
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      // The dialog gives the focus back itself when it can; this covers it going with the page.
      if (
        opener?.isConnected &&
        (!document.activeElement || document.activeElement === document.body)
      ) {
        opener.focus({ preventScroll: true });
      }
    };
  });

  function cancel(event: Event) {
    event.preventDefault();
    if (!locked) onclose();
  }

  function tapOutside(event: MouseEvent) {
    // The dialog itself is only "hit" outside its contents, i.e. on the backdrop.
    if (event.target === dialog && outside && !locked) onclose();
  }
</script>

<dialog
  bind:this={dialog}
  class="sheet {size}"
  {role}
  aria-labelledby="{uid}-title"
  aria-describedby={describedby}
  oncancel={cancel}
  onclick={tapOutside}
>
  <div class="body">
    <span class="grip" aria-hidden="true"></span>
    <h2 id="{uid}-title">{title}</h2>
    {@render children()}
  </div>
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: var(--space-5) var(--space-8) max(var(--space-9), env(safe-area-inset-bottom));
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
    gap: var(--space-5);
  }

  .grip {
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

  /* Phone: a sheet from the bottom edge. */
  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      margin: 0;
      max-height: 92dvh;
      overflow-y: auto;
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    }
  }

  /* Computer: a dialog in the middle. */
  @media (min-width: 768px) {
    dialog {
      margin: auto;
      padding: var(--space-9);
      border-radius: var(--radius-panel);
    }

    .small {
      width: min(420px, calc(100vw - 2 * var(--space-7)));
    }

    .medium {
      width: min(460px, calc(100vw - 2 * var(--space-7)));
    }

    .large {
      width: min(520px, calc(100vw - 2 * var(--space-7)));
    }

    .wide {
      width: min(1040px, calc(100vw - 2 * var(--space-7)));
    }

    .grip {
      display: none;
    }
  }

  @media (forced-colors: active) {
    dialog {
      border: 1px solid CanvasText;
    }
  }
</style>
