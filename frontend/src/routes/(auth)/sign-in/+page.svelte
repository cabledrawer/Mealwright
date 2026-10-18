<script lang="ts">
  // Changes still waiting on this phone (sync protocol 11.5, section 16 decision 4): the
  // same person signing back in sends them at once (the app does that on starting). Anyone
  // else is warned first, and never sends them. A different login always starts clean
  // (cabledrawer 18 Oct): once its sign-in has succeeded, and only then, the phone's copy is
  // wiped as at signing out, and the next start makes a new device ID. A wrong password
  // wipes nothing. A phone database that can't be read wipes nothing either: the login it was
  // last written for carries on (it never wipes anything, so nothing is at risk); anyone else
  // is warned that it couldn't check, with "Try again" and "Carry on anyway — anything waiting
  // on this phone may be lost" (cabledrawer 18 Oct). When the server wouldn't end a session the
  // app was signing out, the page says so, with "Try again" (it stays here meanwhile). And
  // when a wipe couldn't delete the phone database, nobody can sign in until it has: the
  // page says so, with "Try again", and the whole sign-in form is disabled until Try again
  // has deleted it (cabledrawer 18 Oct). A wipe another tab is still running isn't a failure:
  // nothing is said about it unless it fails.
  import { tick, untrack } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { ApiError, signIn } from '$lib/api';
  import Button from '$lib/components/Button.svelte';
  import ConnectionNotice from '$lib/components/ConnectionNotice.svelte';
  import Switch from '$lib/components/Switch.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import { rememberedLogin } from '$lib/offline/device';
  import {
    cantCheckText,
    heldChanges,
    keptText,
    loseOthersText,
    sameUsername,
    signedOutBecauseText,
    takeTurnedAway,
    unfinishedText,
    UNREADABLE,
    waitingForText,
    stillStuckText,
    wipeFailedText,
    type Held,
    type Unreadable
  } from '$lib/offline/held';
  import { endSession } from '$lib/offline/signOut';
  import { signOutState } from '$lib/offline/unfinished.svelte';
  import { wipeDevice, wipeIfAnotherLogin } from '$lib/offline/wipe';
  import { heardWipe, wipeFailed, wipeState } from '$lib/offline/wipePending.svelte';
  import { connection, safeNext, session } from '$lib/session.svelte';
  import { theme } from '$lib/theme.svelte';
  import type { PageProps } from './$types';

  let { data }: PageProps = $props();

  // Filled in when the app has just turned this login away over someone's waiting changes.
  const turnedAway = takeTurnedAway();
  let username = $state(turnedAway);
  let password = $state('');
  let remember = $state(true);
  let busy = $state(false);
  let problem = $state('');

  const secure = $derived(connection(window.isSecureContext, data.setup.plain_http_allowed));
  const device = matchMedia('(max-width: 767px)').matches ? 'phone' : 'computer';

  /** Someone's changes waiting on this phone, or UNREADABLE when it couldn't check. */
  let held = $state<Held | null | Unreadable>(null);
  const unreadable = $derived(held === UNREADABLE);
  const waiting = $derived(held === UNREADABLE ? null : held);
  /** "Wren's 3 changes haven't been sent yet. If you carry on, they're lost." */
  let warning = $state(false);
  /** "Carry on and lose them" was chosen for this username. */
  let losing = false;
  /** The phone couldn't check, and Sign in was pressed: the warning with its two choices. */
  let cantWarning = $state(false);
  /** "Carry on anyway — anything waiting on this phone may be lost" was chosen. */
  let anyway = false;

  $effect(() => {
    void heldChanges().then((found) => (held = found));
  });

  // A wipe (in this tab, another, or before a reload) that couldn't delete the phone database.
  // Not one another tab is still running: that says so only if it fails (heardWipe).
  if (wipeFailed()) wipeState.failed = true;
  $effect(() => {
    addEventListener('storage', heardWipe);
    return () => removeEventListener('storage', heardWipe);
  });
  /** Tries that found the wipe still unfinished: the line is read out again each time. */
  let wipeTries = $state(0);
  let wiping = $state(false);

  /** The wipe failed: the sign-in form is disabled, and only Try again works. */
  const locked = $derived(wipeState.failed);

  /** Wipe again (Try again). True once the phone database is gone. */
  async function wipeAgain(): Promise<boolean> {
    wiping = true;
    try {
      const done = await wipeDevice();
      if (done) held = null;
      else wipeTries++;
      return done;
    } finally {
      wiping = false;
    }
  }

  const someoneElse = $derived(
    !!waiting && username.trim() !== '' && !sameUsername(username, waiting.who)
  );
  /**
   * Just turned away, still as that username, and the server did end the session: the line
   * says why ("You were signed out because Wren's change is waiting…").
   */
  const signedOut = $derived(
    someoneElse &&
      turnedAway !== '' &&
      username.trim().toLowerCase() === turnedAway.trim().toLowerCase() &&
      !signOutState.unfinished
  );
  const heldText = $derived(
    !waiting
      ? ''
      : signedOut
        ? signedOutBecauseText(waiting.who.name, waiting.count, device)
        : someoneElse
          ? waitingForText(waiting.who.name, waiting.count, device)
          : keptText(waiting.count, device)
  );

  // Typing another username takes the warning away until Sign in is pressed again.
  $effect(() => {
    void username;
    untrack(() => {
      warning = false;
      cantWarning = false;
    });
    losing = false;
    anyway = false;
  });

  function submit(event: SubmitEvent) {
    event.preventDefault();
    void go();
  }

  /**
   * Sign in, as pressed. Every press shows (and reads out) what happened. Busy from the first
   * press, while the phone is read and while the server answers, so a fast second press (or
   * Enter) starts nothing more.
   */
  async function go() {
    if (busy) return;
    busy = true;
    try {
      await look();
    } finally {
      busy = false;
    }
  }

  /** What a press of Sign in does, once it has the page to itself (busy). */
  async function look() {
    problem = '';
    losing = false;
    anyway = false;
    // Nobody signs in until an unfinished wipe has deleted the phone database: the form is
    // disabled meanwhile, and only Try again works (wipeAgain).
    if (wipeState.failed) return;
    // Read again: another tab may have queued changes since this page opened.
    held = await heldChanges();
    if (held === UNREADABLE) {
      // Couldn't check. The login the phone database is for carries on: it never wipes
      // anything. Anyone else is warned first, and nothing is sent yet.
      const known = rememberedLogin();
      if (known && sameUsername(username, known)) await signInNow();
      else await warnCantCheck();
      return;
    }
    cantWarning = false;
    if (someoneElse) {
      warning = true;
      return;
    }
    await signInNow();
  }

  /** The couldn't-check warning's Try again: looks again, as Sign in does. */
  let trying = $state(false);
  async function tryAgain() {
    trying = true;
    try {
      await go();
    } finally {
      trying = false;
    }
  }

  /** Show the couldn't-check warning, put back as new so it's read out again. */
  async function warnCantCheck() {
    cantWarning = false;
    await tick();
    cantWarning = true;
  }

  /** Nothing is wiped yet: only once this sign-in has succeeded (signInNow). */
  async function carryOnAnyway() {
    if (busy) return;
    busy = true;
    try {
      anyway = true;
      cantWarning = false;
      await signInNow();
    } finally {
      busy = false;
    }
  }

  async function asThem() {
    if (!waiting) return;
    username = waiting.who.username;
    password = '';
    await tick();
    warning = false;
    document.getElementById('password')?.focus();
  }

  /** Nothing is wiped yet: only once this sign-in has succeeded (signInNow). */
  async function carryOn() {
    if (busy) return;
    busy = true;
    try {
      losing = true;
      warning = false;
      await signInNow();
    } finally {
      busy = false;
    }
  }

  /** "Couldn't finish signing out": ask the server again. */
  let ending = $state(false);
  /** Asks the page made that the server refused: the line is read out again each time. */
  let endTries = $state(0);
  async function endAgain() {
    ending = true;
    try {
      await endHere();
    } finally {
      ending = false;
    }
  }

  /** End the session; when the server won't, say so again. */
  async function endHere() {
    if (!(await endSession())) endTries++;
  }

  async function signInNow() {
    // Not while the wipe hasn't finished (another tab's may have failed since a warning came up).
    if (wipeState.failed) return;
    try {
      const me = await signIn(username, password, remember);
      // Another login than the one this phone holds starts clean, as at sign-out, but never
      // over waiting changes the warning hasn't shown (read again just now, as another tab
      // may have queued some since).
      const result = await wipeIfAnotherLogin(me, anyway ? 'anyway' : losing ? waiting : null);
      losing = false;
      anyway = false;
      if (result === 'wipe-failed') {
        // Nobody is let in until the phone database is deleted: end this session again.
        await endHere();
        warning = false;
        held = null;
        wipeTries++;
        return;
      }
      if (result !== 'kept' && result !== 'wiped') {
        // Another login after all, or the phone couldn't check: end that session again before
        // anything is sent, and warn.
        await endHere();
        held = result;
        warning = result !== UNREADABLE;
        if (result === UNREADABLE) await warnCantCheck();
        return;
      }
      if (result === 'wiped') held = null;
      // Signed in afresh: any session that couldn't be ended isn't this browser's any more.
      signOutState.unfinished = false;
      session.me = me;
      theme.adopt(me.theme);
      const next = safeNext(page.url.searchParams.get('next'));
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- safeNext only returns pages of this app
      await goto(next, { replaceState: true, invalidateAll: true });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      problem = error.detail;
      password = '';
    }
  }
</script>

<svelte:head>
  <title>Sign in · Mealwright</title>
</svelte:head>

<div class="heading">
  <h1>Welcome back</h1>
  <p>Sign in to your household's kitchen</p>
</div>

<ConnectionNotice kind={secure} />

{#if signOutState.unfinished}
  <div class="unfinished">
    {#key endTries}
      <!-- On opening the page a status; after a press the server refused, an alert. -->
      <p role={endTries > 0 ? 'alert' : 'status'}>{unfinishedText(device)}</p>
    {/key}
    <!-- The grey (quiet) look on this screen only; every other Try again is the main button. -->
    <Button quiet disabled={ending} onclick={() => void endAgain()}>
      {ending ? 'Trying…' : 'Try again'}
    </Button>
  </div>
{/if}

{#if wipeState.failed}
  <div class="unfinished">
    {#key wipeTries}
      <!-- On opening the page a status; after a press that didn't help, an alert. -->
      <p role={wipeTries > 0 ? 'alert' : 'status'}>{wipeFailedText(device)}</p>
    {/key}
    <p class="still-stuck">{stillStuckText}</p>
    <Button disabled={wiping} onclick={() => void wipeAgain()}>
      {wiping ? 'Trying…' : 'Try again'}
    </Button>
  </div>
{/if}

{#if unreadable && !cantWarning}
  <p class="cant-check" role="status">{cantCheckText(device)}</p>
{:else if waiting}
  <p class="held" role="status">{heldText}</p>
{/if}

{#if secure !== 'plain-refused'}
  <form onsubmit={submit} novalidate class:locked>
    <TextField
      id="username"
      label="Username"
      bind:value={username}
      autocomplete="username"
      disabled={locked}
    />
    <TextField
      id="password"
      label="Password"
      type="password"
      bind:value={password}
      autocomplete="current-password"
      disabled={locked}
    />
    <div class="remember">
      <span class="remember-text">
        <span id="remember-label" class="remember-label">Remember this {device}</span>
        <span id="remember-hint" class="remember-hint">Stay signed in for 30 days</span>
      </span>
      <Switch
        bind:checked={remember}
        labelledby="remember-label"
        describedby="remember-hint"
        disabled={locked}
      />
    </div>
    {#if problem}
      <p class="problem" role="alert">{problem}</p>
    {/if}
    <!-- While the wipe hasn't finished, no warning's choices either: only Try again works. -->
    {#if warning && waiting && !locked}
      <div class="warning">
        <p role="alert">{loseOthersText(waiting.who.name, waiting.count)}</p>
        <Button disabled={busy} onclick={() => void asThem()}
          >Sign in as {waiting.who.name} instead</Button
        >
        <button type="button" class="lose" disabled={busy} onclick={() => void carryOn()}>
          Carry on and lose {waiting.count === 1 ? 'it' : 'them'}
        </button>
      </div>
    {:else if cantWarning && unreadable && !locked}
      <div class="warning">
        <p role="alert">{cantCheckText(device)}</p>
        <Button disabled={busy || trying} onclick={() => void tryAgain()}>
          {trying ? 'Trying…' : 'Try again'}
        </Button>
        <button type="button" class="lose" disabled={busy} onclick={() => void carryOnAnyway()}>
          Carry on anyway — anything waiting on this {device} may be lost
        </button>
      </div>
    {:else}
      <Button type="submit" disabled={busy || locked}>{busy ? 'Signing in…' : 'Sign in'}</Button>
    {/if}
  </form>

  <p class="forgot">Forgot your password? Ask your household's admin to reset it.</p>
{/if}

<style>
  .heading {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    text-align: center;
  }

  h1 {
    font-size: 1.625rem;
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
    word-spacing: normal;
  }

  .heading p,
  .forgot {
    color: var(--color-text-muted);
    font-size: var(--text-lg);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  /* Disabled while the wipe hasn't finished: dimmed, so it plainly can't be used. */
  form.locked {
    opacity: 0.55;
  }

  .remember {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-6);
    min-height: var(--touch-target);
  }

  .remember-text {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .remember-label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .remember-hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .problem,
  .cant-check,
  .unfinished p {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .unfinished {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
  }

  .unfinished p {
    align-self: stretch;
  }

  /* Small, quiet text under the message: no warning box of its own. */
  .unfinished p.still-stuck {
    padding: 0 14px;
    background: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-regular);
  }

  .held {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-offline);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .warning {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .warning p {
    padding: var(--space-5) 14px;
    border-radius: var(--radius-field);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .lose {
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: none;
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  .forgot {
    font-size: var(--text-base);
    line-height: 1.5;
    text-align: center;
  }

  @media (min-width: 768px) {
    .heading {
      text-align: left;
    }
    h1 {
      font-size: 1.75rem;
    }
  }
</style>
