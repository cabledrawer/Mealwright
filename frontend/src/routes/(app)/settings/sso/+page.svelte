<script lang="ts">
  import { onDestroy } from 'svelte';
  // Settings › Sign-in for everyone (0.9 O1; the mockup Dark-SSO09-Desktop). Admins only,
  // and on a computer: a phone says "Set up on a computer" (cabledrawer 12 Nov). The client
  // secret is never shown or sent back: the field is blank, and blank keeps the saved one.
  // "Test sign-in" asks the server to start a test (a POST, never a link) and opens the
  // sign-in server in a new tab; when this tab is looked at again it asks the server for the
  // result. A test links nothing. When the sign-in server makes whoever signed in there an
  // Admin, this screen asks "Link tess to …?" with their name and email address, and only
  // "Link" links them (O1 review r1 H1). Password sign-in can be turned off only once an admin
  // has signed in with single sign-on and its Privacy switch is on (cabledrawer 12 Nov).
  import { MediaQuery } from 'svelte/reactivity';
  import { ApiError, cantReach, cantReachWords, detailOf, wordsFor } from '#lib/api.js';
  import {
    callbackAddress,
    dropTestedLink,
    getSsoSetup,
    goToSignInServer,
    linkTested,
    putSsoSetup,
    startTest,
    type GroupRole,
    type SsoSetup
  } from '#lib/client/sso.js';
  import Button from '#lib/components/Button.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import TextField from '#lib/components/TextField.svelte';
  import { CopyFeedback } from '#lib/copyFeedback.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import { session } from '#lib/session.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { PHONE_QUERY } from '#lib/layout.js';
  import {
    LINK,
    NOT_LINKED_MEMBER,
    NOT_NOW,
    SETUP_ON_COMPUTER,
    SETUP_PHONE_NOTE,
    SSO_WHO_LINKS,
    linkNote,
    linkQuestion,
    linkWho,
    linkedText,
    signInWith,
    ssoMessage,
    testPassedText
  } from '#lib/ssoWords.js';

  const phone = new MediaQuery(PHONE_QUERY.slice(1, -1));
  const admin = $derived(session.me?.role === 'admin');

  let saved = $state<SsoSetup | null>(null);
  let loadProblem = $state('');
  let button = $state('');
  let issuer = $state('');
  let clientId = $state('');
  let secret = $state('');
  let groupClaim = $state('groups');
  let groups = $state<GroupRole[]>([]);
  let anyoneElse = $state<'none' | 'member'>('none');
  let passwords = $state(true);
  let busy = $state(false);
  let problem = $state('');
  let done = $state('');
  /** The server's notice after a save: password sign-in is on again. */
  let notice = $state('');
  const copier = new CopyFeedback();
  onDestroy(() => copier.dispose());
  let testing = $state(false);
  let testProblem = $state('');
  let linking = $state(false);
  const myUsername = $derived(session.me?.username ?? '');

  const redirect = callbackAddress();

  /** The issuer's host name, for the "On your home network?" line. */
  const issuerHost = $derived.by(() => {
    try {
      return new URL(issuer.trim()).hostname;
    } catch {
      return '';
    }
  });

  /** Password sign-in may go off: an admin signs in with single sign-on, and it's switched on. */
  const passwordsMayGoOff = $derived(
    !!saved && saved.secret_set && saved.admin_linked && saved.switch_on
  );

  function fill(setup: SsoSetup) {
    saved = setup;
    button = setup.button_name;
    issuer = setup.issuer;
    clientId = setup.client_id;
    secret = '';
    groupClaim = setup.group_claim;
    groups = setup.group_roles.map((g) => ({ ...g }));
    anyoneElse = setup.anyone_else;
    passwords = setup.password_sign_in;
  }

  async function load(refill: boolean) {
    try {
      const setup = await getSsoSetup();
      if (refill || !saved) fill(setup);
      else saved = { ...saved, test: setup.test, admin_linked: setup.admin_linked };
      loadProblem = '';
    } catch (error) {
      loadProblem = wordsFor(error, detailOf(null));
      if (error instanceof ApiError && !cantReach(error)) loadProblem = error.detail;
    }
  }

  /** The form is filled from the saved setup once; a resize to a phone and back doesn't refill it
   *  over what was typed (L13). */
  let filledOnce = false;

  $effect(() => {
    if (!admin || phone.current) return;
    void load(!filledOnce);
    filledOnce = true;
    // Back from the test's tab: the result is on the server.
    const again = () => {
      if (document.visibilityState === 'visible') void load(false);
    };
    addEventListener('focus', again);
    document.addEventListener('visibilitychange', again);
    return () => {
      removeEventListener('focus', again);
      document.removeEventListener('visibilitychange', again);
    };
  });

  function addGroup() {
    groups.push({ group: '', role: 'member' });
  }

  function removeGroup(index: number) {
    groups.splice(index, 1);
  }

  async function copy() {
    if (!(await copier.copy(redirect))) {
      toasts.problem('Couldn’t copy. Select the address and copy it.');
    }
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    void save();
  }

  async function save() {
    if (busy) return;
    busy = true;
    problem = '';
    done = '';
    notice = '';
    try {
      const setup = await putSsoSetup({
        issuer: issuer.trim(),
        client_id: clientId.trim(),
        client_secret: secret,
        button_name: button.trim(),
        redirect_uri: redirect,
        group_claim: groupClaim.trim() || 'groups',
        group_roles: groups
          .map((g) => ({ group: g.group.trim(), role: g.role }))
          .filter((g) => g.group),
        anyone_else: anyoneElse,
        // The stored choice goes back unless the admin moved the switch: while single sign-on
        // can't start the screen shows passwords on, and saving that must not store it.
        password_sign_in:
          saved && passwords === saved.password_sign_in ? saved.password_sign_in_stored : passwords
      });
      fill(setup);
      // "Saved. Password sign-in is on again…" when the save changed who gets in while it was off.
      if (setup.passwords_back_on && setup.notice) notice = setup.notice;
      else done = 'Saved.';
    } catch (error) {
      if (cantReach(error)) problem = cantReachWords();
      else if (error instanceof ApiError) problem = error.detail;
      else problem = detailOf(null);
    } finally {
      busy = false;
    }
  }

  function cancel() {
    if (saved) fill(saved);
    problem = '';
    done = '';
    notice = '';
  }

  /** The tab opens on the click itself (a browser blocks one opened later), blank and cut
   *  off from this one; it goes to the sign-in server once the server has started the test.
   *  If the browser won't open a tab, this tab goes there and comes back. */
  async function test() {
    if (testing) return;
    testing = true;
    testProblem = '';
    const tab = window.open('about:blank', '_blank');
    if (tab) tab.opener = null;
    try {
      const { url } = await startTest();
      if (tab) tab.location.replace(url);
      else goToSignInServer(url, true);
    } catch (error) {
      tab?.close();
      testProblem = wordsFor(error);
    } finally {
      testing = false;
    }
  }

  /** "Link" or "Not now": the server's answer is the setup with the test as it now stands. */
  async function answerLink(link: boolean) {
    if (linking || !saved) return;
    linking = true;
    testProblem = '';
    try {
      const setup = await (link ? linkTested() : dropTestedLink());
      saved = { ...saved, test: setup.test, admin_linked: setup.admin_linked };
    } catch (error) {
      testProblem = wordsFor(error);
      void load(false);
    } finally {
      linking = false;
    }
  }
</script>

<svelte:head>
  <title>Single sign-on · Mealwright</title>
</svelte:head>

<PageHeader
  title="Single sign-on"
  parent={{ href: '/(app)/settings/sign-in-everyone', label: 'Sign-in for everyone' }}
/>

{#if !admin}
  <p class="sub">Only an admin can set up single sign-on.</p>
{:else if phone.current}
  <div class="phone card">
    <p class="phone-title">{SETUP_ON_COMPUTER}</p>
    <p class="sub">{SETUP_PHONE_NOTE}</p>
  </div>
{:else}
  <p class="sub intro">
    Let people sign in with your own sign-in server (Authentik, Authelia, Keycloak, Pocket ID…
    anything that speaks OpenID Connect).
  </p>
  {#if loadProblem}<p class="problem" role="alert">{loadProblem}</p>{/if}
  {#if saved?.kept_warning}<p class="warn" role="status">{saved.kept_warning}</p>{/if}
  <form class="grid" onsubmit={submit} novalidate>
    <section class="card" aria-labelledby="sso-server">
      <h2 id="sso-server">1 · Your sign-in server</h2>
      <TextField
        id="sso-button"
        label="Name on the button"
        bind:value={button}
        autocomplete="off"
        hint={button.trim() ? `“${signInWith(button.trim())}”` : undefined}
      />
      <TextField id="sso-issuer" label="Issuer address" bind:value={issuer} autocomplete="off" />
      <TextField id="sso-client" label="Client ID" bind:value={clientId} autocomplete="off" />
      <TextField
        id="sso-secret"
        label="Client secret"
        type="password"
        bind:value={secret}
        autocomplete="off"
        required={!saved?.secret_set}
        hint="Stored encrypted on the server. Leave blank to keep the saved one."
      />
      <div class="field">
        <span class="field-label" id="sso-callback-label">Give this to your sign-in server</span>
        <div class="callback">
          <span class="mono address" aria-labelledby="sso-callback-label">{redirect}</span>
          <button type="button" class="small" onclick={() => void copy()}
            >{copier.label('Copy')}</button
          >
        </div>
        {#if saved?.redirect_uri && saved.redirect_uri !== redirect}
          <span class="hint">Saved as {saved.redirect_uri}. Saving here changes it.</span>
        {/if}
      </div>
      {#if issuerHost}
        <p class="warn">
          <span
            >On your home network? Add <span class="mono">{issuerHost}</span> to Outside connections ›
            Your own network, and turn on the Single sign-on switch there.</span
          >
        </p>
      {/if}
    </section>

    <section class="card" aria-labelledby="sso-who">
      <h2 id="sso-who">2 · Who gets in, and as what</h2>
      <div class="claim">
        <TextField
          id="sso-claim"
          label="Groups come from"
          bind:value={groupClaim}
          autocomplete="off"
        />
      </div>
      {#if groups.length}
        <table>
          <thead
            ><tr><th>Group</th><th>Becomes</th><th><span class="hidden">Remove</span></th></tr
            ></thead
          >
          <tbody>
            {#each groups as row, index (index)}
              <tr>
                <td
                  ><input
                    class="mono group"
                    type="text"
                    aria-label="Group"
                    autocomplete="off"
                    bind:value={row.group}
                  /></td
                >
                <td>
                  <div class="seg" role="radiogroup" aria-label="Becomes" use:radioKeys>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={row.role === 'admin'}
                      onclick={() => (row.role = 'admin')}>Admin</button
                    >
                    <button
                      type="button"
                      role="radio"
                      aria-checked={row.role === 'member'}
                      onclick={() => (row.role = 'member')}>Member</button
                    >
                  </div>
                </td>
                <td class="end">
                  <button
                    type="button"
                    class="small"
                    aria-label="Remove this group"
                    onclick={() => removeGroup(index)}>✕</button
                  >
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
      <button type="button" class="add" onclick={addGroup}>+ Add a group</button>
      <div class="field">
        <span class="field-label" id="sso-anyone">Anyone else</span>
        <div class="seg wide" role="radiogroup" aria-labelledby="sso-anyone" use:radioKeys>
          <button
            type="button"
            role="radio"
            aria-checked={anyoneElse === 'none'}
            onclick={() => (anyoneElse = 'none')}>Not let in</button
          >
          <button
            type="button"
            role="radio"
            aria-checked={anyoneElse === 'member'}
            onclick={() => (anyoneElse = 'member')}>Member</button
          >
        </div>
      </div>
      <!-- Pe3/M2 (cabledrawer 13 Nov): nobody is made at first sign-in; the words proposed. -->
      <p class="hint">{SSO_WHO_LINKS}</p>
    </section>

    <section class="card full" aria-labelledby="sso-try">
      <h2 id="sso-try">3 · Try it, then decide about passwords</h2>
      <div class="test">
        <button
          type="button"
          class="test-button"
          disabled={!saved?.secret_set || testing}
          onclick={() => void test()}>Test sign-in</button
        >
        <span class="sub">
          {saved?.secret_set
            ? 'Opens your sign-in server in a new tab and comes back here.'
            : 'Save first, then test.'}
        </span>
      </div>
      {#if saved?.test}
        {#if saved.test.passed}
          <p class="ok" role="status">
            {testPassedText(saved.test.username, saved.test.groups, saved.test.role)}
            {#if saved.test.link === 'linked'}
              {linkedText(myUsername, saved.test.username ?? 'them')}
            {:else if saved.test.link !== 'can' && saved.test.role === 'member'}
              {NOT_LINKED_MEMBER}
            {/if}
          </p>
          {#if saved.test.link === 'can'}
            <div class="link" role="group" aria-labelledby="sso-link-question">
              <p class="link-question" id="sso-link-question">
                {linkQuestion(myUsername, saved.test.username ?? 'them')}
              </p>
              <p class="sub">
                {linkWho(saved.test.name, saved.test.email)}
                {linkNote(myUsername)}
              </p>
              <div class="actions">
                <Button disabled={linking} onclick={() => void answerLink(true)}>{LINK}</Button>
                <Button quiet disabled={linking} onclick={() => void answerLink(false)}
                  >{NOT_NOW}</Button
                >
              </div>
            </div>
          {/if}
        {:else}
          <p class="warn" role="status">{saved.test.message ?? ssoMessage(saved.test.code)}</p>
        {/if}
      {/if}
      {#if testProblem}<p class="problem" role="alert">{testProblem}</p>{/if}
      {#if saved && !saved.switch_on}
        <p class="warn">
          The Single sign-on switch in Settings › Outside connections is off, so nothing is sent to
          your sign-in server yet.
        </p>
      {/if}
      <div class="switch-row">
        <span class="who">
          <span class="label" id="sso-passwords">Allow password sign-in</span>
          <span class="detail" id="sso-passwords-detail"
            >Turn off to show only the “{signInWith(button.trim() || '…')}” button. Allowed only
            after an admin has signed in with single sign-on. The
            <span class="mono">reset-admin</span> command on the server always works.</span
          >
        </span>
        <Switch
          bind:checked={passwords}
          labelledby="sso-passwords"
          describedby="sso-passwords-detail"
          disabled={passwords && !passwordsMayGoOff}
        />
      </div>
      {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
      {#if notice}<p class="warn" role="status">{notice}</p>{/if}
      <p class="done" role="status">{done}</p>
      <div class="actions">
        <Button type="submit" disabled={busy}>{busy ? 'Saving…' : 'Save'}</Button>
        <Button quiet disabled={busy} onclick={cancel}>Cancel</Button>
      </div>
    </section>
  </form>
{/if}

<style>
  .intro {
    max-width: var(--settings-width);
    font-size: var(--text-md);
  }

  .grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: var(--space-7);
    align-items: start;
    max-width: 1100px;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-7) 18px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .card.full {
    grid-column: 1 / -1;
  }

  h2 {
    margin: 0;
    font-size: 1.0625rem;
    font-weight: var(--weight-extrabold);
  }

  .phone {
    gap: var(--space-2);
  }

  .phone-title {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .sub,
  .detail,
  .hint {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }

  .field-label {
    color: var(--color-label);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .claim {
    max-width: 260px;
  }

  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: var(--text-sm);
  }

  .callback {
    display: flex;
    gap: var(--space-3);
    align-items: center;
  }

  .address {
    flex: 1;
    min-width: 0;
    padding: 10px 12px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-field);
    background: var(--color-ground);
    overflow-wrap: anywhere;
  }

  .small {
    min-height: 36px;
    padding: 0 12px;
    border: 1px solid var(--color-border-strong);
    border-radius: 10px;
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
    cursor: pointer;
  }

  .warn,
  .ok,
  .problem {
    margin: 0;
    padding: 12px 14px;
    border-radius: var(--radius-lg);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .warn,
  .problem {
    border: 1px solid var(--color-warning-border);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .problem {
    font-weight: var(--weight-semibold);
  }

  .ok {
    background: var(--color-note);
    color: var(--color-note-text);
  }

  table {
    width: 100%;
    border-collapse: collapse;
  }

  th {
    padding: 8px 10px;
    border-bottom: 1px solid var(--color-divider);
    color: var(--color-text-muted);
    font-size: 0.75rem;
    font-weight: var(--weight-bold);
    letter-spacing: 0.05em;
    text-align: left;
    text-transform: uppercase;
  }

  td {
    padding: 10px;
    border-bottom: 1px solid var(--color-divider);
    vertical-align: middle;
  }

  tr:last-child td {
    border-bottom: none;
  }

  td.end {
    text-align: right;
  }

  .hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .group {
    box-sizing: border-box;
    width: 100%;
    min-height: 40px;
    padding: 0 10px;
    border: 1px solid var(--color-field-border);
    border-radius: 10px;
    background: var(--color-ground);
    color: var(--color-text);
  }

  .seg {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 3px;
    max-width: 220px;
    padding: 3px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-ground);
  }

  .seg.wide {
    max-width: 320px;
  }

  .seg button {
    min-height: 38px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
    cursor: pointer;
  }

  .seg button[aria-checked='true'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .add {
    align-self: flex-start;
    min-height: 44px;
    padding: 0 14px;
    border: 1px dashed var(--color-add-border);
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .switch-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: 56px;
    border-top: 1px solid var(--color-divider);
  }

  .who {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
  }

  .test {
    display: flex;
    gap: var(--space-4);
    align-items: center;
  }

  .test-button {
    display: inline-flex;
    align-items: center;
    min-height: 36px;
    padding: 0 12px;
    border: none;
    border-radius: 10px;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-bold) var(--text-sm) var(--font-ui);
    text-decoration: none;
    cursor: pointer;
  }

  .test-button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .link {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) 14px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
  }

  .link-question {
    margin: 0;
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .actions {
    display: flex;
    gap: var(--space-4);
  }

  .done {
    margin: 0;
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .done:empty {
    display: none;
  }
</style>
