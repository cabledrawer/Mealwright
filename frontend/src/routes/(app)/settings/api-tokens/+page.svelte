<script lang="ts">
  import { onDestroy } from 'svelte';
  // Settings › API tokens (0.9 O2; the mockup Dark-ApiTokens09). Admins only. The
  // list, "New token" (name, Read only / Read and change, Expires: Never, 30 days, 1 year or
  // Pick a date) and, once made, the token shown this once with Copy and Done. Deleting asks
  // first: a deleted token can't come back, and the apps using it stop at once (the brief's
  // "revoke with a confirm"; cabledrawer 12 Nov). Every word here is accepted (cabledrawer 12 Nov).
  import { ApiError, cantReach, cantReachWords, detailOf } from '#lib/api.js';
  import {
    ENDS,
    LONGEST_NAME,
    deleteApiToken,
    getApiTokens,
    lastDay,
    makeApiToken,
    tokenDetail,
    type ApiToken,
    type ApiTokens,
    type Ends,
    type TokenScope
  } from '#lib/apiTokens.js';
  import { CopyFeedback } from '#lib/copyFeedback.svelte.js';
  import { addDays } from '#lib/dates.js';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import { network } from '#lib/network.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';

  const uid = $props.id();

  let list = $state<ApiTokens | null>(null);
  let loadProblem = $state('');
  let name = $state('');
  let scope = $state<TokenScope>('read');
  let ends = $state<Ends>('year');
  let picked = $state('');
  let checked = $state(false);
  let busy = $state(false);
  let problem = $state('');
  /** The token just made: shown until Done, never again. */
  let made = $state<string | null>(null);
  let asking = $state<ApiToken | null>(null);
  let said = $state('');
  let dialog = $state<HTMLDialogElement>();
  let keep = $state<HTMLButtonElement>();

  const today = $derived(list?.today ?? '');
  const nameError = $derived.by(() => {
    const trimmed = name.trim();
    if (!trimmed) return 'Give the token a name.';
    if ([...trimmed].length > LONGEST_NAME) return `Use at most ${LONGEST_NAME} characters.`;
    return undefined;
  });
  const dateError = $derived(
    ends === 'pick' && (!picked || (today && picked < today)) ? 'Pick today or later.' : undefined
  );

  $effect(() => {
    void network.backAgain;
    void load();
  });

  $effect(() => {
    if (asking && dialog && !dialog.open) {
      dialog.showModal();
      keep?.focus();
    }
  });

  function why(error: unknown): string {
    if (cantReach(error)) return cantReachWords();
    if (error instanceof ApiError) return error.detail;
    return detailOf(null);
  }

  async function load() {
    try {
      list = await getApiTokens();
      loadProblem = '';
    } catch (error) {
      loadProblem = why(error);
    }
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    void make();
  }

  async function make() {
    if (busy) return;
    checked = true;
    problem = '';
    if (nameError || dateError || !today) return;
    busy = true;
    try {
      const answer = await makeApiToken(name.trim(), scope, lastDay(ends, today, picked));
      made = answer.token;
      name = '';
      checked = false;
      await load();
    } catch (error) {
      problem = why(error);
    } finally {
      busy = false;
    }
  }

  const copier = new CopyFeedback();
  onDestroy(() => copier.dispose());

  async function copy() {
    if (made === null) return;
    if (await copier.copy(made)) {
      toasts.show('Token copied');
    } else {
      toasts.show('Couldn’t copy. Select the token and copy it.', { tone: 'problem' });
    }
  }

  function done() {
    made = null;
  }

  function closeAsk() {
    asking = null;
    if (dialog?.open) dialog.close();
  }

  async function remove() {
    const token = asking;
    closeAsk();
    if (token === null) return;
    problem = '';
    said = '';
    try {
      await deleteApiToken(token.id);
      said = `Deleted ${token.name}.`;
    } catch (error) {
      problem = why(error);
    }
    await load();
  }
</script>

<PageHeader
  title="API tokens"
  overline="Household"
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<div class="page">
  <p class="sub">
    For other apps on your own network, like Home Assistant. A token can read, or read and change,
    this household’s data.
  </p>

  {#if list === null}
    <p class="card row detail" role={loadProblem ? 'alert' : undefined}>
      {loadProblem || 'Loading…'}
    </p>
  {:else if list.tokens.length > 0}
    <ul class="card" data-testid="api-tokens">
      {#each list.tokens as token (token.id)}
        <li class="row">
          <span class="who">
            <span class="label">{token.name}</span>
            <span class="detail">{tokenDetail(token, list.today)}</span>
          </span>
          <button
            type="button"
            class="small danger"
            aria-label="Delete {token.name} token"
            disabled={network.offline}
            onclick={() => (asking = token)}>Delete</button
          >
        </li>
      {/each}
    </ul>
  {/if}
  <p class="said" role="status">{said}</p>

  {#if list !== null}
    <h2 class="sub-title" id="{uid}-new">New token</h2>
    {#if made !== null}
      <div class="card pad" data-testid="made-token">
        <p class="warn">
          <Icon name="info" size={18} />
          <span
            ><strong>Copy it now.</strong> You won’t see this token again. If you lose it, delete it and
            make a new one.</span
          >
        </p>
        <output class="mono" aria-label="Your new token">{made}</output>
        <div class="two">
          <button type="button" class="main" onclick={() => void copy()}
            >{copier.label('Copy')}</button
          >
          <button type="button" class="other" onclick={done}>Done</button>
        </div>
      </div>
    {:else}
      <form class="card pad" aria-labelledby="{uid}-new" onsubmit={submit} novalidate>
        <div class="field">
          <label class="field-label" for="{uid}-name">Name</label>
          <input
            id="{uid}-name"
            class="input"
            type="text"
            autocomplete="off"
            placeholder="Shopping widget"
            bind:value={name}
            aria-invalid={checked && !!nameError}
            aria-describedby={checked && nameError ? `${uid}-name-error` : undefined}
          />
          {#if checked && nameError}
            <span class="error" id="{uid}-name-error">{nameError}</span>
          {/if}
        </div>
        <div class="field" role="group" aria-labelledby="{uid}-can">
          <span class="field-label" id="{uid}-can">Can</span>
          <div class="seg">
            <button type="button" aria-pressed={scope === 'read'} onclick={() => (scope = 'read')}
              >Read only</button
            >
            <button type="button" aria-pressed={scope === 'full'} onclick={() => (scope = 'full')}
              >Read and change</button
            >
          </div>
        </div>
        <div class="field" role="group" aria-labelledby="{uid}-ends">
          <span class="field-label" id="{uid}-ends">Expires</span>
          <div class="chips">
            {#each ENDS as choice (choice.value)}
              <button
                type="button"
                class="chip"
                aria-pressed={ends === choice.value}
                onclick={() => {
                  ends = choice.value;
                  if (choice.value === 'pick' && !picked && today) picked = addDays(today, 90);
                }}>{choice.label}</button
              >
            {/each}
          </div>
          {#if ends === 'pick'}
            <label class="visually-hidden" for="{uid}-date">Last day it works</label>
            <input
              id="{uid}-date"
              class="input"
              type="date"
              min={today}
              max={addDays(today, 5 * 365)}
              bind:value={picked}
              aria-invalid={checked && !!dateError}
              aria-describedby={checked && dateError ? `${uid}-date-error` : undefined}
            />
            {#if checked && dateError}
              <span class="error" id="{uid}-date-error">{dateError}</span>
            {/if}
          {/if}
        </div>
        {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
        <button type="submit" class="main" disabled={busy || network.offline}
          >{busy ? 'Making…' : 'Make token'}</button
        >
      </form>
    {/if}
  {/if}

  <p class="note">Admins only. Tokens never see passwords or sign-in settings.</p>
</div>

{#if asking}
  <dialog
    bind:this={dialog}
    role="alertdialog"
    aria-labelledby="{uid}-ask"
    aria-describedby="{uid}-ask-d"
    oncancel={(event) => {
      event.preventDefault();
      closeAsk();
    }}
  >
    <h2 id="{uid}-ask">Delete the {asking.name} token?</h2>
    <p id="{uid}-ask-d">Apps using it stop at once. It can’t be brought back.</p>
    <div class="two">
      <button type="button" class="other" bind:this={keep} onclick={closeAsk}>Keep it</button>
      <button type="button" class="main danger-fill" onclick={() => void remove()}>Delete</button>
    </div>
  </dialog>
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 560px;
  }

  .sub,
  .note {
    margin: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .sub-title {
    margin: var(--space-2) var(--space-2) 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    margin: 0;
    padding: 0 var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    list-style: none;
  }

  .pad {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: var(--space-7);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 56px;
    padding: var(--space-5) 0;
  }

  /* A card that is only a line of words (loading, or a member who can't see the list): the row's
     "no side padding" would put the words on the card's edge (L10). */
  .card.row {
    padding: var(--space-5) var(--space-7);
  }

  .row + .row {
    border-top: 1px solid var(--color-border);
  }

  .who {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .field-label {
    color: var(--color-label);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .input {
    box-sizing: border-box;
    width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    /* 16 px stops phones zooming in on the box. */
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .seg {
    display: flex;
    gap: 3px;
    padding: 3px;
    border-radius: var(--radius-md);
    background: var(--color-fill-strong);
  }

  .seg button {
    flex: 1;
    min-height: var(--touch-target);
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .seg button[aria-pressed='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .main,
  .other,
  .small {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border-radius: var(--radius-button);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .main {
    min-height: 48px;
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .other,
  .small {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .small {
    flex: none;
    padding: 0 var(--space-6);
    font-size: var(--text-sm);
  }

  /* Red words on a card: the lighter red that passes 4.5:1 in both themes, as "Remove from list" (the
     solid --color-danger is for a button's fill). */
  .danger {
    color: var(--color-warning-text);
  }

  .main.danger-fill {
    background: var(--color-danger);
    color: var(--color-danger-text);
  }

  .main:disabled,
  .small:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .two {
    display: flex;
    gap: var(--space-5);
  }

  .two > * {
    flex: 1;
  }

  .warn {
    display: flex;
    gap: var(--space-5);
    margin: 0;
    padding: var(--space-5) var(--space-6);
    border: 1px solid var(--color-warning-border);
    border-radius: var(--radius-lg);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .warn :global(svg) {
    flex: none;
  }

  .mono {
    display: block;
    padding: var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: var(--text-sm);
    word-break: break-all;
    user-select: all;
  }

  .problem {
    margin: 0;
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .said,

  dialog {
    max-width: min(420px, calc(100vw - 32px));
    padding: var(--space-8);
    border: none;
    border-radius: var(--radius-panel);
    background: var(--color-surface);
    color: var(--color-text);
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  dialog h2 {
    margin: 0 0 var(--space-3);
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  dialog p {
    margin: 0 0 var(--space-7);
    color: var(--color-text-muted);
    font-size: var(--text-base);
    line-height: 1.45;
  }
</style>
