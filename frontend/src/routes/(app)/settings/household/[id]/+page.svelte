<script lang="ts">
  // Settings → Household → a person (0.9 A1, mockup Dark-Person09-Phone): their name, colour and
  // portion, whether they sign in (a one-time sign-in link, and their role), Save, and Remove.
  // Everyone sees it; only an admin changes it. Save and Remove each have their Undo (the toast,
  // Ctrl+Z, Recent changes).
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { onDestroy, onMount } from 'svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import LinkSignIn from '#lib/components/people/LinkSignIn.svelte';
  import PersonAvatar from '#lib/components/people/PersonAvatar.svelte';
  import {
    COLOURS,
    PORTION_CHOICES,
    cancelMyResetLink,
    giveLogin,
    portionWords,
    resetPassword,
    takeBackLogin,
    type Colour,
    type Person,
    type PersonChange,
    type Role
  } from '#lib/client/people.js';
  import { CopyFeedback } from '#lib/copyFeedback.svelte.js';
  import { dayMonthWords } from '#lib/dates.js';
  import { network } from '#lib/network.svelte.js';
  import { household, sentence } from '#lib/people.svelte.js';
  import {
    LINK_BY_HAND,
    NOT_LINKED_LINE,
    SSO_ROW,
    UNLINK,
    linkedParts
  } from '#lib/ssoWaitingWords.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { whenWords } from '#lib/yourDataWords.js';

  const id = $derived(Number(page.params.id));
  const person: Person | undefined = $derived(household.people.find((p) => p.id === id));
  const locked = $derived(!household.canChange || network.offline);

  // What's on the form: starts as the person, and Save sends what differs.
  let name = $state('');
  let colour = $state<Colour | null>(null);
  let portion = $state(4);
  let role = $state<Role>('member');
  let shared = $state(false);
  /** "Give a login" chosen for someone without one: the username and role fields show. */
  let giving = $state(false);
  let username = $state('');
  /** The sign-in link just made, shown once (never stored on the server). */
  let link = $state<string | null>(null);
  /** The Reset password link just made (Pe1), shown once the same way. */
  let resetLink = $state<string | null>(null);
  let problem = $state<string | null>(null);
  let loginProblem = $state<string | null>(null);
  let filledFor: number | null = null;

  function fill(from: Person) {
    filledFor = from.id;
    name = from.name;
    colour = from.colour;
    portion = from.portion_quarters;
    role = from.login?.role ?? 'member';
    shared = from.login?.shared ?? false;
    username = from.login?.username ?? suggestedUsername(from.name);
    giving = false;
    link = null;
    resetLink = null;
    problem = null;
    loginProblem = null;
  }

  /** "Joss Roe" → "joss.roe": a starting point the admin can change (cabledrawer 12 Nov). */
  function suggestedUsername(of: string): string {
    return of
      .normalize('NFKD')
      .replace(/[̀-ͯ]/g, '')
      .toLowerCase()
      .trim()
      .replace(/\s+/g, '.')
      .replace(/[^a-z0-9._-]/g, '')
      .slice(0, 50);
  }

  onMount(() => {
    if (!household.loaded) void household.load();
  });

  // Opening another person, or the list arriving: fill the form from them.
  $effect(() => {
    if (person && filledFor !== person.id) fill(person);
  });

  /** Picks of a colour or portion on their way to the server (they save as you pick). */
  let picking = $state(0);
  /** The number of the newest pick: only it may put the old value back. */
  let newest = 0;
  /** How many picks overlapped since none was on its way. */
  let burst = 0;
  // Whenever the list refreshes (an Undo of a pick, another device) and no pick is on its way,
  // the colour and portion show what the person has now, so Save can't send an old pick again.
  $effect(() => {
    if (person && picking === 0 && filledFor === person.id) {
      colour = person.colour;
      portion = person.portion_quarters;
    }
  });

  const login = $derived(person?.login ?? null);
  /** Profile only, or a login whose link is still unused (or ran out): the choice shows. */
  const canChoose = $derived(!login || !login.signs_in);
  const signsIn = $derived(giving || !!login);

  const changes: PersonChange = $derived.by(() => {
    if (!person) return {};
    const out: PersonChange = {};
    if (name.trim() !== person.name) out.name = name.trim();
    if (colour !== person.colour) out.colour = colour;
    if (portion !== person.portion_quarters) out.portion_quarters = portion;
    if (login && role !== login.role) out.role = role;
    if (login?.signs_in && shared !== login.shared) out.shared = shared;
    return out;
  });

  const added = $derived.by(() => {
    if (!person) return '';
    const at = new Date(person.created_at);
    const day = `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')}`;
    const by = person.created_by_name.trim();
    return by ? `Added ${dayMonthWords(day)} by ${by}` : `Added ${dayMonthWords(day)}`;
  });

  const linkUrl = $derived(link ? `${location.origin}${link}` : '');
  const resetUrl = $derived(resetLink ? `${location.origin}${resetLink}` : '');

  /**
   * "Link used today 21:40" (cabledrawer 13 Nov): an admin can spot a link someone else used. In the
   * household's time zone, like every date in the app (16b review R-L4).
   */
  const linkUsed = $derived.by(() => {
    if (!login?.link_used_at) return null;
    const when = whenWords(login.link_used_at, new Date(), household.zone).replace(
      /^(Today|Yesterday) /,
      (w) => w.toLowerCase()
    );
    return `Link used ${when}`;
  });

  /** Only an admin resets someone else's password; their own is Settings → Sign-in. */
  const canReset = $derived(household.canChange && !!person && !person.is_me);

  /**
   * The only admin who signs in: if they forget their own password, nobody here can reset it,
   * so the page says where the way back is (Pe1; shown to that admin, proposed, for cabledrawer).
   */
  const onlyAdmin = $derived(
    household.canChange &&
      household.people.filter((p) => p.login?.role === 'admin' && p.login.signs_in).length === 1
  );

  /**
   * Your own page, and you are the household's only admin who signs in: the Role buttons are
   * switched off for yourself, so say why in the server's own words (F238, hand test 15 Nov).
   */
  const onlyAdminYou = $derived(!!person?.is_me && login?.role === 'admin' && onlyAdmin);

  /**
   * Single sign-on (0.9.5 Pe3/M2): for an admin while it is set up, whether this person is linked
   * to an account at the sign-in server, with Unlink or Link…. Never for a shared login.
   */
  const showSso = $derived(household.canChange && household.singleSignOn && !login?.shared);
  /** The Link… sheet is open. */
  let linking = $state(false);

  async function unlink() {
    if (!person || locked || household.busy) return;
    loginProblem = null;
    try {
      await household.unlink(person.id);
    } catch (error) {
      loginProblem = sentence(error);
    }
  }

  async function linkTo(accountId: number) {
    if (!person) return;
    if (await household.link(accountId, person.id)) linking = false;
  }

  async function back() {
    await goto(resolve('/(app)/settings/household'));
  }

  async function save() {
    if (!person || locked || household.busy || picking > 0) return;
    problem = null;
    if (Object.keys(changes).length === 0) return back();
    try {
      if (await household.change(person.id, changes)) await back();
    } catch (error) {
      problem = sentence(error);
    }
  }

  /**
   * Colour and portion save as you pick them (cabledrawer 13 Nov, hunt L4): no Save press. A refusal
   * or a lost connection says so and puts the person's old value back. While offline the pickers
   * are off, like every other control on this page.
   */
  async function saveNow(change: PersonChange, back: () => void) {
    if (!person || locked) return;
    problem = null;
    const mine = ++newest;
    burst += 1;
    picking += 1;
    try {
      await household.change(person.id, change);
    } catch (error) {
      // Only the newest pick puts the old value back: an earlier one failing while a later one
      // is on its way must not undo what the server is about to keep.
      if (mine === newest) {
        back();
        problem = sentence(error);
      }
    } finally {
      picking -= 1;
      // Replies can come back out of order: after a burst, read the person again.
      if (picking === 0) {
        const overlapped = burst > 1;
        burst = 0;
        if (overlapped) void household.load();
      }
    }
  }

  function pickColour(one: Colour) {
    if (!person || one === colour) return;
    colour = one;
    void saveNow({ colour: one }, () => (colour = person.colour));
  }

  function pickPortion(quarters: number) {
    if (!person || quarters === portion) return;
    portion = quarters;
    void saveNow({ portion_quarters: quarters }, () => (portion = person.portion_quarters));
  }

  async function remove() {
    if (!person || locked || household.busy || picking > 0) return;
    problem = null;
    try {
      if (await household.remove(person.id)) await back();
    } catch (error) {
      problem = sentence(error);
    }
  }

  async function makeLink() {
    if (!person || locked) return;
    loginProblem = null;
    try {
      const made = await giveLogin(person.id, username.trim(), role);
      link = made.path;
      await household.load();
    } catch (error) {
      loginProblem = sentence(error);
    }
  }

  async function profileOnly() {
    if (!person || locked) return;
    loginProblem = null;
    if (!login) {
      giving = false;
      return;
    }
    try {
      await takeBackLogin(person.id);
      link = null;
      giving = false;
      await household.load();
    } catch (error) {
      loginProblem = sentence(error);
    }
  }

  async function reset() {
    if (!person || locked) return;
    loginProblem = null;
    try {
      const made = await resetPassword(person.id);
      resetLink = made.path;
      await household.load();
    } catch (error) {
      loginProblem = sentence(error);
    }
  }

  /**
   * Your own pending reset link (16b security pass S-M1 e): you can cancel it, admin or not, if
   * you didn't ask for one. Your password stays as it is.
   */
  async function cancelReset() {
    if (network.offline) return;
    loginProblem = null;
    try {
      await cancelMyResetLink();
      await household.load();
      toasts.show('Reset link cancelled');
    } catch (error) {
      loginProblem = sentence(error);
    }
  }

  const resetCopier = new CopyFeedback();
  const linkCopier = new CopyFeedback();
  onDestroy(() => {
    resetCopier.dispose();
    linkCopier.dispose();
  });

  async function copy(url: string, copier: CopyFeedback) {
    if (await copier.copy(url)) {
      toasts.show('Link copied');
    } else {
      toasts.show('Couldn’t copy. Select the link and copy it.', { tone: 'problem' });
    }
  }
</script>

<PageHeader
  title={person?.name ?? 'Person'}
  parent={{ href: '/(app)/settings/household', label: 'People' }}
/>

{#if !household.loaded}
  {#if network.down}
    <OfflineNote screen="Household" />
  {:else if household.problem}
    <p class="problem" role="alert">
      {household.problem}
      <button type="button" class="link" onclick={() => void household.load()}>Try again</button>
    </p>
  {:else}
    <p class="loading" role="status">Loading…</p>
  {/if}
{:else if !person}
  <p class="problem" role="alert">
    This person isn’t in the household any more.
    <a class="link" href={resolve('/(app)/settings/household')}>Household</a>
  </p>
{:else}
  <div class="page">
    <div class="who">
      <PersonAvatar id={person.id} name={person.name} colour={colour ?? person.colour} size={56} />
      <p class="added">{added}</p>
    </div>

    <div class="card">
      <div class="field">
        <label for="person-name">Name</label>
        <input
          id="person-name"
          type="text"
          autocomplete="off"
          maxlength="40"
          bind:value={name}
          disabled={locked}
        />
      </div>

      <fieldset class="field" disabled={locked}>
        <legend>Colour</legend>
        <div class="swatches">
          {#each COLOURS as one (one)}
            <button
              type="button"
              class="swatch"
              aria-label={one[0]?.toUpperCase() + one.slice(1)}
              aria-pressed={colour === one}
              style:background="var(--person-{one}-swatch)"
              onclick={() => pickColour(one)}
            ></button>
          {/each}
        </div>
      </fieldset>

      <fieldset class="field" disabled={locked}>
        <legend>Eats</legend>
        <div class="chips">
          {#each PORTION_CHOICES as quarters (quarters)}
            <button
              type="button"
              class="chip"
              aria-pressed={portion === quarters}
              aria-label={portionWords(quarters)}
              onclick={() => pickPortion(quarters)}
              >{portion === quarters && quarters < 4
                ? portionWords(quarters)
                : portionWords(quarters).split(' ')[0]}</button
            >
          {/each}
        </div>
      </fieldset>
    </div>

    <div class="card">
      {#if canChoose && !(person.is_me && login)}
        <fieldset class="field" disabled={locked}>
          <legend>Signs in?</legend>
          <div class="seg">
            <button type="button" aria-pressed={!signsIn} onclick={() => void profileOnly()}
              >Profile only</button
            >
            <button
              type="button"
              aria-pressed={signsIn}
              onclick={() => {
                giving = true;
              }}>Give a login</button
            >
          </div>
        </fieldset>
      {:else}
        <h2 class="card-title">Signs in</h2>
      {/if}

      {#if !signsIn}
        <p class="sub">
          {person.name} has no login, but still counts for portions and can be picked in “Who’s this?”.
        </p>
      {:else}
        {#if !login}
          <div class="field">
            <label for="person-username">Username</label>
            <input
              id="person-username"
              type="text"
              autocomplete="off"
              autocapitalize="none"
              spellcheck="false"
              maxlength="50"
              bind:value={username}
              disabled={locked}
            />
          </div>
        {:else}
          <p class="username">Username: <strong>{login.username}</strong></p>
        {/if}

        <fieldset class="field" disabled={locked || person.is_me}>
          <legend>Role</legend>
          <div class="seg">
            <button type="button" aria-pressed={role === 'admin'} onclick={() => (role = 'admin')}
              >Admin</button
            >
            <button type="button" aria-pressed={role === 'member'} onclick={() => (role = 'member')}
              >Member</button
            >
          </div>
          <span class="hint"
            >Members cook, plan and shop. Admins also change Settings and people.</span
          >
          {#if onlyAdminYou}
            <span class="hint" data-only-admin
              >{person?.name} is the household’s only admin. Make someone else an admin first.</span
            >
          {/if}
        </fieldset>

        {#if login?.signs_in && !person.is_me}
          <div class="switch-row">
            <span class="words">
              <span class="label" id="shared-label">Shared login</span>
              <span class="hint" id="shared-detail"
                >A kitchen tablet everyone uses: it can ask “Who’s this?”</span
              >
              <span class="hint" id="shared-eats"
                >A shared login isn’t counted as someone who eats.</span
              >
            </span>
            <Switch
              bind:checked={shared}
              labelledby="shared-label"
              describedby="shared-detail shared-eats"
              disabled={locked}
            />
          </div>
        {/if}

        {#if login?.has_password}
          <div class="switch-row">
            <span class="words">
              <span class="label">Password</span>
              {#if linkUsed}<span class="hint">{linkUsed}</span>{/if}
            </span>
            {#if canReset}
              <button class="quiet sm" type="button" disabled={locked} onclick={() => void reset()}
                >Reset password</button
              >
            {/if}
          </div>
          {#if resetLink}
            <div class="ok" role="status">
              <span
                ><strong>Reset link made.</strong> It works once, for 24 hours. Send it to {person.name}:
                they pick a new password, and their recipes, plans and history stay as they are.</span
              >
              <span class="mono">{resetUrl}</span>
            </div>
            <button class="quiet" type="button" onclick={() => void copy(resetUrl, resetCopier)}
              >{resetCopier.label('Copy the link')}</button
            >
          {:else if login.reset_pending && canReset}
            <p class="sub">{person.name} hasn’t used the reset link yet.</p>
          {:else if login.reset_pending && person.is_me}
            <!-- proposed, for cabledrawer -->
            <p class="sub">
              Someone made a reset link for your password, and it hasn’t been used yet. If you
              didn’t ask for one, cancel it.
            </p>
            <button
              class="quiet"
              type="button"
              disabled={network.offline}
              onclick={() => void cancelReset()}>Cancel the link</button
            >
          {/if}
        {:else if linkUsed}
          <p class="hint">{linkUsed}</p>
        {/if}

        {#if link}
          <div class="ok" role="status">
            <span
              >Sign-in link made. It works once, for 24 hours: send it to {person.name} to choose a password.</span
            >
            <span class="mono">{linkUrl}</span>
          </div>
          <button class="quiet" type="button" onclick={() => void copy(linkUrl, linkCopier)}
            >{linkCopier.label('Copy the link')}</button
          >
        {:else if !login}
          <button
            class="quiet"
            type="button"
            disabled={locked || !username.trim()}
            onclick={() => void makeLink()}>Make the sign-in link</button
          >
        {:else if !login.signs_in}
          <p class="sub">
            {login.link_pending
              ? `${person.name} hasn’t used the sign-in link yet.`
              : `${person.name}’s sign-in link no longer works.`}
          </p>
          <button class="quiet" type="button" disabled={locked} onclick={() => void makeLink()}
            >Make a new link</button
          >
        {/if}
      {/if}
      {#if showSso}
        <div class="switch-row sso">
          <span class="words">
            <span class="label">{SSO_ROW}</span>
            {#if login?.sso_linked}
              {@const [before, username, after] = linkedParts(login.sso_username)}
              <span class="hint"
                >{before}{#if username}<strong>{username}</strong>{/if}{after}</span
              >
            {:else}
              <span class="hint">{NOT_LINKED_LINE}</span>
            {/if}
          </span>
          {#if login?.sso_linked}
            <button class="quiet sm" type="button" disabled={locked} onclick={() => void unlink()}
              >{UNLINK}</button
            >
          {:else}
            <button
              class="quiet sm"
              type="button"
              disabled={locked}
              onclick={() => (linking = true)}>{LINK_BY_HAND}</button
            >
          {/if}
        </div>
      {/if}
      {#if loginProblem}
        <p class="problem" role="alert">{loginProblem}</p>
      {/if}
    </div>

    {#if showSso}
      <LinkSignIn
        {person}
        open={linking}
        waiting={household.waiting}
        zone={household.zone}
        busy={household.busy}
        offline={network.offline}
        onlink={linkTo}
        onclose={() => (linking = false)}
      />
    {/if}

    {#if onlyAdmin && login?.has_password && (person.is_me || resetLink)}
      <p class="note">
        Forgotten your own password and you’re the only admin? Use <span class="mono"
          >reset-admin</span
        >
        on the server (How to restore, step 2).
      </p>
    {/if}

    {#if problem}
      <p class="problem" role="alert">{problem}</p>
    {/if}

    {#if household.canChange}
      <button
        class="primary"
        type="button"
        disabled={locked || picking > 0}
        onclick={() => void save()}>Save</button
      >
      {#if !person.is_me}
        <button
          class="quiet danger"
          type="button"
          disabled={locked || picking > 0}
          onclick={() => void remove()}>Remove {person.name}</button
        >
        <p class="note">
          Removing someone keeps their meals and history; Recent changes shows “{person.name} (removed)”.
          Undo for {household.undoDays}
          {household.undoDays === 1 ? 'day' : 'days'}.
        </p>
      {/if}
    {:else}
      <p class="note">Only admins can add, change or remove people.</p>
    {/if}
  </div>
{/if}

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 640px;
  }

  .who {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .added,
  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: 14px var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .card-title {
    color: var(--color-text-soft);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  fieldset {
    margin: 0;
    padding: 0;
    border: none;
    min-width: 0;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .field > label,
  legend {
    padding: 0;
    margin-bottom: var(--space-3);
    color: var(--color-text-soft);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .field > label {
    margin-bottom: 0;
  }

  input {
    width: 100%;
    min-height: 46px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-size: 1rem;
    font-weight: var(--weight-medium);
  }

  input:disabled {
    opacity: 0.7;
  }

  .swatches {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-5);
  }

  /* 36 px to see, 44 px to tap. */
  .swatch {
    width: 36px;
    height: 36px;
    margin: 4px;
    border: 3px solid transparent;
    border-radius: 50%;
    cursor: pointer;
  }

  .swatch[aria-pressed='true'] {
    border-color: var(--color-text);
    box-shadow: 0 0 0 2px var(--color-surface) inset;
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .chip {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-field);
    color: var(--color-text-soft);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .seg {
    display: flex;
    gap: 3px;
    padding: 3px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-field);
  }

  .seg button {
    flex: 1;
    min-height: 38px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-soft);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  /* On a touch screen or a phone, everything here is at least 44 × 44 px to tap. */
  @media (pointer: coarse), (max-width: 767px) {
    .swatch {
      width: var(--touch-target);
      height: var(--touch-target);
      margin: 0;
    }

    .seg button {
      min-height: var(--touch-target);
    }
  }

  .seg button[aria-pressed='true'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    line-height: 1.4;
  }

  .username {
    font-size: var(--text-lg);
  }

  .switch-row {
    display: flex;
    align-items: center;
    gap: var(--space-6);
  }

  .words {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-1);
  }

  .label {
    font-size: 1rem;
    font-weight: var(--weight-semibold);
  }

  .ok {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-6) 14px;
    border-radius: var(--radius-lg);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .mono {
    font-family: ui-monospace, Menlo, Consolas, monospace;
    overflow-wrap: anywhere;
    user-select: all;
  }

  .primary,
  .quiet {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 48px;
    padding: 0 18px;
    border-radius: var(--radius-lg);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .sm {
    min-height: var(--touch-target);
    padding: 0 14px;
    font-size: var(--text-md);
  }

  .primary {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .quiet {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .danger {
    margin-top: var(--space-4);
    border-color: var(--color-warning-border);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  button:disabled {
    cursor: default;
    opacity: 0.6;
  }

  .note {
    padding: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
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
