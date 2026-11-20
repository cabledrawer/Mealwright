<script lang="ts">
  import '#lib/styles/fields.css';
  // "Link…" on the Person page (0.9.5 Pe3/M2, mockup Dark-Person095-Phone): pick, from the
  // single sign-on sign-ins waiting for an admin, the one that is this person. The same sheet
  // as "Who is this?" (WhoIsThis.svelte), the other way round. Its words are proposed, for
  // cabledrawer.
  import Button from '#lib/components/Button.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
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

  let picked = $state<number | null>(null);
  let problem = $state<string | null>(null);

  const choices = $derived(signInsFor(person, waiting));
  const pickedSignIn = $derived(choices.find((w) => w.id === picked) ?? null);

  $effect(() => {
    if (open) {
      picked = null;
      problem = null;
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

{#if open}
  <Sheet title={linkSheetTitle(person.name)} {onclose}>
    <form class="body" onsubmit={link}>
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
        {#if problem}<p class="mw-error" role="alert">{problem}</p>{/if}
        <Button type="submit" disabled={pickedSignIn === null || busy || offline}
          >{linkToButton(pickedSignIn)}</Button
        >
      {/if}
      <Button quiet onclick={onclose}>{CLOSE}</Button>
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
</style>
