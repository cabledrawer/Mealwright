<script lang="ts">
  // "Your own network": the places on the household's own network that Mealwright may
  // visit (spec section 6, "Recipe import, decided for 0.5"). Each is a name, one address
  // or a range. Only an admin changes the list; a member sees it. Taking one off is
  // at once, with Undo; adding one answers in the server's own sentence if it won't do.
  import { network } from '#lib/network.svelte.js';
  import type { OwnNetworkEntry } from '#lib/client/privacy.js';
  import {
    entryWords,
    MEMBER_NOTE,
    NETWORK_BLOCKED,
    NETWORK_EMPTY,
    NETWORK_HELP,
    NETWORK_INTRO,
    offlineNote,
    OWN_NETWORK_ANCHOR,
    type Locked
  } from '#lib/privacyWords.js';
  import Icon from '../Icon.svelte';

  let {
    entries,
    locked = null,
    value = $bindable(''),
    problem = null,
    removeProblem = null,
    adding = false,
    anchor = OWN_NETWORK_ANCHOR,
    onadd,
    onremove
  }: {
    entries: OwnNetworkEntry[];
    locked?: Locked;
    /** What's typed in the box. */
    value?: string;
    /** Why what was typed can't be added (the server's sentence). */
    problem?: string | null;
    /** Taking one off didn't work: why. */
    removeProblem?: string | null;
    adding?: boolean;
    /** The heading's id, which links can go to. Only the gallery changes it. */
    anchor?: string;
    onadd: () => void;
    onremove: (entry: OwnNetworkEntry) => void;
  } = $props();

  const box = $derived(`${anchor}-text`);
  const frozen = $derived(locked !== null);

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!frozen && !adding) onadd();
  }
</script>

<section class="section" aria-labelledby={anchor}>
  <div class="heading">
    <h2 id={anchor}>Your own network</h2>
    <span class="chip">Admins only · whole server</span>
  </div>
  <div class="card">
    <p class="intro">{NETWORK_INTRO}</p>

    {#if entries.length}
      <ul aria-label="Allowed on your own network">
        {#each entries as entry (entry.id)}
          <li>
            <span class="words">
              <span class="value">{entry.value}</span>
              <span class="detail">{entryWords(entry)}</span>
            </span>
            {#if locked !== 'member'}
              <button
                type="button"
                class="remove"
                aria-label="Remove {entry.value}"
                disabled={frozen}
                onclick={() => onremove(entry)}
              >
                <Icon name="trash" size={20} stroke={2.2} />
                <span class="remove-text">Remove</span>
              </button>
            {/if}
          </li>
        {/each}
      </ul>
    {:else}
      <p class="empty">{NETWORK_EMPTY}</p>
    {/if}

    {#if removeProblem}
      <p class="problem" role="alert">{removeProblem}</p>
    {/if}

    {#if locked !== 'member'}
      <form onsubmit={submit} novalidate>
        <label for={box}>Add a name or address</label>
        <div class="add">
          <input
            id={box}
            type="text"
            bind:value
            placeholder="for example wiki.home.lan or 192.168.1.20"
            autocomplete="off"
            autocapitalize="none"
            spellcheck="false"
            disabled={frozen}
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? `${box}-problem` : undefined}
          />
          <button type="submit" class="submit" disabled={frozen || adding}
            >{adding ? 'Adding…' : 'Add'}</button
          >
        </div>
        {#if problem}
          <p id="{box}-problem" class="problem" role="alert">{problem}</p>
        {/if}
      </form>
    {/if}

    {#if locked === 'member'}
      <p class="help">{MEMBER_NOTE}</p>
    {:else if locked === 'offline'}
      <p class="help">{offlineNote(network.deviceOffline)}</p>
    {/if}
    <p class="help">{NETWORK_HELP}</p>
    <p class="blocked"><b>Always blocked, even if listed:</b> {NETWORK_BLOCKED}</p>
  </div>
</section>

<style>
  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .heading {
    display: flex;
    flex-wrap: nowrap;
    min-height: 28px;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3) var(--space-4);
    padding: 0 var(--space-3);
  }

  h2 {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
    scroll-margin-top: 80px;
  }

  .chip {
    flex: 0 1 auto;
    min-width: 0;
    padding: 3px 8px;
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text-soft);
    font-size: 0.6875rem;
    font-weight: var(--weight-extrabold);
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: 14px var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .intro {
    color: var(--color-text-soft);
    font-size: var(--text-base);
    line-height: 1.45;
  }

  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    border-bottom: 1px solid var(--color-divider);
  }

  li {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 52px;
    border-top: 1px solid var(--color-divider);
  }

  .words {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
    padding: var(--space-3) 0;
  }

  .value {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .remove {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .remove:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  /* On a computer the button says what it does, as the mockup does. */
  .remove-text {
    display: none;
  }

  @media (min-width: 768px) {
    .remove {
      padding: 0 var(--space-4);
    }

    .remove-text {
      display: inline;
    }
  }

  .empty {
    padding: 14px;
    border: 1px dashed var(--color-field-border);
    border-radius: var(--radius-lg);
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: center;
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  label {
    color: var(--color-label);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .add {
    display: flex;
    gap: var(--space-4);
  }

  input {
    flex: 1;
    min-width: 0;
    min-height: 48px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    /* 16 px stops phones zooming in on the field. */
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  input:focus-visible {
    outline: 2px solid var(--color-focus);
    outline-offset: 1px;
  }

  input[aria-invalid='true'] {
    border-color: var(--color-warning-text);
  }

  input:disabled {
    opacity: 0.6;
  }

  .submit {
    flex: none;
    min-height: 48px;
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }

  .submit:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    line-height: 1.4;
  }

  .help {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .blocked {
    padding: var(--space-5) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-chip);
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    line-height: 1.45;
  }
</style>
