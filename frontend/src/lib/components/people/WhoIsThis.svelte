<script lang="ts">
  // "Who is lorna.s?" (0.9.5 Pe3/M2, mockup Dark-HouseholdWaiting095-Phone): a single sign-on
  // sign-in that matches nobody, for an admin to link to a person, to a new person, or to
  // refuse (cabledrawer 13 Nov). A phone sheet: a real modal dialog, Esc closes it and the focus
  // goes back where it came from. On a computer it is a box in the middle of the screen.
  import { tick } from 'svelte';
  import PersonAvatar from '#lib/components/people/PersonAvatar.svelte';
  import type { Person, WaitingSignIn } from '#lib/client/people.js';
  import { sentence } from '#lib/people.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import {
    NEW_PERSON,
    REFUSE,
    linkButton,
    linkable,
    pickDetail,
    whoLine,
    whoTitle
  } from '#lib/ssoWaitingWords.js';

  let {
    waiting,
    people,
    zone,
    busy,
    offline,
    onlink,
    onrefuse,
    onclose
  }: {
    /** The sign-in to say who it is; null: closed. */
    waiting: WaitingSignIn | null;
    people: Person[];
    zone: string | null;
    busy: boolean;
    offline: boolean;
    /** Link it to this person, or to a new person (null). A refusal throws its sentence. */
    onlink: (memberId: number | null) => Promise<void>;
    onrefuse: () => Promise<void>;
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let picked = $state<number | 'new' | null>(null);
  let problem = $state<string | null>(null);

  const choices = $derived(waiting ? linkable(people, waiting) : []);
  const pickedPerson = $derived(
    picked === 'new' ? 'new' : (choices.find((p) => p.id === picked) ?? null)
  );

  $effect(() => {
    if (waiting && !dialog.open) {
      picked = null;
      problem = null;
      dialog.showModal();
      void tick().then(() => dialog.querySelector<HTMLElement>('[role="radio"]')?.focus());
    } else if (!waiting && dialog.open) {
      dialog.close();
    }
  });

  async function act(doing: () => Promise<void>) {
    problem = null;
    try {
      await doing();
    } catch (error) {
      problem = sentence(error);
    }
  }

  function link(event: SubmitEvent) {
    event.preventDefault();
    if (pickedPerson === null) return;
    void act(() => onlink(pickedPerson === 'new' ? null : pickedPerson.id));
  }
</script>

<dialog
  bind:this={dialog}
  class="who-sheet"
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={(event) => {
    if (event.target === dialog) onclose();
  }}
>
  {#if waiting}
    <form class="body" onsubmit={link}>
      <span class="grab" aria-hidden="true"></span>
      <h2 class="title" id="{uid}-title">{whoTitle(waiting)}</h2>
      <p class="sub">{whoLine(waiting, new Date(), zone)}</p>
      <div class="picks" role="radiogroup" aria-label="Person" use:radioKeys>
        {#each choices as person (person.id)}
          <button
            class="pick"
            type="button"
            role="radio"
            aria-checked={picked === person.id}
            onclick={() => (picked = person.id)}
          >
            <span class="radio" aria-hidden="true"></span>
            <PersonAvatar id={person.id} name={person.name} colour={person.colour} size={32} />
            <span class="name">{person.name}</span>
            <span class="detail">{pickDetail(person)}</span>
          </button>
        {/each}
        <button
          class="pick"
          type="button"
          role="radio"
          aria-checked={picked === 'new'}
          onclick={() => (picked = 'new')}
        >
          <span class="radio" aria-hidden="true"></span>
          <span class="name">{NEW_PERSON}</span>
        </button>
      </div>
      {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
      <button class="main" type="submit" disabled={pickedPerson === null || busy || offline}
        >{linkButton(pickedPerson)}</button
      >
      <button
        class="refuse"
        type="button"
        disabled={busy || offline}
        onclick={() => void act(onrefuse)}>{REFUSE}</button
      >
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
    gap: var(--space-5);
    min-height: 56px;
    padding: var(--space-3) 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: 14px;
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

  .refuse {
    min-height: 52px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-button);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-bold) 1rem var(--font-ui);
    cursor: pointer;
  }

  .refuse:disabled {
    opacity: 0.6;
    cursor: default;
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
