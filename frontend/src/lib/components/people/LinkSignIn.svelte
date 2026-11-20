<script lang="ts">
  // "Link…" on the Person page (0.9.5 Pe3/M2, mockup Dark-Person095-Phone): pick, from the
  // single sign-on sign-ins waiting for an admin, the one that is this person. The same sheet
  // as "Who is this?" (WhoIsThis.svelte), the other way round. Its words are proposed, for
  // cabledrawer.
  import { tick } from 'svelte';
  import type { Person, WaitingSignIn } from '#lib/client/people.js';
  import { sentence } from '#lib/people.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import {
    CLOSE,
    linkSheetLine,
    linkSheetTitle,
    linkToButton,
    nobodyWaiting,
    signInsFor,
    signedInDetail
  } from '#lib/ssoWaitingWords.js';

  let {
    person,
    open,
    waiting,
    zone,
    busy,
    offline,
    onlink,
    onclose
  }: {
    person: Person;
    open: boolean;
    waiting: WaitingSignIn[];
    zone: string | null;
    busy: boolean;
    offline: boolean;
    /** Link this person to that sign-in. A refusal throws its sentence. */
    onlink: (accountId: number) => Promise<void>;
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let picked = $state<number | null>(null);
  let problem = $state<string | null>(null);

  const choices = $derived(signInsFor(person, waiting));
  const pickedSignIn = $derived(choices.find((w) => w.id === picked) ?? null);

  $effect(() => {
    if (open && !dialog.open) {
      picked = null;
      problem = null;
      dialog.showModal();
      void tick().then(() =>
        dialog.querySelector<HTMLElement>('[role="radio"], button.close')?.focus()
      );
    } else if (!open && dialog.open) {
      dialog.close();
    }
  });

  async function link(event: SubmitEvent) {
    event.preventDefault();
    if (pickedSignIn === null) return;
    problem = null;
    try {
      await onlink(pickedSignIn.id);
    } catch (error) {
      problem = sentence(error);
    }
  }
</script>

<dialog
  bind:this={dialog}
  class="link-sheet"
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={(event) => {
    if (event.target === dialog) onclose();
  }}
>
  {#if open}
    <form class="body" onsubmit={link}>
      <span class="grab" aria-hidden="true"></span>
      <h2 class="title" id="{uid}-title">{linkSheetTitle(person.name)}</h2>
      {#if choices.length === 0}
        <p class="sub">{nobodyWaiting(person.name)}</p>
      {:else}
        <p class="sub">{linkSheetLine(person.name)}</p>
        <div class="picks" role="radiogroup" aria-label="Sign-in" use:radioKeys>
          {#each choices as signIn (signIn.id)}
            <button
              class="pick"
              type="button"
              role="radio"
              aria-checked={picked === signIn.id}
              onclick={() => (picked = signIn.id)}
            >
              <span class="radio" aria-hidden="true"></span>
              <span class="name">{signIn.username}</span>
              <span class="detail">{signedInDetail(signIn, new Date(), zone)}</span>
            </button>
          {/each}
        </div>
        {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
        <button class="main" type="submit" disabled={pickedSignIn === null || busy || offline}
          >{linkToButton(pickedSignIn)}</button
        >
      {/if}
      <button class="close" type="button" onclick={onclose}>{CLOSE}</button>
    </form>
  {/if}
</dialog>

<style>
  dialog {
    inset: auto 0 0 0;
    width: 100%;
    max-width: none;
    max-height: 92dvh;
    margin: 0;
    padding: var(--space-4) var(--space-8) max(28px, env(safe-area-inset-bottom));
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-toast);
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .grab {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .title {
    margin: 0;
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
    overflow-wrap: anywhere;
  }

  .picks {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .pick {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-5);
    min-height: 56px;
    padding: var(--space-3) 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) 1rem var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .pick[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
  }

  .radio {
    flex: none;
    width: 20px;
    height: 20px;
    border: 2px solid var(--color-text-muted);
    border-radius: 50%;
  }

  .pick[aria-checked='true'] .radio {
    border: 6px solid var(--color-accent-on-soft);
  }

  .name {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-medium);
    overflow-wrap: anywhere;
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .main {
    min-height: 52px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-extrabold) 1rem var(--font-ui);
    cursor: pointer;
  }

  .main:disabled {
    background: var(--color-fill);
    color: var(--color-text-muted);
    cursor: default;
  }

  .close {
    min-height: 52px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-button);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-bold) 1rem var(--font-ui);
    cursor: pointer;
  }

  @media (min-width: 768px) {
    dialog {
      inset: 0;
      width: min(460px, 100%);
      margin: auto;
      border-radius: var(--radius-xl);
    }

    .grab {
      display: none;
    }
  }
</style>
