<script lang="ts">
  // Drafts (mockups Drafts05-Phone and Drafts05-Desktop, spec "Drafts (cabledrawer 21 Oct)"): the
  // imports your household hasn't finished, kept for 15 days. Each says where it came from, who
  // started it, how many days it has left and how far the checking has got, with visible
  // buttons: Carry on (or Save recipe, when every ingredient is checked) and Delete. Delete
  // hides the draft at once and a toast offers Undo (and Ctrl+Z does the same). On a phone each
  // card also swipes (cabledrawer 21 Oct): right = Carry on, left = Delete (with the same Undo toast,
  // no asking); each is shown as a button first, and the card's own buttons do the same. A phone
  // has cards, a computer a table (no swipes).
  // Online only: drafts are kept on the server.
  // 0.9.5 (Import from Mealie, cabledrawer 13 Nov): when some drafts came from Mealie, chips show
  // All or From Mealie; From Mealie says the lines each still waits on, and "Save all N as they
  // are" saves them all (unread lines kept as plain text, nothing on the shopping list).
  import { offlineNote } from '#lib/privacyWords.js';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { onMount } from 'svelte';
  import type { DraftBrief } from '#lib/client/drafts.js';
  import { saveAllMealieDrafts } from '#lib/client/mealie.js';
  import { ApiError, cantReach, cantReachWords } from '#lib/api.js';
  import { DRAFTS_LEAD, linesWords, saveAllWords, unreadWords } from '#lib/mealieWords.js';
  import {
    RUNNING_OUT,
    allChecked,
    daysWords,
    fromWords,
    needYou,
    phoneSource,
    progressShare,
    progressWords,
    shortProgress
  } from '#lib/draftWords.js';
  import { drafts } from '#lib/drafts.svelte.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { nextDraft } from '#lib/nextDraft.svelte.js';
  import { saveFromDraft } from '#lib/import.draftSave.js';
  import { initial, session } from '#lib/session.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import type { Side } from '#lib/swipe.js';
  import EmptyState from '../EmptyState.svelte';
  import FilterChips from '../FilterChips.svelte';
  import OfflineNote from '../OfflineNote.svelte';
  import PageHeader from '../PageHeader.svelte';
  import SwipeRow from '../SwipeRow.svelte';

  let { fromMealie = false }: { fromMealie?: boolean } = $props();

  let phone = $state(matchMedia('(max-width: 767px)').matches);
  $effect(() => {
    const media = matchMedia('(max-width: 767px)');
    const onchange = () => (phone = media.matches);
    media.addEventListener('change', onchange);
    return () => media.removeEventListener('change', onchange);
  });

  onMount(() => {
    if (!network.offline) void drafts.load();
  });
  let seen = network.backAgain;
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      void drafts.load();
    }
  });
  // An Undo done from the keyboard after a reload (Ctrl+Z finds the delete on the server) says
  // something changed: the list is fetched again.
  let changes = kitchen.version;
  $effect(() => {
    const now = kitchen.version;
    if (now !== changes) {
      changes = now;
      void drafts.load();
    }
  });

  /** The draft being saved from its row, and what went wrong on a row. */
  let saving = $state<number | null>(null);
  let problems = $state<Record<number, string>>({});

  async function saveNow(draft: DraftBrief) {
    if (saving !== null) return;
    saving = draft.id;
    delete problems[draft.id];
    const done = await saveFromDraft(draft.id);
    saving = null;
    if ('problem' in done) {
      problems[draft.id] = done.problem;
      return;
    }
    void drafts.load();
    nextDraft.mark(done.recipeId, draft.id);
    await goto(resolve('/(app)/recipes/[id]', { id: String(done.recipeId) }));
  }

  /** All drafts, only those from Mealie, or only those from a link (the chips show only when
   *  some came from Mealie; Links only when some came from a link: mockup
   *  Dark-MealieCheck095-Phone). A draft from pasted text is under All. */
  // svelte-ignore state_referenced_locally
  let only = $state<'all' | 'mealie' | 'link'>(fromMealie ? 'mealie' : 'all');
  const mealie = $derived(drafts.drafts.filter((draft) => draft.source.kind === 'mealie'));
  const links = $derived(drafts.drafts.filter((draft) => draft.source.kind === 'link'));
  const showing = $derived(
    only === 'mealie' && mealie.length ? 'mealie' : only === 'link' && links.length ? 'link' : 'all'
  );
  const listed = $derived(
    showing === 'mealie' ? mealie : showing === 'link' ? links : drafts.drafts
  );
  const mealieLine = (draft: DraftBrief) =>
    unreadWords(draft.waiting ?? [], needYou(draft), !phone);

  let savingAll = $state(false);
  let saveAllProblem = $state<string | null>(null);

  async function saveAll() {
    if (savingAll) return;
    savingAll = true;
    saveAllProblem = null;
    try {
      await saveAllMealieDrafts();
      only = 'all';
    } catch (error) {
      saveAllProblem =
        error instanceof ApiError && !cantReach(error) ? error.detail : cantReachWords();
    } finally {
      savingAll = false;
    }
    void drafts.load();
  }

  /** Which cards are swiped open, and to which side. */
  let swiped = $state<Record<number, Side>>({});

  const here = (draft: DraftBrief) =>
    resolve('/(app)/recipes/drafts/[id]', { id: String(draft.id) });
  const subtitle = $derived(
    phone
      ? 'Imports your household hasn’t finished · kept for 15 days'
      : 'Imports your household hasn’t finished · kept for 15 days, then deleted quietly'
  );
</script>

<PageHeader title="Drafts" parent={{ href: '/(app)/recipes', label: 'Recipes' }} {subtitle}>
  {#snippet actions()}
    {#if !phone}<a class="import" href={resolve('/(app)/recipes/import')}>Import a recipe</a>{/if}
  {/snippet}
</PageHeader>

{#snippet buttons(draft: DraftBrief)}
  {#if allChecked(draft)}
    <button
      type="button"
      class="save"
      disabled={saving !== null || network.offline}
      onclick={() => void saveNow(draft)}
      aria-label="Save recipe {draft.name}"
    >
      {saving === draft.id ? 'Saving…' : 'Save recipe'}
    </button>
  {/if}
  <a class="carry" href={here(draft)} aria-label="Carry on {draft.name}">Carry on</a>
  <button
    type="button"
    class="delete"
    aria-label="Delete {draft.name}"
    disabled={network.offline}
    onclick={() => void drafts.remove(draft)}>Delete</button
  >
{/snippet}

{#if network.down && !drafts.loaded}
  <OfflineNote screen="Drafts" />
{:else if drafts.problem && !drafts.loaded}
  <div class="failed" role="alert">
    <p>{drafts.problem}</p>
    <button type="button" class="again" onclick={() => void drafts.load()}>Try again</button>
  </div>
{:else if !drafts.loaded}
  <p class="loading" aria-busy="true">Loading…</p>
{:else}
  {#if network.offline}
    <p class="stale" role="status">
      {offlineNote(network.deviceOffline)}
    </p>
  {/if}
  {#if drafts.deleteProblem}
    <p class="failed-line" role="alert">{drafts.deleteProblem}</p>
  {/if}
  {#if mealie.length}
    <FilterChips
      label="Show"
      options={[
        { value: 'all', label: `All ${drafts.drafts.length}` },
        { value: 'mealie', label: `From Mealie ${mealie.length}` },
        ...(links.length ? [{ value: 'link' as const, label: `Links ${links.length}` }] : [])
      ]}
      selected={showing}
      onselect={(value) => (only = value)}
    />
  {/if}
  {#if showing === 'mealie'}
    <div class="mealie">
      <p class="lead">{DRAFTS_LEAD}</p>
      {#if session.me?.role === 'admin'}
        <button
          type="button"
          class="save-all"
          disabled={savingAll || network.offline}
          onclick={() => void saveAll()}
          >{savingAll ? 'Saving…' : saveAllWords(mealie.length)}</button
        >
      {/if}
      {#if saveAllProblem}<p class="failed-line" role="alert">{saveAllProblem}</p>{/if}
    </div>
  {/if}
  {#if drafts.drafts.length === 0}
    <EmptyState title="No drafts">
      When you import a recipe and leave before saving it, it waits here for 15 days.
    </EmptyState>
  {:else if phone}
    <ul class="cards" aria-label="Drafts">
      {#each listed as draft (draft.id)}
        <li>
          <SwipeRow
            bind:open={() => swiped[draft.id] ?? null, (side) => (swiped[draft.id] = side)}
            right={{
              label: 'Carry on',
              describe: draft.name,
              icon: 'arrow-right',
              tone: 'move',
              run: () => void goto(here(draft))
            }}
            left={network.offline
              ? undefined
              : {
                  label: 'Delete',
                  describe: draft.name,
                  icon: 'trash',
                  tone: 'danger',
                  run: () => void drafts.remove(draft)
                }}
          >
            <article class="card" class:ready={allChecked(draft)}>
              <div class="head">
                <span class="what">
                  <span class="name">{draft.name}</span>
                  {#if draft.source.kind === 'mealie' && draft.waiting?.length}
                    <span class="source">{mealieLine(draft)}</span>
                  {:else}
                    <span class="source">{phoneSource(draft)}</span>
                  {/if}
                </span>
                <span class="left" class:running-out={draft.days_left <= RUNNING_OUT}
                  >{daysWords(draft.days_left)}</span
                >
              </div>
              <div class="progress">
                <div class="bar" aria-hidden="true">
                  <div class="fill" style:width="{progressShare(draft)}%"></div>
                </div>
                <span class="words" class:done={allChecked(draft)}>{progressWords(draft)}</span>
              </div>
              <div class="buttons" class:three={allChecked(draft)}>{@render buttons(draft)}</div>
              {#if problems[draft.id]}<p class="failed-line" role="alert">
                  {problems[draft.id]}
                </p>{/if}
            </article>
          </SwipeRow>
        </li>
      {/each}
    </ul>
    <p class="foot">
      Nothing here is in your recipes yet. Drafts are deleted quietly after 15 days.
    </p>
  {:else}
    <table class="table">
      <caption class="sr">Drafts</caption>
      <thead>
        <tr>
          <th scope="col">Recipe</th>
          <th scope="col">From</th>
          <th scope="col">Started by</th>
          <th scope="col">Checked</th>
          <th scope="col">Left</th>
          <th scope="col"><span class="sr">Actions</span></th>
        </tr>
      </thead>
      <tbody>
        {#each listed as draft (draft.id)}
          <tr>
            <th scope="row" class="name">{draft.name}</th>
            <td class="from"
              >{fromWords(draft)}{#if draft.source.kind === 'mealie' && draft.waiting?.length}<span
                  class="waiting">{mealieLine(draft)} · {linesWords(needYou(draft))}</span
                >{/if}</td
            >
            <td
              ><span class="who"
                ><span class="avatar" aria-hidden="true">{initial(draft.started_by)}</span
                >{draft.started_by}</span
              ></td
            >
            <td>
              <div class="progress">
                <div class="bar" aria-hidden="true">
                  <div class="fill" style:width="{progressShare(draft)}%"></div>
                </div>
                <span class="words">{shortProgress(draft)}</span>
              </div>
            </td>
            <td class="left" class:running-out={draft.days_left <= RUNNING_OUT}
              >{daysWords(draft.days_left, false)}</td
            >
            <td>
              <div class="buttons">{@render buttons(draft)}</div>
              {#if problems[draft.id]}<p class="failed-line" role="alert">
                  {problems[draft.id]}
                </p>{/if}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
    <p class="foot">
      Anyone in your household can carry on with a draft. Nothing here is in your recipes or
      ingredients until it’s saved.
    </p>
  {/if}
{/if}

<style>
  .sr {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
    white-space: nowrap;
  }

  .import {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-8);
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .loading,
  .stale,
  .foot {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    line-height: 1.45;
  }

  .foot {
    padding: var(--space-2) var(--space-6);
    text-align: center;
  }

  .failed {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
  }

  .failed p {
    color: var(--color-text-muted);
  }

  .mealie {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    max-width: 860px;
  }

  .lead,
  .waiting {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .waiting {
    display: block;
  }

  .save-all {
    min-height: var(--touch-target);
    padding: 0 var(--space-8);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .save-all:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .failed-line {
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .again {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  /* --- A phone: cards ----------------------------------------------------------------- */
  .cards {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .cards li {
    border-radius: var(--radius-2xl);
    overflow: hidden;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .head {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: var(--space-5);
  }

  .what {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .card .name {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .source {
    color: var(--color-text-muted);
    font-size: 0.8125rem;
    overflow-wrap: anywhere;
  }

  .left {
    flex: none;
    padding-top: 3px;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .left.running-out {
    color: var(--color-warning-text);
    font-weight: var(--weight-extrabold);
  }

  .progress {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .bar {
    height: 6px;
    border-radius: 3px;
    background: var(--color-border);
    overflow: hidden;
  }

  .fill {
    height: 100%;
    background: var(--color-accent);
  }

  .words {
    color: var(--color-text-muted);
    font-size: 0.8125rem;
  }

  .words.done {
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
  }

  .buttons {
    display: grid;
    grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
    gap: var(--space-4);
  }

  .buttons.three .save {
    grid-column: 1 / -1;
  }

  .buttons.three .carry,
  .buttons.three .delete {
    grid-row: 2;
  }

  .carry,
  .delete,
  .save {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 46px;
    border-radius: var(--radius-lg);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    text-decoration: none;
    cursor: pointer;
  }

  .carry {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .delete {
    border: none;
    background: var(--color-chip);
    color: var(--color-text);
  }

  .save {
    border: none;
    background: var(--color-accent);
    color: var(--color-surface);
  }

  .three .carry {
    background: var(--color-chip);
    color: var(--color-text);
  }

  button:disabled {
    opacity: 0.6;
    cursor: default;
  }

  /* --- A computer: a table ------------------------------------------------------------ */
  .table {
    width: 100%;
    max-width: 1100px;
    padding: 6px 18px;
    border-collapse: separate;
    border-spacing: 0;
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
    font-size: var(--text-base);
    text-align: left;
  }

  .table th,
  .table td {
    padding: 14px 6px;
    border-top: 1px solid var(--color-border);
    vertical-align: middle;
    font-weight: var(--weight-regular);
  }

  .table thead th {
    padding: 12px 6px;
    border-top: none;
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .table th.name {
    font-size: 1rem;
    font-weight: var(--weight-extrabold);
    /* break-word, not anywhere: the column is never narrower than a whole word, so long
       From lines can't squeeze "Minestrone" into "Minestron / e". */
    overflow-wrap: break-word;
  }

  .from {
    color: var(--color-text-soft);
    overflow-wrap: anywhere;
  }

  .who {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .avatar {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border-radius: var(--radius-full);
    background: var(--color-avatar);
    color: var(--color-avatar-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
  }

  .table .progress {
    min-width: 8rem;
    gap: var(--space-2);
  }

  .table .words {
    font-size: var(--text-sm);
  }

  .table td.left {
    font-size: var(--text-base);
  }

  .table .buttons {
    display: flex;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: var(--space-3);
  }

  .table .carry,
  .table .delete,
  .table .save {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border-radius: var(--radius-full);
    font-size: var(--text-base);
  }

  .table .delete {
    border: 1px solid var(--color-border-strong);
    background: transparent;
  }
</style>
