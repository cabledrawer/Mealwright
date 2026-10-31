<script lang="ts">
  // "You already have this recipe" (mockup ImportAlready-Phone, spec "The same link twice",
  // cabledrawer 21 Oct): Open it · Import again as a copy. A sheet on a phone, a dialog on a
  // computer. The server answered before fetching anything, so nothing was visited.
  import { network } from '#lib/network.svelte.js';
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import type { Already } from '#lib/import.svelte.js';

  let {
    already,
    busy = false,
    oncopy,
    onclose
  }: {
    already: Already;
    busy?: boolean;
    oncopy: () => void;
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  onMount(() => {
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
    };
  });

  const when = $derived(
    already.importedAt
      ? new Date(already.importedAt).toLocaleDateString(undefined, {
          day: 'numeric',
          month: 'short'
        })
      : ''
  );
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  oncancel={(e) => {
    e.preventDefault();
    onclose();
  }}
  onclick={(e) => {
    if (e.target === dialog) onclose();
  }}
>
  <div class="body">
    <span class="grip" aria-hidden="true"></span>
    <h2 id="{uid}-title">You already have this recipe</h2>
    <div class="card">
      {#if already.photo}
        <img src={already.photo.list_url} alt="" width="56" height="56" />
      {:else}
        <span class="square" aria-hidden="true"></span>
      {/if}
      <span class="what">
        <span class="name">{already.recipe.name}</span>
        <span class="when">Imported {when} from {already.site}</span>
      </span>
    </div>
    <a class="primary" href={resolve('/(app)/recipes/[id]', { id: String(already.recipe.id) })}
      >Open it</a
    >
    <button type="button" class="secondary" disabled={busy || network.offline} onclick={oncopy}
      >Import again as a copy</button
    >
    <button type="button" class="cancel" onclick={onclose}>Cancel</button>
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
      margin: auto;
      padding-top: var(--space-8);
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

  .card {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    padding: var(--space-4);
    border-radius: var(--radius-xl);
    background: var(--color-ground);
  }

  img,
  .square {
    flex: none;
    width: 56px;
    height: 56px;
    border-radius: var(--radius-md);
    background: var(--color-photo);
    object-fit: cover;
  }

  .what {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .name {
    font: var(--weight-semibold) 1.1875rem var(--font-reading);
    overflow-wrap: anywhere;
  }

  .when {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .primary,
  .secondary,
  .cancel {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 52px;
    border-radius: var(--radius-button);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    text-decoration: none;
    cursor: pointer;
  }

  .primary {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .secondary {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .cancel {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
  }
</style>
