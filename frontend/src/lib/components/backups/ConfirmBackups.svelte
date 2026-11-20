<script lang="ts">
  // Settings › Backups & your data (F257, 0.9.5-beta.3): the one place that asks for the admin's
  // password, and only when the action needs it: a Keep that deletes backups, or Back up now at a
  // full folder (R6). Before this a "Your password" box stood on the page just above the export's
  // password box, and a sign-in password went into the wrong one. Proposed, for cabledrawer.
  //
  // The password lives in this sheet only: the box is emptied as the request goes, and the sheet
  // (and with it the password) goes when the action is done or cancelled. It is never logged or
  // stored. An admin who signs in only with single sign-on confirms at the sign-in server instead.
  import Button from '../Button.svelte';
  import ButtonRow from '../ButtonRow.svelte';
  import Sheet from '../Sheet.svelte';
  import type { HowToConfirm } from '#lib/client/yourData.js';
  import { network } from '#lib/network.svelte.js';
  import {
    CONFIRMING_SSO,
    CONFIRM_SSO_BUTTON,
    CONFIRM_SSO_LINE,
    KEEP_FEWER_CANCEL,
    YOUR_PASSWORD
  } from '#lib/yourDataWords.js';

  let {
    title,
    going,
    goWords,
    busyWords,
    confirmedWords,
    how,
    busy,
    confirming,
    problem,
    oncancel,
    onconfirm,
    onsso
  }: {
    /** "Keep fewer backups?" or "Back up now?". */
    title: string;
    /** What goes: "This deletes the oldest backup." */
    going: string;
    goWords: string;
    busyWords: string;
    confirmedWords: string;
    /** Null while the server is asked how this admin confirms. */
    how: HowToConfirm | null;
    busy: boolean;
    confirming: boolean;
    problem: string | null;
    oncancel: () => void;
    /** Sends the action; the password only when this admin confirms with one. */
    onconfirm: (password: string | undefined) => void;
    onsso: () => void;
  } = $props();

  const uid = $props.id();
  let password = $state('');
  const withSso = $derived(how?.confirm_with === 'single_sign_on');
  const ready = $derived(
    how !== null && (withSso ? how.confirmed : password.length > 0) && !busy && !network.offline
  );

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!ready) return;
    const sent = withSso ? undefined : password;
    // Kept no longer than this one request: the box is empty while it goes.
    password = '';
    onconfirm(sent);
  }
</script>

<Sheet {title} size="small" locked={busy} onclose={oncancel} describedby="{uid}-going">
  <form onsubmit={submit}>
    <p id="{uid}-going" class="going">{going}</p>
    {#if withSso}
      {#if how?.confirmed}
        <p class="sub" role="status">{confirmedWords}</p>
      {:else}
        <p class="sub">{CONFIRM_SSO_LINE}</p>
        <Button quiet disabled={confirming || busy || network.offline} onclick={onsso}
          >{confirming ? CONFIRMING_SSO : CONFIRM_SSO_BUTTON}</Button
        >
      {/if}
    {:else if how}
      <label class="field">
        {YOUR_PASSWORD}
        <!-- The sheet opens to ask for exactly this, so the box takes the focus. -->
        <!-- svelte-ignore a11y_autofocus -->
        <input
          type="password"
          bind:value={password}
          autocomplete="current-password"
          spellcheck="false"
          autocapitalize="off"
          maxlength="4096"
          disabled={busy}
          autofocus
        />
      </label>
    {/if}
    {#if problem}
      <p class="problem" role="alert">{problem}</p>
    {/if}
    <ButtonRow>
      <Button quiet disabled={busy} onclick={oncancel}>{KEEP_FEWER_CANCEL}</Button>
      <Button type="submit" danger disabled={!ready}>{busy ? busyWords : goWords}</Button>
    </ButtonRow>
  </form>
</Sheet>

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .going {
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
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
