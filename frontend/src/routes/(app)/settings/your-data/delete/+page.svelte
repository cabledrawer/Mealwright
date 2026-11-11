<script lang="ts">
  // Settings → Your data → Delete everything (0.9, D1; mockup Dark-DeleteAll09-Phone; the whole
  // of it is proposed, for cabledrawer). Admins only: the typed words and the admin's own password.
  // The server makes a safety backup first and deletes nothing if it can't; the backups folder
  // is kept; everyone is signed out. This browser's own copy is wiped too, as signing out does,
  // and Mealwright then shows first-run setup.
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { backUpNow, deleteEverything } from '#lib/client/yourData.js';
  import { network } from '#lib/network.svelte.js';
  import { signOutHere } from '#lib/offline/signOut.js';
  import { session } from '#lib/session.svelte.js';
  import { DELETE_WORDS, lastBackupWords, wordsMatch } from '#lib/yourDataWords.js';

  const admin = $derived(session.me?.role === 'admin');

  let words = $state('');
  let password = $state('');
  let busy = $state(false);
  let backingUp = $state(false);
  let backedUp = $state<string | null>(null);
  let problem = $state<string | null>(null);

  const ready = $derived(wordsMatch(words) && password.length > 0 && !busy && !network.offline);

  const failed = (error: unknown) =>
    error instanceof ApiError && !cantReach(error) ? error.detail : cantReachWords();

  async function backUp() {
    backingUp = true;
    problem = null;
    backedUp = null;
    try {
      const backups = await backUpNow();
      if (backups.problem) problem = `Couldn’t back up: ${backups.problem}`;
      else backedUp = `Backed up: ${lastBackupWords(backups)}`;
    } catch (error) {
      problem = failed(error);
    } finally {
      backingUp = false;
    }
  }

  async function remove(event: SubmitEvent) {
    event.preventDefault();
    if (!ready) return;
    busy = true;
    problem = null;
    try {
      await deleteEverything(words, password);
    } catch (error) {
      busy = false;
      password = '';
      problem = failed(error);
      return;
    }
    // Everything is gone on the server, and this browser's session with it: wipe its copy
    // (nothing waiting here has anywhere to go now), then first-run setup.
    await signOutHere('anyway');
    await goto(resolve('/(auth)/setup'), { replace: true, invalidateAll: true });
  }
</script>

<PageHeader
  title="Delete everything?"
  parent={{ href: '/(app)/settings/your-data', label: 'Your data' }}
/>

<div class="page">
  <div class="stop">
    <strong>This deletes all of it</strong>
    <p>
      Every recipe, plan, shopping list, pantry item, person, login and setting. There is no Undo.
      Mealwright then starts again at first-run setup.
    </p>
    <p>Your backups in the <span class="mono">backups</span> folder are kept.</p>
  </div>

  {#if !admin}
    <p class="note">Only the household’s admin can do this.</p>
  {:else}
    <button
      type="button"
      class="quiet"
      disabled={backingUp || busy || network.offline}
      onclick={() => void backUp()}>{backingUp ? 'Backing up…' : 'Back up now first'}</button
    >
    {#if backedUp}
      <p class="done" role="status">{backedUp}</p>
    {/if}

    <form class="form" onsubmit={(event) => void remove(event)}>
      <label class="fld">
        <span>Type <span class="mono typed">{DELETE_WORDS}</span> to confirm</span>
        <input
          type="text"
          bind:value={words}
          autocomplete="off"
          autocapitalize="off"
          spellcheck="false"
        />
      </label>
      <label class="fld">
        Your password
        <input type="password" bind:value={password} autocomplete="current-password" />
      </label>
      {#if problem}
        <p class="problem" role="alert">{problem}</p>
      {/if}
      <button type="submit" class="danger" disabled={!ready}
        >{busy ? 'Deleting…' : 'Delete everything'}</button
      >
    </form>
    <p class="note">Admins only. Everyone else is signed out straight away.</p>
  {/if}
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 560px;
  }

  .stop {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-7);
    border: 1px solid var(--color-stop-border);
    border-radius: var(--radius-xl);
    background: var(--color-stop);
    color: var(--color-stop-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .stop strong {
    color: var(--color-stop-title);
    font-size: 1.0625rem;
    font-weight: var(--weight-extrabold);
  }

  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: var(--text-md);
  }

  .typed {
    color: var(--color-text);
  }

  .form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    margin-top: var(--space-4);
  }

  .fld {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    color: var(--color-label);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .fld input {
    width: 100%;
    min-height: 46px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .fld input:focus-visible {
    outline: 2px solid var(--color-focus);
    outline-offset: 1px;
  }

  .quiet,
  .danger {
    min-height: 48px;
    padding: 0 18px;
    border-radius: var(--radius-field);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .quiet {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .danger {
    border: 1px solid var(--color-stop-border);
    background: var(--color-stop);
    color: var(--color-stop-title);
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .note {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .done {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-md);
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
</style>
