<script lang="ts">
  // Settings → Your data (0.9, D1; spec section 7; mockup Dark-YourData09-Phone): backups,
  // How to restore, Export everything, History, and Start again.
  //
  // Everyone in the household can look; only an admin changes anything (the server refuses
  // anyone else). Export's optional password is not here yet: it comes with the library that
  // encrypts the file. Offline it says so, as Privacy does.
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import Icon from '#lib/components/Icon.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { getHousehold } from '#lib/client/household.js';
  import {
    backUpNow,
    changeBackups,
    EXPORT_PATH,
    getBackups,
    KEEP_MOST,
    type BackupEvery,
    type Backups
  } from '#lib/client/yourData.js';
  import { network } from '#lib/network.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import {
    ADMINS_ONLY,
    EVERY_WORDS,
    EXPORT_LEAD,
    PHOTOS_NOTE,
    SAME_DISK,
    UNDO_REACH,
    keepWords,
    lastBackupWords,
    problemWords
  } from '#lib/yourDataWords.js';

  const admin = $derived(session.me?.role === 'admin');

  let backups = $state<Backups | null>(null);
  let historyMonths = $state<number | null>(null);
  let loadProblem = $state<string | null>(null);
  let problem = $state<string | null>(null);
  let busy = $state(false);
  let now = $state(new Date());

  const failed = (error: unknown) =>
    error instanceof ApiError && !cantReach(error) ? error.detail : cantReachWords();

  async function load() {
    loadProblem = null;
    try {
      backups = await getBackups();
      now = new Date();
    } catch (error) {
      loadProblem = failed(error);
    }
    getHousehold().then(
      (household) => (historyMonths = household.history_months),
      () => {}
    );
  }

  onMount(() => void load());

  async function change(what: { every?: BackupEvery; keep?: number }) {
    if (!backups) return;
    const before = backups;
    backups = { ...backups, ...what };
    problem = null;
    try {
      backups = await changeBackups(what);
    } catch (error) {
      backups = before;
      problem = failed(error);
    }
  }

  async function backUp() {
    busy = true;
    problem = null;
    try {
      backups = await backUpNow();
      now = new Date();
    } catch (error) {
      problem = failed(error);
    } finally {
      busy = false;
    }
  }

  const failure = $derived(backups ? problemWords(backups, now) : null);
  const locked = $derived(!admin || network.offline);
  const keeps = Array.from({ length: KEEP_MOST }, (_, i) => i + 1);
</script>

<PageHeader title="Your data" parent={{ href: '/(app)/settings', label: 'Settings' }} />

{#if !backups}
  {#if network.down}
    <OfflineNote screen="Settings" />
  {:else if loadProblem}
    <p class="problem" role="alert">
      {loadProblem}
      <button type="button" class="link" onclick={() => void load()}>Try again</button>
    </p>
  {:else}
    <p class="loading" role="status">Loading…</p>
  {/if}
{:else}
  <div class="page">
    {#if !admin}
      <p class="note">{ADMINS_ONLY}</p>
    {/if}

    <section class="part" aria-labelledby="backups">
      <h2 id="backups">Backups</h2>
      <div class="card">
        <div class="row">
          <label class="lbl" for="every">How often</label>
          {#if locked}
            <span class="val">{EVERY_WORDS[backups.every]}</span>
          {:else}
            <span class="pick">
              <select
                id="every"
                value={backups.every}
                onchange={(event) =>
                  void change({ every: event.currentTarget.value as BackupEvery })}
              >
                {#each Object.entries(EVERY_WORDS) as [value, words] (value)}
                  <option {value}>{words}</option>
                {/each}
              </select>
              <Icon name="chevron-down" size={16} stroke={2.4} />
            </span>
          {/if}
        </div>
        <div class="row">
          <label class="lbl" for="keep">Keep</label>
          {#if locked}
            <span class="val">{keepWords(backups.keep)}</span>
          {:else}
            <span class="pick">
              <select
                id="keep"
                value={backups.keep}
                onchange={(event) => void change({ keep: Number(event.currentTarget.value) })}
              >
                {#each keeps as keep (keep)}
                  <option value={keep}>{keepWords(keep)}</option>
                {/each}
              </select>
              <Icon name="chevron-down" size={16} stroke={2.4} />
            </span>
          {/if}
        </div>
        <div class="row">
          <span class="lbl"
            >Last backup<small data-testid="last-backup">{lastBackupWords(backups, now)}</small
            ></span
          >
          {#if admin}
            <button
              type="button"
              class="small"
              disabled={busy || network.offline}
              onclick={() => void backUp()}>{busy ? 'Backing up…' : 'Back up now'}</button
            >
          {/if}
        </div>
      </div>
      {#if failure}
        <p class="problem" role="alert">{failure}</p>
      {/if}
      {#if problem}
        <p class="problem" role="alert">{problem}</p>
      {/if}
      <div class="disk">
        <Icon name="alert" size={18} stroke={2.2} />
        <p>{SAME_DISK}</p>
      </div>
      <p class="note">{PHOTOS_NOTE}</p>
      <a class="card row to" href={resolve('/(app)/settings/your-data/restore')}>
        <span class="lbl">How to restore<small>Step by step</small></span>
        <Icon name="back" size={18} stroke={2.4} />
      </a>
    </section>

    <section class="part" aria-labelledby="export">
      <h2 id="export">Export everything</h2>
      <div class="card pad">
        <p class="sub">{EXPORT_LEAD}</p>
        {#if admin}
          {#if network.offline}
            <!-- Offline a download can only fail in the browser's own words: off, as the page's other buttons. -->
            <button type="button" class="export" disabled>Export</button>
          {:else}
            <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- a file from the API, not a page -->
            <a class="export" href={EXPORT_PATH} download>Export</a>
          {/if}
        {/if}
      </div>
    </section>

    <section class="part" aria-labelledby="history">
      <h2 id="history">History</h2>
      <div class="card">
        <div class="row">
          <span class="lbl">Keep pantry history<small>Then thinned to monthly totals</small></span>
          {#if historyMonths !== null}
            <span class="val">{historyMonths} months</span>
          {/if}
        </div>
      </div>
      <p class="note">{UNDO_REACH}</p>
    </section>

    {#if admin}
      <section class="part" aria-labelledby="start-again">
        <h2 id="start-again">Start again</h2>
        <a class="danger" href={resolve('/(app)/settings/your-data/delete')}>Delete everything…</a>
      </section>
    {/if}
  </div>
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    max-width: 760px;
  }

  .part {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  h2 {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .pad {
    gap: var(--space-5);
    padding: 14px var(--space-7);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 56px;
    padding: var(--space-5) var(--space-7);
    border-top: 1px solid var(--color-border);
    color: var(--color-text);
  }

  .row:first-child {
    border-top: none;
  }

  .lbl {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    font-size: 1rem;
    font-weight: var(--weight-semibold);
  }

  .lbl small {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-medium);
    line-height: 1.4;
  }

  .val {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    text-align: right;
  }

  /* The value is a choice: the browser's own list, looking like the row's value. */
  .pick {
    position: relative;
    display: inline-flex;
    align-items: center;
    color: var(--color-text-muted);
  }

  .pick select {
    min-height: var(--touch-target);
    max-width: 62vw;
    padding: 0 22px 0 var(--space-3);
    border: none;
    border-radius: var(--radius-field);
    background: transparent;
    color: var(--color-text-muted);
    /* 16 px: smaller and iOS zooms in when it opens. */
    font: var(--weight-semibold) 1rem var(--font-ui);
    text-align: right;
    appearance: none;
    cursor: pointer;
  }

  .pick select:focus-visible {
    outline: 2px solid var(--color-focus);
  }

  .pick :global(svg) {
    position: absolute;
    right: 2px;
    pointer-events: none;
  }

  .small {
    flex: none;
    min-height: var(--touch-target);
    padding: 0 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-field);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .small:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .to {
    flex-direction: row;
    border-top: none;
    text-decoration: none;
  }

  .to :global(svg) {
    flex: none;
    color: var(--color-text-muted);
    transform: scaleX(-1);
  }

  .disk {
    display: flex;
    gap: var(--space-5);
    padding: var(--space-5) 14px;
    border: 1px solid var(--color-maybe-chip-border);
    border-radius: var(--radius-field);
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .disk :global(svg) {
    flex: none;
    margin-top: 1px;
  }

  .sub,
  .note {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .note {
    padding: 0 var(--space-3);
  }

  .export,
  .danger {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 48px;
    padding: 0 18px;
    border-radius: var(--radius-field);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .export {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-family: inherit;
  }

  .export:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .danger {
    border: 1px solid var(--color-stop-border);
    background: var(--color-stop);
    color: var(--color-stop-title);
  }

  .loading {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .problem {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }
</style>
