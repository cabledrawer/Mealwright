<script lang="ts">
  // "Import a recipe", step 1 (mockups Import05-Phone and Import05-Desktop and their dark
  // versions, spec section 6 "One box"): one box that takes a link or pasted recipe text, and
  // Mealwright works out which. A link needs "Recipe import from links" to be on; pasted text
  // never goes online. Online only: offline, the box says it needs the server and nothing is
  // queued. Under "How it works", a note says photos aren't downloaded while that switch is
  // off (`photosOff`: true only when the server has said so, never on a guess). `linksOff` is the same
  // for the links switch: the link chip says it is off instead of "your server visits this page".
  import { resolve } from '$app/paths';
  import { tick } from 'svelte';
  import Button from '#lib/components/Button.svelte';
  import Icon from '#lib/components/Icon.svelte';
  import { network } from '#lib/network.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import { OUTSIDE_CONNECTIONS_ANCHOR } from '#lib/privacyWords.js';
  import {
    canPaste,
    GONE_FROM_DRAFTS,
    IN_DRAFTS,
    importLinks,
    LINKS_HELP,
    LINKS_SERVER_NOTE,
    leftOutWords,
    noneReadWords,
    pasteLimitWords,
    linksHeading,
    READING,
    QUICK_HELP,
    ALL_MATCHED,
    NEEDS_CHECKING,
    SAVED,
    saveReadyWords,
    TRY_AGAIN,
    WAITING
  } from '#lib/importLinks.svelte.js';
  import { offlineNote, PASTE_INSTEAD_STEPS, type ImportFlow } from '#lib/import.svelte.js';

  import '#lib/styles/fields.css';
  let {
    flow,
    photosOff = false,
    linksOff = false
  }: { flow: ImportFlow; photosOff?: boolean; linksOff?: boolean } = $props();

  const uid = $props.id();
  let box = $state<HTMLTextAreaElement>();
  const several = $derived(flow.linkCount > 1);
  const reading = $derived(flow.phase === 'reading' || importLinks.running);
  const typed = $derived(flow.text.trim() !== '');
  const kind = $derived(!typed ? null : flow.isLink ? 'link' : 'text');

  const refused = $derived(flow.problem?.code === 'site_refused');
  // A refused site clears the link: the cursor goes to the empty box, ready for pasting (F115).
  $effect(() => {
    if (refused) void tick().then(() => box?.focus());
  });

  let resultsHeading = $state<HTMLElement>();

  /** Save ready recipes: the button goes when it is done, so the cursor goes to the results. */
  async function saveReady() {
    await importLinks.saveReady();
    await tick();
    resultsHeading?.focus();
  }

  /** "Paste text instead": empty the box of the link and put the cursor back in it. */
  async function pasteInstead() {
    flow.text = '';
    flow.problem = null;
    await tick();
    box?.focus();
  }
</script>

<form
  class="start"
  onsubmit={(e) => {
    e.preventDefault();
    if (several) void importLinks.run(flow.links);
    else void flow.read();
  }}
>
  <div class="card">
    <label class="mw-label big" for="{uid}-box">Paste a link or the recipe’s text</label>
    <textarea
      id="{uid}-box"
      bind:this={box}
      class="mw-input box"
      rows="6"
      placeholder="https://… or the title, ingredients and method"
      aria-describedby="{uid}-limit {uid}-kind"
      aria-invalid={flow.problem && !flow.problem.switchedOff && !refused ? true : undefined}
      readonly={reading}
      bind:value={flow.text}></textarea>

    <p class="limit" id="{uid}-limit">{pasteLimitWords()}</p>

    <p class="kind" id="{uid}-kind" aria-live="polite">
      {#if kind === 'link' && linksOff}
        <!-- F239: the green "your server visits this page" is true only while the switch is on. -->
        <span class="chip"
          ><Icon name="link" size={18} stroke={2.2} />Importing from links is switched off</span
        >
      {:else if kind === 'link'}
        <span class="chip good"
          ><Icon name="link" size={18} stroke={2.2} />{#if several}{linksHeading(
              flow.linkCount
            )}{:else}A link · your server visits this page once{/if}</span
        >
      {:else if kind === 'text'}
        <span class="chip"
          ><Icon name="note" size={18} stroke={2.2} />Pasted text · nothing goes online</span
        >
      {/if}
    </p>

    {#if network.offline}
      <p class="offline" role="status">{offlineNote()}</p>
    {/if}

    {#if flow.problem}
      {#if flow.problem.switchedOff}
        <div class="alert" role="alert">
          <p class="title">Importing from links is switched off</p>
          <p>
            Nothing was fetched.
            {#if flow.problem.admin}Switch it on in Settings › Outside connections, or paste the
              recipe’s text instead; pasted text never goes online.{:else}An admin can switch it on
              in Settings › Outside connections. You can paste the recipe’s text instead; pasted
              text never goes online.{/if}
          </p>
          <p class="actions">
            {#if flow.problem.admin}
              <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- Settings › Outside connections is built beside this page -->
              <a class="button" href="/settings/privacy#{OUTSIDE_CONNECTIONS_ANCHOR}"
                >Open Settings</a
              >
            {/if}
            <Button quiet small onclick={() => void pasteInstead()}>Paste text instead</Button>
          </p>
        </div>
      {:else}
        <div class="alert plain" role="alert">
          <p class="title">{flow.problem.message}</p>
          {#if refused}
            <ol class="how-to" aria-label="How to paste the recipe instead">
              {#each PASTE_INSTEAD_STEPS as step (step)}<li>{step}</li>{/each}
            </ol>
          {/if}
          {#if flow.problem.code === 'import_switched_off' || /^(bad_link|not_a_page|no_recipe|cant_read)$/.test(flow.problem.code)}
            <p class="actions">
              <Button quiet small onclick={() => void pasteInstead()}>Paste text instead</Button>
            </p>
          {/if}
        </div>
      {/if}
    {/if}

    <Button type="submit" disabled={reading || !typed || network.offline}>
      {reading ? 'Reading…' : several ? 'Read the recipes' : 'Read the recipe'}
    </Button>
    <p class="visually-hidden" role="status">{reading ? 'Reading the recipe' : ''}</p>
  </div>

  {#if importLinks.rows.length > 0}
    <section class="results" aria-label="Links being read">
      <h2 class="overline" tabindex="-1" bind:this={resultsHeading}>
        {linksHeading(importLinks.rows.length)}
      </h2>
      <ul class="rows" aria-live="polite">
        {#each importLinks.rows as row (row.link)}
          <li class="row" data-state={row.state}>
            <span class="what">
              <b>{row.title}</b>
              <span class="site">{row.site}{row.state === 'ready' ? ` · ${IN_DRAFTS}` : ''}</span>
              {#if row.message}<span class="why">{row.message}</span>{/if}
            </span>
            {#if row.state === 'ready' && row.savedId !== null}
              <!-- Saved by quick import (F216): its recipe, until that is undone. -->
              <span class="status ok">{SAVED}</span>
              <a
                class="ghost small check"
                href={resolve('/(app)/recipes/[id]', { id: String(row.savedId) })}
                aria-label="Open {row.title}">Open</a
              >
            {:else if row.state === 'ready' && importLinks.gone(row)}
              <!-- Saved or discarded elsewhere: nothing to open. -->
              <span class="status">{GONE_FROM_DRAFTS}</span>
            {:else if row.state === 'ready'}
              <span class="status" class:ok={row.allMatched}
                >{row.allMatched ? ALL_MATCHED : NEEDS_CHECKING}</span
              >
              {#if row.draftId !== null}
                <!-- F209 (cabledrawer 10 Nov): each result opens its draft's Check straight away. -->
                <a
                  class="ghost small check"
                  href={resolve('/(app)/recipes/drafts/[id]', { id: String(row.draftId) })}
                  aria-label="Check {row.title}">Check</a
                >
              {/if}
            {:else if row.state === 'reading'}
              <span class="status busy">{READING}</span>
            {:else if row.state === 'waiting'}
              <span class="status">{WAITING}</span>
            {:else if canPaste(row)}
              <Button quiet small onclick={() => void pasteInstead()}>Paste text</Button>
            {:else if row.state === 'failed' && row.code !== 'already_imported'}
              <!-- RF4 I3: this one link is read again; the others are left as they are. -->
              <Button
                quiet
                small
                disabled={reading}
                aria-label="{TRY_AGAIN}: {row.title}"
                onclick={() => void importLinks.retry(row)}>{TRY_AGAIN}</Button
              >
            {/if}
          </li>
        {/each}
      </ul>
      {#if importLinks.ready.length > 0 && !importLinks.running}
        <!-- Quick import (F216, cabledrawer 10 Nov): the drafts whose ingredients all matched, saved
             in one go; the rest stay in Drafts for checking. -->
        <p class="actions">
          <Button small disabled={importLinks.saving} onclick={() => void saveReady()}
            >{importLinks.saving ? 'Saving…' : saveReadyWords(importLinks.ready.length)}</Button
          >
        </p>
        <p class="help">{QUICK_HELP}</p>
      {/if}
      {#if importLinks.leftOut > 0}
        <p class="help" role="status">{leftOutWords(importLinks.leftOut, importLinks.room)}</p>
      {/if}
      <p class="help">{LINKS_HELP}</p>
      <p class="server">{LINKS_SERVER_NOTE}</p>
      <p class="actions">
        <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- Drafts is built beside this page -->
        <a class="button" href="/recipes/drafts">Go to Drafts</a>
      </p>
    </section>
  {/if}

  {#if importLinks.rows.length === 0 && importLinks.leftOut > 0}
    <p class="help" role="status">{noneReadWords(importLinks.leftOut)}</p>
  {/if}

  <aside class="how" aria-label="How it works">
    <p class="overline">How it works</p>
    <p>
      <b>A link:</b> your Mealwright server reads the page and shows you what it found. Nothing is saved
      until you choose.
    </p>
    <p>
      <b>Pasted text:</b> the title, ingredients and method, copied from anywhere. Nothing goes online.
    </p>
  </aside>

  {#if photosOff}
    <p class="photos">
      Recipe photos: not downloaded.
      {#if session.me?.role === 'admin'}
        <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- Settings › Outside connections is built beside this page -->
        <a href="/settings/privacy#{OUTSIDE_CONNECTIONS_ANCHOR}"
          >Change in Settings › Outside connections</a
        >
      {:else}
        An admin can switch them on in Settings › Outside connections.
      {/if}
    </p>
  {/if}
</form>

<style>
  .start {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 760px;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-7);
    border-radius: var(--radius-3xl);
    background: var(--color-surface);
  }

  .big {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
    color: var(--color-text);
  }

  .box {
    min-height: 8.5rem;
    resize: vertical;
    padding: var(--space-6);
    border: 2px solid var(--color-accent);
    border-radius: var(--radius-xl);
    font-size: 1rem;
    line-height: 1.45;
  }

  .kind {
    min-height: 0;
  }

  .limit {
    margin: 0;
    font-size: var(--text-sm);
    color: var(--color-text-muted);
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-chip);
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .chip.good {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .offline {
    padding: var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-md);
  }

  .alert {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6);
    border: 1px solid var(--color-warning-border);
    border-radius: var(--radius-xl);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .alert .title {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .alert.plain {
    border-color: var(--color-danger);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .how-to {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding-left: var(--space-8);
    font-size: var(--text-md);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .button,
  .ghost {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border-radius: var(--radius-lg);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
    cursor: pointer;
  }

  .button {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .ghost {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .how {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .results {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .rows {
    margin: 0;
    padding: 0 var(--space-6);
    list-style: none;
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    min-height: 56px;
    padding: var(--space-4) 0;
    border-bottom: 1px solid var(--color-border);
  }

  .row:last-child {
    border-bottom: none;
  }

  .what {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .site,
  .help,
  .server {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .why {
    color: var(--color-warning-text);
    font-size: var(--text-sm);
  }

  .status {
    flex: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .status.ok {
    color: var(--color-accent);
  }

  .status.busy {
    color: var(--color-warning-text);
  }

  .small {
    flex: none;
  }

  a.check {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    color: var(--color-text);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .photos {
    padding: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .photos a {
    color: var(--color-accent);
    font-weight: var(--weight-bold);
  }

  .overline {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }
</style>
