<script lang="ts">
  // Settings › Backups & your data (0.9, D1; spec section 7; mockup Dark-YourData09-Phone): backups,
  // How to restore, Export everything, History, and Start again.
  //
  // Everyone in the household can look; only an admin changes anything (the server refuses
  // anyone else). Export's optional password (0.9.5): empty, "Export" is the plain link to the
  // zip; with a password it asks the server for the encrypted file in a request body and the
  // browser saves it. The password is kept nowhere (not in the page's storage, not in the
  // address) and the box is emptied once the file is on its way. Offline it says so, as
  // Privacy does.
  import { onDestroy, onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import Icon from '#lib/components/Icon.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import { ApiError, cantReach, cantReachWords, wordsFor } from '#lib/api.js';
  import { getHousehold } from '#lib/client/household.js';
  import {
    markConfirming,
    rememberAction,
    startConfirm,
    goToSignInServer,
    takeAction
  } from '#lib/client/sso.js';
  import {
    backUpNow,
    changeBackups,
    EXPORT_PATH,
    exportWithPassword,
    getBackups,
    getHowToConfirm,
    KEEP_MOST,
    type HowToConfirm,
    type BackupEvery,
    type Backups
  } from '#lib/client/yourData.js';
  import { network } from '#lib/network.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import {
    ADMINS_ONLY,
    BACK_UP_NOW_CONFIRM,
    CONFIRMED_SSO_BACKUP,
    CONFIRMED_SSO_KEEP,
    CONFIRMING_SSO,
    CONFIRM_SSO_BUTTON,
    CONFIRM_SSO_LINE,
    deletesBackupsWords,
    KEEP_FEWER_BUSY,
    KEEP_FEWER_BUTTON,
    KEEP_FEWER_CANCEL,
    REPLACES_OLDEST,
    EVERY_WORDS,
    EXPORT_LEAD,
    EXPORT_MAKING,
    EXPORT_PASSWORD_HINT,
    EXPORT_PASSWORD_LABEL,
    EXPORT_PASSWORD_LENGTH,
    EXPORT_PASSWORD_RULE,
    exportPasswordOk,
    SAFETY_COPY_NOTE,
    SAME_DISK,
    UNDO_REACH,
    includePhotosWords,
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
    wordsFor(error);

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

  async function change(what: { every?: BackupEvery; keep?: number; photos?: boolean }) {
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

  // R6: a Keep that would delete backups, or a Back up now that would push the oldest one out,
  // waits here for the admin's password (or the single sign-on confirm step, as Delete everything
  // asks); nothing is sent until then.
  type Ask = { keep: number } | { backUpNow: true };
  let ask = $state<Ask | null>(null);
  let keepPassword = $state('');
  let keepBusy = $state(false);
  let how = $state<HowToConfirm | null>(null);
  let confirming = $state(false);
  const withSso = $derived(how?.confirm_with === 'single_sign_on');
  const keepReady = $derived(
    how !== null &&
      (withSso ? how.confirmed : keepPassword.length > 0) &&
      !keepBusy &&
      !network.offline
  );
  const pendingKeep = $derived(ask && 'keep' in ask ? ask.keep : null);
  const goingWords = $derived(
    !backups || ask === null
      ? ''
      : 'keep' in ask
        ? deletesBackupsWords(backups.count - ask.keep)
        : REPLACES_OLDEST
  );
  const confirmedWords = $derived(
    ask !== null && 'backUpNow' in ask ? CONFIRMED_SSO_BACKUP : CONFIRMED_SSO_KEEP
  );
  const goWords = $derived(
    ask !== null && 'backUpNow' in ask ? BACK_UP_NOW_CONFIRM : KEEP_FEWER_BUTTON
  );

  function openAsk(what: Ask) {
    ask = what;
    keepPassword = '';
    problem = null;
    how = null;
    getHowToConfirm(
      'keep' in what ? { action: 'keep', keep: what.keep } : { action: 'backup_now' }
    ).then(
      (answer) => (how = answer),
      // Can't tell: the password field; the server still decides.
      () => (how = { confirm_with: 'password', confirmed: false })
    );
  }

  async function pickKeep(keep: number) {
    if (!backups) return;
    if (keep >= backups.count) {
      ask = null;
      await change({ keep });
      return;
    }
    openAsk({ keep });
  }

  function cancelKeep() {
    ask = null;
    keepPassword = '';
    problem = null;
  }

  async function keepFewer(event: SubmitEvent) {
    event.preventDefault();
    if (!keepReady || ask === null || !backups) return;
    keepBusy = true;
    problem = null;
    const password = withSso ? undefined : keepPassword;
    try {
      if ('keep' in ask) {
        backups = await changeBackups(
          password === undefined ? { keep: ask.keep } : { keep: ask.keep, password }
        );
      } else {
        backups = await backUpNow(password);
        now = new Date();
      }
      ask = null;
    } catch (error) {
      problem = failed(error);
      // The proof ran out, or was another session's: ask for a fresh one.
      if (withSso && error instanceof ApiError && error.code === 'confirm_first' && how)
        how = { ...how, confirmed: false };
    } finally {
      keepPassword = '';
      keepBusy = false;
    }
  }

  async function confirmAtServer() {
    confirming = true;
    problem = null;
    try {
      const { url } = await startConfirm(
        ask === null
          ? undefined
          : 'keep' in ask
            ? { action: 'keep', keep: ask.keep }
            : { action: 'backup_now' }
      );
      markConfirming(true, Date.now(), 'backups');
      if (ask) rememberAction(ask);
      goToSignInServer(url, true);
    } catch (error) {
      confirming = false;
      problem = failed(error);
    }
  }

  // Back from the sign-in server with a confirming: open the box again for what was asked.
  onMount(() => {
    const again = takeAction();
    if (again && admin) openAsk(again);
  });

  /** Back up now: at a full folder the new backup pushes the oldest out, so it asks first. */
  async function backUp() {
    if (!backups) return;
    if (backups.count >= backups.keep) {
      openAsk({ backUpNow: true });
      return;
    }
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

  let exportPassword = $state('');
  let exporting = $state(false);
  let exportProblem = $state<string | null>(null);
  let plainLink = $state<HTMLAnchorElement | null>(null);
  // Leaving the page stops a download still on its way (and says nothing about it).
  const leaving = new AbortController();
  onDestroy(() => leaving.abort());

  /** Export (Enter in the box too): no password, the plain file; a password, the encrypted one. */
  async function exportFile(event: SubmitEvent) {
    event.preventDefault();
    if (exporting) return;
    exportProblem = null;
    if (exportPassword === '') {
      plainLink?.click();
      return;
    }
    if (!exportPasswordOk(exportPassword)) {
      exportProblem = EXPORT_PASSWORD_LENGTH;
      return;
    }
    exporting = true;
    try {
      await exportWithPassword(exportPassword, leaving.signal);
      exportPassword = '';
    } catch (error) {
      if (!leaving.signal.aborted) exportProblem = failed(error);
    } finally {
      exporting = false;
    }
  }

  const failure = $derived(backups ? problemWords(backups, now) : null);
  const locked = $derived(!admin || network.offline);
  const keeps = Array.from({ length: KEEP_MOST }, (_, i) => i + 1);
</script>

<PageHeader
  title="Backups & your data"
  overline="Household"
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

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
          <!-- A label only where there is a field for it to point at (not for someone who can only look). -->
          {#if locked}
            <span class="lbl">How often</span>
          {:else}
            <label class="lbl" for="every">How often</label>
          {/if}
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
          <!-- A label only where there is a field for it to point at (not for someone who can only look). -->
          {#if locked}
            <span class="lbl">Keep</span>
          {:else}
            <label class="lbl" for="keep">Keep</label>
          {/if}
          {#if locked}
            <span class="val">{keepWords(backups.keep)}</span>
          {:else}
            <span class="pick">
              <select
                id="keep"
                value={pendingKeep ?? backups.keep}
                onchange={(event) => void pickKeep(Number(event.currentTarget.value))}
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
            >Include photos<small id="include-photos-words"
              >{includePhotosWords(backups.photos_size, backups.database_size)}</small
            ></span
          >
          <Switch
            checked={backups.photos}
            disabled={locked}
            label="Include photos in backups"
            describedby="include-photos-words"
            onchange={(on) => void change({ photos: on })}
          />
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
      {#if ask !== null}
        <form class="ask" onsubmit={(event) => void keepFewer(event)}>
          <strong>{goingWords}</strong>
          {#if withSso}
            {#if how?.confirmed}
              <p class="sub" role="status">{confirmedWords}</p>
            {:else}
              <p class="sub">{CONFIRM_SSO_LINE}</p>
              <button
                type="button"
                class="small"
                disabled={confirming || keepBusy || network.offline}
                onclick={() => void confirmAtServer()}
                >{confirming ? CONFIRMING_SSO : CONFIRM_SSO_BUTTON}</button
              >
            {/if}
          {:else if how}
            <label class="askfield">
              Your password
              <input type="password" bind:value={keepPassword} autocomplete="current-password" />
            </label>
          {/if}
          <div class="buttons">
            <button type="submit" class="small" disabled={!keepReady}
              >{keepBusy ? KEEP_FEWER_BUSY : goWords}</button
            >
            <button type="button" class="small" disabled={keepBusy} onclick={cancelKeep}
              >{KEEP_FEWER_CANCEL}</button
            >
          </div>
        </form>
      {/if}
      {#if failure}
        <p class="problem" role="alert">{failure}</p>
      {/if}
      {#if problem}
        <p class="problem" role="alert">{problem}</p>
      {/if}
      <p class="note">{SAFETY_COPY_NOTE}</p>
      <div class="disk">
        <Icon name="alert" size={18} stroke={2.2} />
        <p>{SAME_DISK}</p>
      </div>
      <a class="card row to" href={resolve('/(app)/settings/your-data/restore')}>
        <span class="lbl">How to restore<small>Step by step</small></span>
        <Icon name="back" size={18} stroke={2.4} />
      </a>
    </section>

    <!-- 0.9.5 (cabledrawer 14 Nov): only the household's admin imports, like the
         other Your data actions (the server refuses a member), so a member doesn't see the row. -->
    {#if admin}
      <section class="part" aria-labelledby="import">
        <h2 id="import">Import</h2>
        <a class="card row to" href={resolve('/(app)/settings/your-data/mealie')}>
          <span class="lbl"
            >Import from Mealie<small>Recipes and ingredients from a Mealie backup file</small
            ></span
          >
          <Icon name="back" size={18} stroke={2.4} />
        </a>
      </section>
    {/if}

    <section class="part" aria-labelledby="export">
      <h2 id="export">Export everything</h2>
      <div class="card pad">
        <p class="sub">{EXPORT_LEAD}</p>
        {#if admin}
          <form class="export-form" onsubmit={(event) => void exportFile(event)}>
            <div class="field">
              <label for="export-password">{EXPORT_PASSWORD_LABEL}</label>
              <input
                id="export-password"
                type="password"
                autocomplete="new-password"
                spellcheck="false"
                autocapitalize="off"
                maxlength="4096"
                aria-describedby="export-hint export-rule"
                disabled={network.offline || exporting}
                bind:value={exportPassword}
              />
              <span class="hint" id="export-hint">{EXPORT_PASSWORD_HINT}</span>
              <span class="hint" id="export-rule">{EXPORT_PASSWORD_RULE}</span>
            </div>
            {#if exportProblem}
              <p class="problem" role="alert">{exportProblem}</p>
            {/if}
            {#if network.offline}
              <!-- Offline a download can only fail in the browser's own words: off, as the page's other buttons. -->
              <button type="button" class="export" disabled>Export</button>
            {:else if exportPassword === ''}
              <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- a file from the API, not a page -->
              <a class="export" href={EXPORT_PATH} download bind:this={plainLink}>Export</a>
            {:else}
              <button type="submit" class="export" disabled={exporting}
                >{exporting ? EXPORT_MAKING : 'Export'}</button
              >
            {/if}
          </form>
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
    outline: var(--focus-width) solid var(--color-focus);
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

  .ask {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-5);
    padding: var(--space-5) 14px;
    border: 1px solid var(--color-stop-border);
    border-radius: var(--radius-field);
    background: var(--color-stop);
    color: var(--color-stop-text);
    font-size: var(--text-md);
  }

  .ask strong {
    color: var(--color-stop-title);
    font-weight: var(--weight-extrabold);
  }

  .askfield {
    display: flex;
    flex-direction: column;
    align-self: stretch;
    gap: var(--space-3);
    font-weight: var(--weight-bold);
  }

  .askfield input {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .askfield input:focus-visible {
    outline: var(--focus-width) solid var(--color-focus);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
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

  .export-form {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  .field {
    display: flex;
    flex-direction: column;
    align-self: stretch;
    gap: var(--space-3);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .field input {
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-field);
    background: var(--color-surface);
    color: var(--color-text);
    /* 16 px: smaller and iOS zooms in when it takes focus. */
    font: var(--weight-regular) 1rem var(--font-ui);
  }

  .field input:focus-visible {
    outline: var(--focus-width) solid var(--color-focus);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-regular);
    line-height: 1.45;
    overflow-wrap: anywhere;
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
