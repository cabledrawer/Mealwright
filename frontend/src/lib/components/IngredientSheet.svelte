<script lang="ts">
  // Shows the ingredient editor when something asks for it (ingredientEditor.open):
  // a sheet from the bottom on phones, a panel on the right on desktop. A real modal
  // dialog, so focus stays inside, Escape closes it, and focus goes back afterwards.
  import { ingredientEditor } from '#lib/ingredientEditor.svelte.js';
  import IngredientEditor from './IngredientEditor.svelte';

  let dialog: HTMLDialogElement;
  let name = $state('');
  const foodId = $derived(ingredientEditor.foodId);

  $effect(() => {
    if (foodId !== null && !dialog.open) dialog.showModal();
    else if (foodId === null && dialog.open) dialog.close();
  });

  // Escape fires "cancel" straight away. (Not "close": that arrives a moment later, and
  // could close a food opened in the meantime.)

  function closeOnBackdrop(event: MouseEvent) {
    // The dialog itself is only "hit" outside its contents, i.e. on the backdrop.
    if (event.target === dialog) ingredientEditor.close();
  }
</script>

<dialog
  bind:this={dialog}
  aria-label={name ? `Edit ${name}` : 'Edit ingredient'}
  oncancel={() => ingredientEditor.close()}
  onclick={closeOnBackdrop}
>
  {#if foodId !== null}
    <div class="body">
      <span class="handle" aria-hidden="true"></span>
      {#key foodId}
        <IngredientEditor
          {foodId}
          variant="sheet"
          onname={(n) => (name = n)}
          onclose={() => ingredientEditor.close()}
          onopen={(id) => ingredientEditor.open(id)}
        />
      {/key}
    </div>
  {/if}
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
    scrollbar-width: none;
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

  /* Phone: a sheet from the bottom. */
  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      max-height: min(680px, calc(100dvh - 120px));
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  /* Desktop: a panel on the right. */
  @media (min-width: 768px) {
    dialog {
      inset: var(--space-7) var(--space-7) var(--space-7) auto;
      width: min(440px, calc(100vw - 2 * var(--space-7)));
      height: auto;
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: 0;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }
    .handle {
      display: none;
    }
  }
</style>
