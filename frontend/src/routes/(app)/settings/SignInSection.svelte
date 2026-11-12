<script lang="ts">
  // Settings → Sign-in, above Sign out (PR A2; the mockup Dark-SignInSettings09): your
  // password ("Change password", with when it last changed), where you're signed in (this
  // device tagged, every other one with its own Sign out) and "Sign out everywhere else".
  // For admins, "For the household": single sign-on (set up on a computer) and the Password
  // sign-in switch (0.9 O1). API tokens and how many there are (0.9 O2). Signing out another device has no
  // "Are you sure?": nothing is lost, it only has to sign in again.
  import { resolve } from '$app/paths';
  import { cantReach, cantReachWords, detailOf, ApiError } from '#lib/api.js';
  import { getApiTokens } from '#lib/apiTokens.js';
  import Icon from '#lib/components/Icon.svelte';
  import {
    changedText,
    deviceName,
    getMySignIn,
    placeDetail,
    signOutDevice,
    signOutEverywhereElse,
    type MySignIn
  } from '#lib/mySignIn.js';
  import { network } from '#lib/network.svelte.js';
  import { getSsoSetup, putPasswordSignIn, type SsoSetup } from '#lib/client/sso.js';
  import Switch from '#lib/components/Switch.svelte';
  import {
    NOT_SET_UP,
    PASSWORDS_NOTE,
    PASSWORD_OFF,
    PASSWORD_ON,
    SETUP_ON_COMPUTER
  } from '#lib/ssoWords.js';

  let { device, admin = false }: { device: 'phone' | 'computer'; admin?: boolean } = $props();

  let mine = $state<MySignIn | null>(null);
  let problem = $state('');
  /** Why the list couldn't be fetched: shown in its place, not read out (nothing was tapped). */
  let loadProblem = $state('');
  let busy = $state(false);
  /** How many API tokens the household has (admins only); null until known. */
  let tokens = $state<number | null>(null);
  /** Said after a sign-out here, for screen readers ("Signed out iPad · Safari."). */
  let said = $state('');

  let sso = $state<SsoSetup | null>(null);
  let passwords = $state(true);
  let ssoProblem = $state('');
  let switching = $state(false);
  /** Password sign-in may go off: an admin signs in with single sign-on, and it's switched on. */
  const passwordsMayGoOff = $derived(!!sso && sso.secret_set && sso.admin_linked && sso.switch_on);

  $effect(() => {
    void network.backAgain;
    if (!admin) return;
    void getSsoSetup()
      .then((found) => {
        sso = found;
        passwords = found.password_sign_in;
      })
      .catch(() => undefined); // the rows still show, with "Not set up"
  });

  async function setPasswords(on: boolean) {
    if (switching) return;
    switching = true;
    ssoProblem = '';
    try {
      sso = await putPasswordSignIn(on);
      passwords = sso.password_sign_in;
    } catch (error) {
      passwords = !on;
      ssoProblem = why(error);
    } finally {
      switching = false;
    }
  }

  const others = $derived(mine ? mine.sessions.filter((s) => !s.this_device) : []);

  $effect(() => {
    void network.backAgain;
    void load();
    if (admin)
      void getApiTokens()
        .then((found) => (tokens = found.tokens.length))
        .catch(() => undefined); // the row still leads to the list, which says what's wrong
  });

  function why(error: unknown): string {
    if (cantReach(error)) return cantReachWords();
    if (error instanceof ApiError) return error.detail;
    return detailOf(null);
  }

  async function load() {
    try {
      mine = await getMySignIn();
      loadProblem = '';
    } catch (error) {
      loadProblem = why(error);
    }
  }

  async function run(job: () => Promise<MySignIn>, done: string) {
    if (busy) return;
    busy = true;
    problem = '';
    said = '';
    try {
      mine = await job();
      said = done;
    } catch (error) {
      problem = why(error);
      // An already-ended sign-in: show the list as it is now.
      if (error instanceof ApiError && error.status === 404) await load();
    } finally {
      busy = false;
    }
  }
</script>

<h3 class="sub-title">Your password</h3>
<div class="card">
  <a class="row to" href={resolve('/(app)/settings/password')}>
    <span class="who">
      <span class="label">Change password</span>
      {#if mine && changedText(mine)}<span class="detail">{changedText(mine)}</span>{/if}
    </span>
    <Icon name="back" size={18} stroke={2.4} />
  </a>
</div>

<h3 class="sub-title">Where you’re signed in</h3>
<div class="card" data-testid="signed-in-places">
  {#if mine === null}
    <p class="row detail">{loadProblem || 'Loading…'}</p>
  {:else}
    {#each mine.sessions as place (place.id)}
      <div class="row">
        <span class="who">
          <span class="label">{deviceName(place)}</span>
          <span class="detail">{placeDetail(place)}</span>
        </span>
        {#if place.this_device}
          <span class="tag">This {device}</span>
        {:else}
          <button
            type="button"
            class="small"
            aria-label="Sign out {deviceName(place)}"
            disabled={busy || network.offline}
            onclick={() =>
              void run(() => signOutDevice(place.id), `Signed out ${deviceName(place)}.`)}
            >Sign out</button
          >
        {/if}
      </div>
    {/each}
  {/if}
</div>
{#if problem}<p class="warning-line" role="alert">{problem}</p>{/if}
<p class="said" role="status">{said}</p>
{#if others.length > 0}
  <button
    type="button"
    class="everywhere"
    disabled={busy || network.offline}
    onclick={() => void run(signOutEverywhereElse, 'Signed out everywhere else.')}
    >Sign out everywhere else</button
  >
{/if}

{#if admin}
  <h3 class="sub-title">For the household (admins)</h3>
  <div class="card" data-testid="household-sign-in">
    <a class="row to" href={resolve('/(app)/settings/sso')}>
      <span class="who">
        <span class="label">Single sign-on</span>
        {#if device === 'phone'}<span class="detail">{SETUP_ON_COMPUTER}</span>{/if}
      </span>
      <span class="value">{sso?.secret_set ? sso.button_name : NOT_SET_UP}</span>
      <Icon name="back" size={18} stroke={2.4} />
    </a>
    <div class="row">
      <span class="who">
        <span class="label" id="passwords-label">Password sign-in</span>
        <span class="detail" id="passwords-detail">{passwords ? PASSWORD_ON : PASSWORD_OFF}</span>
      </span>
      <Switch
        bind:checked={passwords}
        labelledby="passwords-label"
        describedby="passwords-detail"
        disabled={switching || network.offline || (passwords && !passwordsMayGoOff)}
        onchange={(on) => void setPasswords(on)}
      />
    </div>
    <a class="row to" href={resolve('/(app)/settings/api-tokens')}>
      <span class="who"><span class="label">API tokens</span></span>
      {#if tokens !== null}<span class="count" data-testid="api-token-count">{tokens}</span>{/if}
      <Icon name="back" size={18} stroke={2.4} />
    </a>
  </div>
  {#if ssoProblem}<p class="warning-line" role="alert">{ssoProblem}</p>{/if}
  <p class="note">{PASSWORDS_NOTE}</p>
{/if}

<style>
  .value {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    white-space: nowrap;
  }

  .note {
    margin: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .sub-title {
    margin: var(--space-2) 0 0;
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    padding: var(--space-1) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: 54px;
    margin: 0;
    padding: var(--space-4) 0;
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
  }

  .count {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .to {
    color: inherit;
    text-decoration: none;
  }

  .to :global(svg) {
    flex: none;
    color: var(--color-text-muted);
    transform: scaleX(-1);
  }

  .tag {
    padding: var(--space-1) var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .small,
  .everywhere {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-button);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .everywhere {
    align-self: stretch;
  }

  .small:disabled,
  .everywhere:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .warning-line {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .said {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
