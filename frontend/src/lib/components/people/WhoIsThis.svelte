<script lang="ts">
  // "Who is lorna.s?" (0.9.5 Pe3/M2, mockup Dark-HouseholdWaiting095-Phone): a single sign-on
  // sign-in that matches nobody, for an admin to link to a person, to a new person, or to
  // refuse (cabledrawer 13 Nov). A phone sheet: a real modal dialog, Esc closes it and the focus
  // goes back where it came from. On a computer it is a box in the middle of the screen.
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
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
  let picked = $state<number | 'new' | null>(null);
  let problem = $state<string | null>(null);

  const choices = $derived(waiting ? linkable(people, waiting) : []);
  const pickedPerson = $derived(
    picked === 'new' ? 'new' : (choices.find((p) => p.id === picked) ?? null)
  );

  const isOpen = $derived(waiting !== null);
  $effect(() => {
    if (isOpen) {
      picked = null;
      problem = null;
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

{#if waiting}
  <Sheet title={whoTitle(waiting)} outside={true} {onclose}>
    <form class="body" onsubmit={link}>
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
      <Button type="submit" disabled={pickedPerson === null || busy || offline}
        >{linkButton(pickedPerson)}</Button
      >
      <Button quiet disabled={busy || offline} onclick={() => void act(onrefuse)}>{REFUSE}</Button>
    </form>
  </Sheet>
{/if}

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
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
</style>
