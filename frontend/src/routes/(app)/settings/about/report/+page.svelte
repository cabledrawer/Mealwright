<script lang="ts">
  // Settings › About › Report a problem (mockup Dark-Report09-Phone; spec section 7 "Bug
  // reports", cabledrawer 17 Oct; plan row X2).
  //
  // 1. The server builds the report (version, browser and device, recent errors for an admin)
  //    with personal details already removed. 2. All of it is shown here; every line can be
  //    changed or removed (cabledrawer 12 Nov: each line with its own ✕, as drawn), and
  //    "What were you doing?" is typed here. 3. The person sends it: Open on GitHub (a link to a
  //    filled-in new-issue page, their own click), Copy, or Download (a text file made here).
  //    The server makes no connection for any of it.
  import { onDestroy, onMount, tick } from 'svelte';
  import Icon from '#lib/components/Icon.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { getProblemReport, type ProblemReport } from '#lib/client/problemReport.js';
  import {
    COPIED,
    COPY,
    COPY_FAILED,
    DOING,
    DOWNLOAD,
    GITHUB_HINT,
    INTRO,
    IN_REPORT,
    LINE_REMOVED,
    MEMBER_NOTE,
    NO_LINES,
    OPEN_ON_GITHUB,
    REMOVED_NOTE,
    REMOVE_LINE,
    TITLE,
    TRIMMED_NOTE,
    fileName,
    issueLink,
    issueTitle,
    lineLabel,
    reportText,
    startingLines
  } from '#lib/problemReport.js';
  import { CopyFeedback } from '#lib/copyFeedback.svelte.js';
  import { autosize } from '#lib/recipes/autosize.js';
  import { toasts } from '#lib/toast.svelte.js';

  interface Line {
    id: number;
    text: string;
  }

  let report = $state<ProblemReport | null>(null);
  let problem = $state<string | null>(null);
  let loading = $state(false);
  let doing = $state('');
  let lines = $state<Line[]>([]);
  let nextId = 0;

  async function load() {
    loading = true;
    try {
      const answer = await getProblemReport();
      report = answer;
      lines = startingLines(answer).map((text) => ({ id: nextId++, text }));
      problem = null;
    } catch (error) {
      problem = error instanceof ApiError && !cantReach(error) ? error.detail : cantReachWords();
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    void load();
  });

  const text = $derived(
    reportText(
      doing,
      lines.map((line) => line.text)
    )
  );
  const link = $derived(report ? issueLink(report.new_issue_page, issueTitle(doing), text) : null);

  let listEl = $state<HTMLElement | null>(null);

  async function remove(index: number) {
    const [gone] = lines.splice(index, 1);
    if (!gone) return;
    // Keep the keyboard near: the next line's ✕, or the one before, or the box.
    await tick();
    const buttons = listEl?.querySelectorAll<HTMLButtonElement>('button.remove');
    const next = buttons?.[Math.min(index, (buttons?.length ?? 1) - 1)];
    next?.focus();
    toasts.show(LINE_REMOVED, {
      action: {
        label: 'Undo',
        run: () => {
          lines.splice(Math.min(index, lines.length), 0, gone);
          toasts.show(`Undone: ${LINE_REMOVED}`);
        }
      }
    });
  }

  const copier = new CopyFeedback();
  onDestroy(() => copier.dispose());

  async function copy() {
    if (await copier.copy(text)) {
      toasts.show(COPIED);
    } else {
      toasts.show(COPY_FAILED, { tone: 'problem' });
    }
  }

  function download() {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName();
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
</script>

<PageHeader title={TITLE} parent={{ href: '/(app)/settings/about', label: 'About' }} />

<div class="page">
  <p class="intro">{INTRO}</p>

  {#if problem && !report}
    <p class="problem" role="alert">
      {problem}
      <button type="button" class="link" onclick={() => void load()}>Try again</button>
    </p>
  {/if}

  <label class="fld">
    {DOING}
    <textarea bind:value={doing} use:autosize={doing} rows="3"></textarea>
  </label>

  {#if report}
    <section class="section" aria-labelledby="in-report">
      <h2 class="title" id="in-report">{IN_REPORT}</h2>
      {#if lines.length}
        <ul class="card" bind:this={listEl}>
          {#each lines as line, index (line.id)}
            <li class="row">
              <textarea
                class="line"
                rows="1"
                aria-label={lineLabel(index + 1)}
                bind:value={line.text}
                use:autosize={line.text}></textarea>
              <button
                type="button"
                class="remove"
                aria-label={REMOVE_LINE}
                onclick={() => void remove(index)}>✕</button
              >
            </li>
          {/each}
        </ul>
      {:else}
        <p class="quiet">{NO_LINES}</p>
      {/if}
      {#if !report.errors_included}<p class="quiet">{MEMBER_NOTE}</p>{/if}
    </section>

    <p class="ok">
      <Icon name="shield" size={18} />
      <span>{REMOVED_NOTE}</span>
    </p>

    {#if link}
      <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- another site: the person's own click -->
      <a class="btn" href={link.href} target="_blank" rel="noopener noreferrer">{OPEN_ON_GITHUB}</a>
      <span class="hint">{GITHUB_HINT}</span>
      {#if link.trimmed}<p class="quiet trimmed">{TRIMMED_NOTE}</p>{/if}
    {/if}
    <div class="pair">
      <button type="button" class="btn2" onclick={() => void copy()}>{copier.label(COPY)}</button>
      <button type="button" class="btn2" onclick={download}>{DOWNLOAD}</button>
    </div>
  {:else if loading}
    <p class="quiet" role="status">Loading…</p>
  {/if}
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    max-width: 640px;
  }

  .intro {
    margin: 0 var(--space-2) var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .fld {
    display: flex;
    flex-direction: column;
    gap: 6px;
    color: var(--color-label);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .fld textarea {
    box-sizing: border-box;
    width: 100%;
    min-height: 84px;
    padding: 10px var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-size: 1rem; /* 16px, not the mockup's 15: smaller fields make iOS zoom in */
    font-weight: var(--weight-medium);
    resize: none;
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
    margin: 0;
    padding: 0;
    overflow: hidden;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    list-style: none;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 46px;
    padding: var(--space-3) 14px;
    border-top: 1px solid var(--color-divider);
  }

  .row:first-child {
    border-top: none;
  }

  /* A report line: reads as plain text, and is a text box to change it. */
  .line {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    box-sizing: border-box;
    padding: var(--space-2) var(--space-3);
    border: 1px solid transparent;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-text-soft);
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: 1rem; /* 16px, not the mockup's 13: smaller fields make iOS zoom in */
    line-height: 1.4;
    overflow-wrap: anywhere;
    resize: none;
  }

  .line:hover,
  .line:focus {
    border-color: var(--color-field-border);
    background: var(--color-field);
  }

  /* A 44 px target around the mockup's 32 px outlined ✕. */
  .remove {
    position: relative;
    display: inline-flex;
    flex: none;
    align-items: center;
    justify-content: center;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .remove::before {
    position: absolute;
    width: 32px;
    height: 32px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-md);
    content: '';
  }

  .quiet {
    margin: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .ok {
    display: flex;
    gap: var(--space-4);
    margin: 0;
    padding: var(--space-5) 14px;
    border: 1px solid var(--color-note-border);
    border-radius: var(--radius-xl);
    background: var(--color-note);
    color: var(--color-note-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .ok :global(svg) {
    flex: none;
  }

  .btn,
  .btn2 {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 48px;
    padding: 0 18px;
    border-radius: var(--radius-button);
    font-size: 0.9375rem;
    font-weight: var(--weight-bold);
    text-decoration: none;
    cursor: pointer;
  }

  .btn {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .btn2 {
    flex: 1;
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
    text-align: center;
  }

  .trimmed {
    text-align: center;
  }

  .pair {
    display: flex;
    gap: 10px;
  }

  .problem {
    margin: 0;
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
