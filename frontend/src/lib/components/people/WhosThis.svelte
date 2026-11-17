<script lang="ts">
  // The "Who's this?" sheet (0.9 A1, mockup Dark-WhosThis09-Phone): on a shared login, pick
  // yourself so Recent changes says who did what. A bottom sheet on a phone, a dialog on a
  // computer. Escape is "Just looking".
  import { session } from '#lib/session.svelte.js';
  import { whosThis } from '#lib/whosThis.svelte.js';
  import PersonAvatar from './PersonAvatar.svelte';

  /** For the gallery: what a pick does instead of telling the server. */
  let {
    onpick = (id: number | null) => whosThis.pick(id)
  }: {
    onpick?: (id: number | null) => unknown;
  } = $props();

  let dialog: HTMLDialogElement;
  const uid = $props.id();

  $effect(() => {
    if (whosThis.open) {
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  });
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  aria-describedby="{uid}-sub"
  oncancel={(event) => {
    event.preventDefault();
    void onpick(null);
  }}
  data-testid="whos-this"
>
  <div class="body">
    <span class="handle" aria-hidden="true"></span>
    <h2 id="{uid}-title">Who’s this?</h2>
    <p class="sub" id="{uid}-sub">
      This is {session.me?.name ?? 'a shared login'}. Pick yourself so Recent changes says who did
      what.
    </p>
    <div class="grid">
      {#each whosThis.people as person (person.id)}
        <button
          type="button"
          class="who"
          disabled={whosThis.busy}
          onclick={() => void onpick(person.id)}
        >
          <PersonAvatar id={person.id} name={person.name} colour={person.colour} size={52} />
          <span class="name">{person.name}</span>
        </button>
      {/each}
    </div>
    {#if whosThis.problem}
      <p class="problem" role="alert">{whosThis.problem}</p>
    {/if}
    <button type="button" class="looking" disabled={whosThis.busy} onclick={() => void onpick(null)}
      >Just looking (don’t ask again for an hour)</button
    >
    <p class="note">
      Asked again after 30 minutes without use. Turn this off in Settings › People.
    </p>
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
    font-size: 1.5rem;
    font-weight: var(--weight-extrabold);
  }

  .sub {
    margin-top: -6px;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-5);
  }

  .who {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
    padding: var(--space-7) var(--space-4);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-xl);
    background: var(--color-field);
    color: var(--color-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .name {
    max-width: 100%;
    overflow-wrap: anywhere;
    text-align: center;
  }

  .looking {
    min-height: 48px;
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  button:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .note {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

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

  @media (min-width: 768px) {
    dialog {
      width: min(460px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }

    .handle {
      display: none;
    }
  }
</style>
