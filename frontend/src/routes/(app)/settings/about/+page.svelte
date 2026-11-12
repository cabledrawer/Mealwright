<script lang="ts">
  // Settings → About (mockup Dark-About09-Phone). This PR (X1, "Update check") builds only the
  // update parts: "New version ready", the version and its release day, the version-age note
  // and the admins' Updates card. X2 adds Help's "Report a problem". U1 adds "Licences and
  // credits": the licence, a plain link to the source, the USDA credit and the fonts' licences.
  // Nothing is requested for them: the link is the person's own click.
  //
  // Spec section 7 "Updates" (cabledrawer 17 Oct): (1) how old this version is, with no connection;
  // (2) Check now, admins only, one plain request to the public release list, made by the
  // server through its outbound gate; (3) the daily check, its own Privacy switch, off at first.
  // Check now works whatever that switch says: it only controls the daily check (cabledrawer 12 Nov).
  import { onMount } from 'svelte';
  import { resolve } from '$app/paths';
  import Icon from '#lib/components/Icon.svelte';
  import Logo from '#lib/components/Logo.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import {
    CHECK_NOW,
    CHECK_NOW_DETAIL,
    CHECKING,
    DAILY,
    DATA_DETAIL,
    DATA_LABEL,
    FONTS_DETAIL,
    FONTS_LABEL,
    LICENCE_LABEL,
    LICENCE_VALUE,
    LICENCES_HEADING,
    READY_TEXT,
    READY_TITLE,
    UPDATE_TAG,
    UPDATES_HEADING,
    ageWords,
    dailyWords,
    lastWords,
    releasedWords,
    shortLink,
    SOURCE_DETAIL,
    SOURCE_LABEL,
    sourceLink,
    todayHere,
    versionHeading
  } from '#lib/aboutWords.js';
  import { network } from '#lib/network.svelte.js';
  import { newVersion } from '#lib/newVersion.svelte.js';
  import { updates } from '#lib/updates.svelte.js';
  import { VERSION } from '#lib/version.js';
  import { OUTSIDE_CONNECTIONS_ANCHOR } from '#lib/privacyWords.js';
  import { HELP_HEADING, TITLE as REPORT_A_PROBLEM } from '#lib/problemReport.js';

  onMount(() => {
    void newVersion.watch();
    void updates.load();
  });

  const info = $derived(updates.info);
  const age = $derived(info ? ageWords(info.released, todayHere()) : null);
  const last = $derived(info?.last ? lastWords(info.last) : null);
  const daily = $derived(dailyWords(info?.daily === true));
  const privacyHref = `/settings/privacy#${OUTSIDE_CONNECTIONS_ANCHOR}`;
</script>

<PageHeader title="About" parent={{ href: '/(app)/settings', label: 'Settings' }} />

<div class="page">
  {#if newVersion.ready}
    <p class="ready" role="status">
      <Icon name="info" size={18} />
      <span><strong>{READY_TITLE}</strong> {READY_TEXT}</span>
    </p>
  {/if}

  <div class="version">
    <Logo size={56} />
    <div class="words">
      <span class="name">{versionHeading(info?.version ?? VERSION)}</span>
      {#if info}<span class="sub">{releasedWords(info.released)}</span>{/if}
    </div>
  </div>

  {#if info && age}
    <p class="old">
      <Icon name="info" size={18} />
      <span
        >{age} New versions are listed at
        <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- another site: the person's own click -->
        <a href={info.releases_page} target="_blank" rel="noopener noreferrer"
          >{shortLink(info.releases_page)}</a
        >.</span
      >
    </p>
  {/if}

  {#if !info && updates.problem}
    <p class="problem" role="alert">
      {updates.problem}
      <button type="button" class="link" onclick={() => void updates.load()}>Try again</button>
    </p>
  {/if}

  {#if info?.can_check}
    <section class="section" aria-labelledby="updates">
      <h2 class="title" id="updates">{UPDATES_HEADING}</h2>
      <div class="card">
        {#if last}
          <!-- eslint-disable svelte/no-navigation-without-resolve -- the releases page is another site (the person's own click); Privacy's link carries its #outside-connections anchor -->
          {#if last.outcome === 'newer'}
            <a
              href={info.releases_page}
              class="row"
              target="_blank"
              rel="noopener noreferrer"
              data-outcome={last.outcome}
            >
              <span class="lbl">{last.title}<small>{last.detail}</small></span>
              <span class="tag">{UPDATE_TAG}</span>
              <span class="chev"><Icon name="back" size={18} stroke={2} /></span>
            </a>
          {:else}
            <div class="row" data-outcome={last.outcome}>
              <span class="lbl">{last.title}<small>{last.detail}</small></span>
            </div>
          {/if}
        {/if}
        <div class="row">
          <span class="lbl">{CHECK_NOW}<small>{CHECK_NOW_DETAIL}</small></span>
          <button
            type="button"
            class="check"
            disabled={updates.checking || network.offline}
            onclick={() => void updates.check()}>{updates.checking ? CHECKING : CHECK_NOW}</button
          >
        </div>
        {#if updates.checkProblem}
          <p class="row-problem" role="alert">{updates.checkProblem}</p>
        {/if}
        <a class="row" href={privacyHref}>
          <span class="lbl">{DAILY}<small>{daily.detail}</small></span>
          <span class="val">{daily.value}</span>
          <span class="chev"><Icon name="back" size={18} stroke={2} /></span>
        </a>
        <!-- eslint-enable svelte/no-navigation-without-resolve -->
      </div>
      <p class="live" role="status">
        {#if updates.checking}{CHECKING}{:else if last}{last.title}{/if}
      </p>
    </section>
  {/if}

  <!-- Help (mockup Dark-About09-Phone): Report a problem, for everyone (X2). -->
  <section class="section" aria-labelledby="help">
    <h2 class="title" id="help">{HELP_HEADING}</h2>
    <div class="card">
      <a class="row" href={resolve('/(app)/settings/about/report')}>
        <span class="lbl">{REPORT_A_PROBLEM}</span>
        <span class="chev"><Icon name="back" size={18} stroke={2} /></span>
      </a>
    </div>
  </section>

  <section class="section" aria-labelledby="licences">
    <h2 class="title" id="licences">{LICENCES_HEADING}</h2>
    <div class="card">
      <div class="row">
        <span class="lbl">{LICENCE_LABEL}</span>
        <span class="val">{LICENCE_VALUE}</span>
      </div>
      {#if info}
        <!-- eslint-disable svelte/no-navigation-without-resolve -- the source is another site: the person's own click, no request from the app -->
        <a
          class="row"
          href={sourceLink(info.releases_page)}
          target="_blank"
          rel="noopener noreferrer"
        >
          <!-- eslint-enable svelte/no-navigation-without-resolve -->
          <span class="lbl">{SOURCE_LABEL}<small>{SOURCE_DETAIL}</small></span>
          <span class="chev"><Icon name="back" size={18} stroke={2} /></span>
        </a>
      {:else}
        <div class="row">
          <span class="lbl">{SOURCE_LABEL}<small>{SOURCE_DETAIL}</small></span>
        </div>
      {/if}
      <div class="row">
        <span class="lbl">{DATA_LABEL}<small>{DATA_DETAIL}</small></span>
      </div>
      <div class="row">
        <span class="lbl">{FONTS_LABEL}<small>{FONTS_DETAIL}</small></span>
      </div>
    </div>
  </section>
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 640px;
  }

  .ready,
  .old {
    display: flex;
    gap: var(--space-4);
    padding: var(--space-5) 14px;
    border: 1px solid;
    border-radius: var(--radius-xl);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .ready :global(svg),
  .old :global(svg) {
    flex: none;
  }

  .ready {
    border-color: var(--color-note-border);
    background: var(--color-note);
    color: var(--color-note-text);
  }

  .old {
    border-color: var(--color-caution-border);
    background: var(--color-caution);
    color: var(--color-caution-text);
  }

  .old a {
    color: inherit;
    font-weight: var(--weight-bold);
    text-decoration: underline;
    overflow-wrap: anywhere;
  }

  .version {
    display: flex;
    align-items: center;
    gap: 14px;
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }

  .name {
    font-size: 1.375rem; /* 22px, as the mockup */
    font-weight: var(--weight-extrabold);
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin-top: var(--space-3);
  }

  .title {
    margin: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .card {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 56px;
    padding: var(--space-5) 14px;
    border-top: 1px solid var(--color-divider);
    color: var(--color-text);
    text-decoration: none;
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
    white-space: nowrap;
  }

  .tag {
    padding: 2px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.02em;
  }

  .chev {
    display: inline-flex;
    flex: none;
    color: var(--color-text-muted);
    transform: scaleX(-1);
  }

  .check {
    flex: none;
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .check:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .row-problem,
  .problem {
    padding: var(--space-5) 14px;
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.45;
  }

  .problem {
    border-radius: var(--radius-field);
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

  /* Said to a screen reader when a check starts and ends; the card shows the same. */
  .live {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }
</style>
