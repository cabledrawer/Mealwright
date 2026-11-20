<script lang="ts">
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Loading from '#lib/components/Loading.svelte';
  // Drafts, "By ingredient" (cabledrawer 15 Nov, 0.9.5-beta.2; mockups
  // Dark-MealieByIngredient2-Desktop and -Phone; the words: groupWords.ts, proposed, for
  // cabledrawer). The lines of the Mealie drafts that couldn't be matched are grouped by
  // ingredient, most-used first. One answer for a group (an ingredient the household has, a new
  // one with its pantry place, or plain text) goes into every draft that uses it. Nothing is
  // saved until the person answers; "Skip for now" changes nothing on the server. A recipe
  // whose lines are all answered moves from Drafts to Recipes. The toast's Undo (or Ctrl+Z)
  // reverses the group's answers. Computer: the list and the answer side by side. Phone: the
  // list, then the answer on its own page with a back button. Online only.
  import { untrack } from 'svelte';
  import { ApiError, cantReach, wordsFor } from '#lib/api.js';
  import { newChangeId } from '#lib/changeId.js';
  import { serverUndo } from '#lib/client/changes.js';
  import {
    answerGroup,
    groupLines,
    type GroupAnswer,
    listGroups,
    type GroupLines,
    type IngredientGroup,
    type IngredientGroups
  } from '#lib/client/drafts.js';
  import type { Ref } from '#lib/client/types.js';
  import { drafts } from '#lib/drafts.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { undoHistory } from '#lib/undo.svelte.js';
  import * as words from '#lib/groupWords.js';
  import EmptyState from '../EmptyState.svelte';
  import FoodPicker from '../FoodPicker.svelte';
  import Icon from '../Icon.svelte';
  import OfflineNote from '../OfflineNote.svelte';

  let { phone = false }: { phone?: boolean } = $props();

  /** The most groups asked for at first; "Show all" asks for more (proposed, for cabledrawer). */
  const FIRST = 50;
  const ALL = 5000;

  let found = $state<IngredientGroups | null>(null);
  let loading = $state(true);
  let problem = $state<string | null>(null);
  let all = $state(false);
  let asked = 0;

  async function load() {
    const mine = ++asked;
    problem = null;
    try {
      const answer = await listGroups(all ? ALL : FIRST);
      if (mine !== asked) return;
      found = answer;
    } catch (error) {
      if (mine !== asked) return;
      problem = error instanceof ApiError && !cantReach(error) ? error.detail : words.COULDNT_LOAD;
    } finally {
      if (mine === asked) loading = false;
    }
  }
  $effect(() => {
    // Asked again when Show all is pressed, and when the server can be reached again.
    void all;
    void network.backAgain;
    if (!network.offline) untrack(() => void load());
  });

  /** The groups whose answers are being saved (F260–F262): out of the list at once. */
  let saving = $state<string[]>([]);
  const groups = $derived((found?.groups ?? []).filter((g) => !saving.includes(g.key)));
  const places = $derived(found?.places ?? []);

  /** Which group is open. The computer always has one (the first, until another is chosen); the
   *  phone has one only once a row is pressed (its answer is then a page of its own). */
  let chosen = $state<string | null>(null);
  const selected = $derived<IngredientGroup | null>(
    groups.find((g) => g.key === chosen) ?? (phone ? null : (groups[0] ?? null))
  );

  type Mode = 'ingredient' | 'new' | 'text';
  let mode = $state<Mode>('new');
  let food = $state<Ref | null>(null);
  let picking = $state(false);
  let newName = $state('');
  let placeId = $state<number | null>(null);

  let formFor = '';
  function reset(group: IngredientGroup) {
    food = group.suggestion;
    mode = group.suggestion ? 'ingredient' : 'new';
    picking = false;
    newName = group.new_name;
    placeId = group.new_place?.id ?? places[0]?.id ?? null;
    // Another group (or this one after an answer or Undo): its lines as written start short.
    more = null;
    moreFor = null;
    moreFailed = null;
  }
  $effect(() => {
    const group = selected;
    if (!group || group.key === formFor) return;
    formFor = group.key;
    untrack(() => reset(group));
  });

  const ready = $derived(
    mode === 'text' ||
      (mode === 'ingredient' && food !== null) ||
      (mode === 'new' && !!newName.trim())
  );

  let failed = $state<string | null>(null);
  /** The change ID of each answer not yet saved (one per answer): a press again after a dropped
   * connection sends the same ID, so the server gives the first result, not a second answer. */
  const attempts: Record<string, string> = {};

  function openRow(group: IngredientGroup) {
    chosen = group.key;
    failed = null;
  }

  /** "+ more" (F259): every way the open group's lines are written, once asked for. Shown only
   *  while that group stays open. */
  let more = $state<GroupLines | null>(null);
  let moreFor = $state<string | null>(null);
  let moreFailed = $state<string | null>(null);
  let fetching = false;
  const shownMore = $derived(more && selected && more.key === selected.key ? more : null);

  async function showMore(group: IngredientGroup) {
    if (fetching) return;
    fetching = true;
    moreFailed = null;
    moreFor = group.key;
    try {
      const found = await groupLines(group.key);
      if (moreFor === group.key) more = found;
    } catch (error) {
      if (moreFor === group.key) moreFailed = wordsFor(error);
    } finally {
      fetching = false;
    }
  }

  function showFewer() {
    more = null;
    moreFor = null;
  }

  /** The next group in the list after this one (null at the end). */
  function after(group: IngredientGroup): IngredientGroup | null {
    const at = groups.findIndex((g) => g.key === group.key);
    return groups[at + 1] ?? null;
  }

  /** Skip for now: nothing is sent; the next group opens (the phone goes back to its list). */
  function skip() {
    const group = selected;
    if (!group) return;
    failed = null;
    chosen = phone ? null : (after(group)?.key ?? null);
  }

  /** How long "Saving…" and "Undoing…" toasts may stay: until the server's answer replaces them. */
  const WAITING_MS = 120_000;
  /** The answers being saved, one after another in the order given. */
  let queue: Promise<void> = Promise.resolve();

  function refresh() {
    void Promise.all([load(), drafts.load()]);
  }

  /** F260–F262: the answer is saved in the background. The next group opens at once and the
   *  count of groups left goes down at once; the toast says it is saving, then gives the
   *  server's summary with Undo. A save that fails brings its group back, saying why. */
  function answer() {
    const group = selected;
    if (!group || !ready || network.offline) return;
    const body =
      mode === 'ingredient' && food
        ? ({ key: group.key, kind: 'ingredient', food_id: food.id } as const)
        : mode === 'new'
          ? ({ key: group.key, kind: 'new', name: newName.trim(), place_id: placeId } as const)
          : ({ key: group.key, kind: 'text' } as const);
    const sent = JSON.stringify(body);
    const id = (attempts[sent] ??= newChangeId());
    failed = null;
    chosen = phone ? null : (after(group)?.key ?? null);
    saving = [...saving, group.key];
    const toast = toasts.show(words.savingWords(group.name), { duration: WAITING_MS });
    queue = queue.then(() => save(group, body, sent, id, toast));
  }

  async function save(
    group: IngredientGroup,
    body: GroupAnswer,
    sent: string,
    id: string,
    toast: number
  ) {
    try {
      const done = await answerGroup(body, id);
      delete attempts[sent];
      const change = done.change;
      undoHistory.record({
        label: change.summary,
        needsServer: true,
        undo: async () => {
          toasts.show(words.undoingWords(group.name), { duration: WAITING_MS });
          const message = await serverUndo(change.id)();
          formFor = '';
          refresh();
          return message;
        }
      });
      if (found) {
        const gone = found.groups.some((g) => g.key === group.key);
        found = {
          ...found,
          groups: found.groups.filter((g) => g.key !== group.key),
          total: Math.max(0, found.total - (gone ? 1 : 0)),
          drafts: Math.max(0, found.drafts - done.moved),
          recipes_ready: found.recipes_ready + done.moved
        };
      }
      saving = saving.filter((k) => k !== group.key);
      refresh();
    } catch (error) {
      toasts.dismiss(toast);
      saving = saving.filter((k) => k !== group.key);
      if (error instanceof ApiError && error.status === 404) {
        // Another person got there first.
        delete attempts[sent];
        failed = words.ALREADY_ANSWERED;
      } else {
        // Back to the group that didn't save, with why; a press again sends the same change ID.
        chosen = group.key;
        failed = `${words.couldntSaveFor(group.name)} ${wordsFor(error)}`;
      }
      void load();
    }
  }

  const left = $derived(
    (found?.total ?? 0) - saving.filter((k) => found?.groups.some((g) => g.key === k)).length
  );
  const readyRecipes = $derived(found?.recipes_ready ?? 0);
  const percent = $derived.by(() => {
    const total = readyRecipes + (found?.drafts ?? 0);
    return total ? Math.round((readyRecipes / total) * 100) : 0;
  });

  /** Up and down move between the rows of the list. */
  function move(event: KeyboardEvent) {
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    const rows = Array.from(
      (event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('button.row')
    );
    const at = rows.indexOf(document.activeElement as HTMLButtonElement);
    const next = rows[at + (event.key === 'ArrowDown' ? 1 : -1)];
    if (at >= 0 && next) {
      event.preventDefault();
      next.focus();
    }
  }
</script>

{#snippet progress()}
  <div class="progress">
    {#if phone}
      <strong>{words.leftPhoneWords(left, readyRecipes)}</strong>
    {:else}
      <div class="line">
        <strong>{words.leftWords(left)}</strong>
        <span class="sub">{words.readyWords(readyRecipes)}</span>
      </div>
    {/if}
    <div
      class="bar"
      role="progressbar"
      aria-label="Recipes ready"
      aria-valuemin="0"
      aria-valuemax="100"
      aria-valuenow={percent}
    >
      <span style:width="{percent}%"></span>
    </div>
    <span class="small">{phone ? words.LEAD_PHONE : words.LEAD}</span>
  </div>
{/snippet}

{#snippet list()}
  <section class="card list" aria-label="Ingredients to answer">
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div role="group" aria-label="Ingredients to answer" onkeydown={move}>
      {#each groups as group (group.key)}
        <button
          type="button"
          class="row"
          aria-current={!phone && selected?.key === group.key}
          onclick={() => openRow(group)}
        >
          <span class="rn">
            <b>{group.name}</b>
            <span>{group.examples.map((line) => `“${line}”`).join(', ')}</span>
          </span>
          <span class="cnt">{words.inDraftsWords(group.drafts, !phone)}</span>
        </button>
      {/each}
    </div>
    {#if found && found.total > groups.length}
      <p class="small foot">
        {words.SHOWING_FIRST} ·
        <button type="button" class="linkish" onclick={() => (all = true)}>{words.SHOW_ALL}</button>
      </p>
    {/if}
  </section>
{/snippet}

{#snippet examples(group: IngredientGroup)}
  <div class="examples">
    {#if shownMore}
      {#each shownMore.lines as line (line.written)}<span class="q"
          >{line.written}{#if line.count > 1}<span class="times"
              >{` · ${words.timesWords(line.count)}`}</span
            >{/if}</span
        >{/each}
      {#if shownMore.total > shownMore.lines.length}<span class="small left"
          >{words.moreWaysWords(shownMore.total - shownMore.lines.length)}</span
        >{/if}
      <button type="button" class="q more" aria-expanded="true" onclick={showFewer}
        >{words.FEWER_LINES}</button
      >
    {:else}
      {#each group.examples as line (line)}<span class="q">{line}</span>{/each}
      {#if group.lines > group.examples.length}<button
          type="button"
          class="q more"
          aria-expanded="false"
          onclick={() => void showMore(group)}>{words.MORE_LINES}</button
        >{/if}
    {/if}
  </div>
  {#if moreFailed && moreFor === group.key}<p class="failed-line" role="alert">
      {moreFailed}
    </p>{/if}
{/snippet}

{#snippet panel(group: IngredientGroup)}
  <div class="options">
    <button
      type="button"
      class="opt"
      aria-pressed={mode === 'ingredient'}
      onclick={() => (mode = 'ingredient')}
    >
      <span class="dot"></span>
      <span class="grow">{phone ? words.OPTION_HAVE_PHONE : words.OPTION_HAVE}</span>
    </button>
    {#if mode === 'ingredient'}
      <div class="fld">
        <span class="label">{words.WHICH_ONE}</span>
        {#if food && !picking}
          <div class="picked">
            <span class="grow">{food.name}</span>
            <button type="button" class="linkish" onclick={() => (picking = true)}
              >{words.CHANGE_IT}</button
            >
          </div>
          <span class="small">{words.SUGGESTED}</span>
        {:else}
          <FoodPicker
            label={words.WHICH_ONE}
            placeholder="Type a name"
            onpick={(picked) => {
              food = picked;
              picking = false;
            }}
            oncancel={() => (picking = false)}
          />
          <span class="small">{words.NO_SUGGESTION}</span>
        {/if}
      </div>
    {/if}
    <button type="button" class="opt" aria-pressed={mode === 'new'} onclick={() => (mode = 'new')}>
      <span class="dot"></span>
      <span class="grow">{words.OPTION_NEW}</span>
    </button>
    {#if mode === 'new'}
      <label class="fld"
        >{words.NAME}
        <input type="text" bind:value={newName} maxlength="100" autocomplete="off" />
      </label>
      <div class="fld" role="group" aria-label={words.KEPT}>
        <span class="label">{words.KEPT}</span>
        <div class="chips">
          {#each places as place (place.id)}
            <button
              type="button"
              class="chip"
              aria-pressed={placeId === place.id}
              onclick={() => (placeId = place.id)}>{place.name}</button
            >
          {/each}
        </div>
      </div>
    {/if}
    <button
      type="button"
      class="opt"
      aria-pressed={mode === 'text'}
      onclick={() => (mode = 'text')}
    >
      <span class="dot"></span>
      <span class="grow"
        >{words.OPTION_TEXT}<span class="small hint"
          >{phone ? words.TEXT_HINT_PHONE : words.TEXT_HINT}</span
        ></span
      >
    </button>
  </div>
  {#if failed}<p class="failed-line" role="alert">{failed}</p>{/if}
  <div class="actions" class:sticky={phone}>
    <ButtonRow>
      <Button quiet onclick={skip}>{phone ? words.SKIP_PHONE : words.SKIP}</Button>
      <Button disabled={!ready || network.offline} onclick={answer}
        >{words.useForAll(group.drafts, phone)}</Button
      >
    </ButtonRow>
  </div>
{/snippet}

{#if network.offline && !found}
  <OfflineNote screen="Drafts" />
{:else if loading && !found}
  <Loading />
{:else if problem && !found}
  <div class="failed" role="alert">
    <p>{problem}</p>
    <Button quiet small onclick={() => void load()}>Try again</Button>
  </div>
{:else if found}
  {#if network.offline}
    <p class="stale" role="status">Offline. You can look, but answers need the server.</p>
  {/if}
  {#if phone && selected}
    <div class="sheet">
      <div class="top">
        <button
          type="button"
          class="x"
          aria-label={words.BACK_TO_LIST}
          onclick={() => (chosen = null)}><Icon name="back" size={20} /></button
        >
        <h2 class="title">{selected.name}</h2>
        <span class="cnt">{words.draftsWords(selected.drafts)}</span>
      </div>
      <p class="small caps">{words.WRITTEN_AS}</p>
      {@render examples(selected)}
      {@render panel(selected)}
    </div>
  {:else}
    {@render progress()}
    {#if problem}<p class="failed-line" role="alert">{problem}</p>{/if}
    {#if failed && !selected}<p class="failed-line" role="alert">{failed}</p>{/if}
    {#if groups.length === 0}
      <EmptyState title={words.ALL_DONE_TITLE}>{words.ALL_DONE}</EmptyState>
    {:else if phone}
      {@render list()}
    {:else}
      <div class="wide">
        {@render list()}
        {#if selected}
          <section class="card answer" aria-label="Answer">
            <div class="what">
              <span class="small caps">{words.usedIn(selected.drafts)}</span>
              <h2>{selected.name}</h2>
            </div>
            {@render examples(selected)}
            {@render panel(selected)}
          </section>
        {/if}
      </div>
    {/if}
  {/if}
{/if}

<style>
  .stale {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .failed {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
  }

  .failed-line {
    color: var(--color-warning-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  .card {
    display: flex;
    flex-direction: column;
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .small {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .caps {
    font-weight: var(--weight-bold);
    letter-spacing: 0.06em;
    text-transform: uppercase;
  }

  /* --- The progress line and bar -------------------------------------------------------- */
  .progress {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 1100px;
    padding: var(--space-5) var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .line {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-4);
  }

  .line strong {
    font-size: var(--text-xl);
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .bar {
    height: 10px;
    border-radius: 5px;
    background: var(--color-border);
    overflow: hidden;
  }

  .bar span {
    display: block;
    height: 100%;
    border-radius: 5px;
    background: var(--color-accent);
  }

  /* --- The list ------------------------------------------------------------------------- */
  .wide {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.15fr);
    gap: var(--space-8);
    align-items: start;
    max-width: 1100px;
  }

  .list {
    overflow: hidden;
  }

  .row {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    width: 100%;
    min-height: 58px;
    padding: var(--space-3) var(--space-6);
    border: none;
    border-top: 1px solid var(--color-border);
    background: transparent;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .row:first-child {
    border-top: none;
  }

  .row[aria-current='true'] {
    background: var(--color-accent-soft);
  }

  .rn {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .rn b {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .rn span {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .cnt {
    color: var(--color-warning-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    white-space: nowrap;
  }

  .foot {
    margin: 0;
    padding: var(--space-4) var(--space-6);
    border-top: 1px solid var(--color-border);
  }

  .linkish {
    padding: 0;
    border: none;
    background: none;
    color: var(--color-accent-on-soft);
    font: inherit;
    font-weight: var(--weight-bold);
    text-decoration: underline;
    cursor: pointer;
  }

  /* --- The answer ----------------------------------------------------------------------- */
  .answer {
    gap: var(--space-6);
    padding: var(--space-8);
  }

  .what {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  h2 {
    margin: 0;
    font-size: var(--text-2xl, 1.5rem);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .examples {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }

  .q {
    padding: 8px 10px;
    border-radius: 10px;
    background: var(--color-field);
    color: var(--color-text-soft);
    font-family: ui-monospace, Menlo, Consolas, monospace;
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  .times {
    color: var(--color-text-muted);
    font-family: var(--font-ui);
    white-space: nowrap;
  }

  .more {
    border: 1px solid var(--color-border-strong);
    color: var(--color-accent-on-soft);
    font-family: var(--font-ui);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  /* "+ more" and "Show fewer" on the phone: a finger-sized target, like every button there. */
  .sheet .more {
    min-height: var(--touch-target);
  }

  .left {
    align-self: center;
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .opt {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-4) var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-lg) var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .opt[aria-pressed='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
  }

  .dot {
    flex: none;
    box-sizing: border-box;
    width: 20px;
    height: 20px;
    border: 2px solid var(--color-border-strong);
    border-radius: 10px;
  }

  .opt[aria-pressed='true'] .dot {
    border: 6px solid var(--color-accent);
  }

  .grow {
    flex: 1;
  }

  .hint {
    display: block;
    font-weight: var(--weight-medium);
  }

  .fld {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    color: var(--color-text-soft);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .fld input {
    box-sizing: border-box;
    width: 100%;
    min-height: 46px;
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  .picked {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 46px;
    padding: 0 var(--space-5);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font-weight: var(--weight-medium);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    min-height: 44px;
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: var(--color-field);
    color: var(--color-text-soft);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .chip[aria-pressed='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .actions {
    margin-top: var(--space-2);
  }

  button:disabled {
    opacity: 0.55;
    cursor: default;
  }

  /* --- A phone: the answer is a page of its own ----------------------------------------- */
  .sheet {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .top {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  .x {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text);
    cursor: pointer;
  }

  .title {
    flex: 1;
    font-size: var(--text-xl);
  }

  .sticky {
    position: sticky;
    bottom: 0;
    padding: var(--space-4) 0;
    background: var(--color-ground);
  }
</style>
