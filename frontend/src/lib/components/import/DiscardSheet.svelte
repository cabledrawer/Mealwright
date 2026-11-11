<script lang="ts">
  // "Discard this draft?" (F211, cabledrawer 10 Nov: Discard draft on Check asks once, deletes the
  // draft and its waiting photo, and Undo is in Recent changes, as on the Drafts list). The words
  // here are proposed, for cabledrawer; the button's name is his. A sheet on a phone, a dialog on a
  // computer, the same shape as the leave sheet.
  import { onMount } from 'svelte';
  import { holdUndo } from '#lib/undo.svelte.js';

  let {
    name,
    kept,
    busy = false,
    ondiscard,
    onstay
  }: {
    /** The recipe's name as it is in the box. */
    name: string;
    /** The review is a draft on the server (so the delete can be undone). */
    kept: boolean;
    busy?: boolean;
    ondiscard: () => void;
    onstay: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  onMount(() => {
    const letGo = holdUndo(); // Ctrl+Z must not move the lines behind this sheet
    dialog.showModal();
    return () => {
      letGo();
      if (dialog.open) dialog.close();
    };
  });

  const words = $derived(name.trim() || 'this recipe');
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  aria-describedby="{uid}-text"
  oncancel={(e) => {
    e.preventDefault();
    if (!busy) onstay();
  }}
  onclick={(e) => {
    if (e.target === dialog && !busy) onstay();
  }}
>
  <div class="body">
    <span class="grip" aria-hidden="true"></span>
    <h2 id="{uid}-title">Discard this draft?</h2>
    <p id="{uid}-text">
      {#if kept}
        {words} will be deleted from Drafts, with its waiting photo. You can undo it from Recent changes.
      {:else}
        {words} isn’t kept in Drafts yet, so nothing of it is kept. Its waiting photo is deleted.
      {/if}
    </p>
    <div class="buttons">
      <button type="button" class="discard" disabled={busy} onclick={ondiscard}>
        {busy ? 'Discarding…' : 'Discard draft'}
      </button>
      <button type="button" class="stay" disabled={busy} onclick={onstay}>Keep checking</button>
    </div>
  </div>
</dialog>

<style>
  dialog {
    width: min(100vw, 30rem);
    max-width: 100vw;
    max-height: none;
    margin: auto auto 0;
    padding: var(--space-5) var(--space-8) var(--space-9);
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
  }

  @media (min-width: 768px) {
    dialog {
      width: min(100vw - 48px, 460px);
      margin: auto;
      padding: var(--space-9);
      border-radius: var(--radius-3xl);
    }

    .grip {
      display: none;
    }
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
  }

  p {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .buttons {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .discard,
  .stay {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 52px;
    border-radius: var(--radius-button);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .discard {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .stay {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  button:disabled {
    opacity: 0.6;
    cursor: default;
  }

  @media (min-width: 768px) {
    .buttons {
      flex-direction: row-reverse;
      flex-wrap: wrap;
      justify-content: flex-start;
      align-items: center;
      padding-top: var(--space-3);
    }

    .discard,
    .stay {
      min-height: var(--touch-target);
      padding: 0 var(--space-7);
      border-radius: var(--radius-full);
    }
  }
</style>
