<script lang="ts">
  // "Manage tags" (mockup Dark-RecipesTags08-Phone, cabledrawer 9 Nov): a sheet on a phone, a dialog on
  // a computer, opened from Recipes. Each tag with how many recipes use it; Rename, and
  // Merge into… another tag. A tag that looks like another (the same letters, other spelling:
  // "south-indian" and "South Indian") says so and has Merge into… as its main button. A
  // merge asks once, in words, then goes with a toast and Undo (it is in Recent changes too).
  // A rename to a name another tag has is refused with a sentence that says so.
  import { onMount, tick } from 'svelte';
  import { ApiError } from '#lib/api.js';
  import { newChangeId } from '#lib/changeId.js';
  import { serverUndo } from '#lib/client/changes.js';
  import { listTags, mergeTag, renameTag, type TagCount } from '#lib/client/recipes.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { holdUndo, undoHistory } from '#lib/undo.svelte.js';

  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import '#lib/styles/fields.css';
  import { plural } from '#lib/words.js';
  import { couldntLoad } from '#lib/errorWords.js';

  let { onclose }: { onclose: () => void } = $props();

  const uid = $props.id();
  let body: HTMLDivElement;
  let tags = $state<TagCount[]>([]);
  let loaded = $state(false);
  let problem = $state<string | null>(null);
  /** The tag being renamed, and what is typed. */
  let renaming = $state<number | null>(null);
  let typed = $state('');
  /** The tag being merged away, and the one it goes into (asked before it happens). */
  let merging = $state<number | null>(null);
  let into = $state<number | null>(null);
  let busy = $state(false);

  /** The letters and digits only, lower case: "south-indian" and "South Indian" are alike. */
  const alike = (name: string) => name.toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

  const lookalike = (tag: TagCount): TagCount | undefined =>
    tags.find((other) => other.id !== tag.id && alike(other.name) === alike(tag.name));

  const mergingTag = $derived(tags.find((t) => t.id === merging));
  const intoTag = $derived(tags.find((t) => t.id === into));

  async function load() {
    try {
      tags = (await listTags()).tags;
      problem = null;
    } catch {
      problem = couldntLoad('the tags');
    }
    loaded = true;
  }

  onMount(() => {
    const letGo = holdUndo(); // Ctrl+Z must not move anything behind this sheet
    void load();
    return () => {
      letGo();
    };
  });

  // Another phone, or an Undo from the toast, changed the tags: read them again.
  let seen = kitchen.version;
  $effect(() => {
    const now = kitchen.version;
    if (now !== seen) {
      seen = now;
      void load();
    }
  });

  async function startRename(tag: TagCount) {
    merging = null;
    problem = null;
    renaming = tag.id;
    typed = tag.name;
    await tick();
    body.querySelector<HTMLInputElement>('input.rename')?.select();
  }

  async function saveRename(tag: TagCount) {
    const name = typed.trim();
    if (!name || busy) return;
    if (name === tag.name) {
      renaming = null;
      return;
    }
    busy = true;
    problem = null;
    try {
      await renameTag(tag.id, name);
      renaming = null;
      kitchen.changed();
      await load();
    } catch (error) {
      problem = error instanceof ApiError ? error.detail : 'Couldn’t rename the tag. Try again.';
    } finally {
      busy = false;
    }
  }

  function startMerge(tag: TagCount) {
    renaming = null;
    problem = null;
    merging = tag.id;
    body.closest('dialog')?.scrollTo(0, 0); // the picker replaces the list, so it is the first thing in view
    into = (lookalike(tag) ?? tags.find((t) => t.id !== tag.id))?.id ?? null;
    // The button pressed is gone with the list: the keyboard goes to the picker (FX4 review r1).
    void tick().then(() => document.getElementById(`${uid}-into`)?.focus());
  }

  /** Cancel the merge: the list comes back, and the keyboard is on that tag's Merge into…. */
  function cancelMerge() {
    const id = merging;
    merging = null;
    void tick().then(() => body.querySelector<HTMLButtonElement>(`[data-merge="${id}"]`)?.focus());
  }

  async function doMerge() {
    const from = mergingTag;
    const target = intoTag;
    if (!from || !target || busy) return;
    busy = true;
    problem = null;
    try {
      const { change } = await mergeTag(from.id, target.id, newChangeId());
      merging = null;
      kitchen.changed();
      undoHistory.record({
        label: change.summary,
        needsServer: true,
        undo: serverUndo(change.id)
      });
      await load();
    } catch (error) {
      problem = error instanceof ApiError ? error.detail : 'Couldn’t merge the tags. Try again.';
    } finally {
      busy = false;
    }
  }

  const count = (n: number) => `${n} ${plural(n, 'recipe', 'recipes')}`;
</script>

<Sheet title="Manage tags" {onclose}>
  <div class="body" bind:this={body}>
    {#if loaded}<p class="total">{tags.length} {plural(tags.length, 'tag', 'tags')}</p>{/if}

    {#if loaded && tags.length === 0 && !problem}
      <p class="muted">No tags yet. Add one to a recipe and it shows here.</p>
    {/if}

    {#if tags.length && !mergingTag}
      <ul class="card">
        {#each tags as tag (tag.id)}
          {@const like = lookalike(tag)}
          <li class:like={like !== undefined}>
            {#if renaming === tag.id}
              <form
                class="edit"
                onsubmit={(e) => {
                  e.preventDefault();
                  void saveRename(tag);
                }}
              >
                <label class="visually-hidden" for="{uid}-rename">New name for {tag.name}</label>
                <input
                  id="{uid}-rename"
                  class="rename mw-input"
                  maxlength="40"
                  bind:value={typed}
                  autocomplete="off"
                />
                <Button small quiet onclick={() => (renaming = null)}>Cancel</Button>
                <Button type="submit" small disabled={busy || !typed.trim()}>Save</Button>
              </form>
            {:else}
              <span class="what">
                <b>{tag.name}</b>
                <span class="sub"
                  >{count(tag.recipes)}{#if like}{` · looks like ${like.name}`}{/if}</span
                >
              </span>
              <span class="buttons">
                <Button
                  small
                  quiet
                  aria-label="Rename {tag.name}"
                  onclick={() => void startRename(tag)}>Rename</Button
                >
                {#if tags.length > 1}
                  <Button
                    small
                    quiet={like === undefined}
                    aria-label="Merge {tag.name} into…"
                    data-merge={tag.id}
                    onclick={() => startMerge(tag)}>Merge into…</Button
                  >
                {/if}
              </span>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    {#if mergingTag}
      <div class="ask">
        <label for="{uid}-into">Merge “{mergingTag.name}” into</label>
        <select id="{uid}-into" class="mw-input" bind:value={into}>
          {#each tags.filter((t) => t.id !== mergingTag.id) as other (other.id)}
            <option value={other.id}>{other.name}</option>
          {/each}
        </select>
        {#if intoTag}
          <p class="note">
            Merge “{mergingTag.name}” into “{intoTag.name}”? Its {count(mergingTag.recipes)}
            {plural(mergingTag.recipes, 'gets', 'get')} “{intoTag.name}”, and “{mergingTag.name}”
            goes. You can Undo.
          </p>
        {/if}
        <ButtonRow>
          <Button disabled={busy || !intoTag} onclick={() => void doMerge()}>Merge</Button>
          <Button quiet onclick={cancelMerge}>Cancel</Button>
        </ButtonRow>
      </div>
    {/if}

    {#if problem}<p class="error" role="alert">{problem}</p>{/if}

    {#if !mergingTag}
      <Button quiet onclick={onclose}>Close</Button>
    {/if}
  </div>
</Sheet>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .total,
  .sub,
  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .card {
    margin: 0;
    padding: 0 var(--space-6);
    list-style: none;
    border-radius: var(--radius-2xl);
    background: var(--color-ground);
  }

  li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: var(--space-4);
    min-height: 56px;
    padding: var(--space-3) 0;
    border-bottom: 1px solid var(--color-border);
  }

  li:last-child {
    border-bottom: none;
  }

  li.like {
    margin: 0 calc(var(--space-6) * -1);
    padding: var(--space-3) var(--space-6);
    background: var(--color-accent-soft);
  }

  .what {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .buttons,
  .edit {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .edit {
    flex: 1;
    align-items: center;
  }

  .rename {
    flex: 1;
    min-width: 8rem;
  }

  .ask {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .ask select {
    font-size: 1rem;
  }

  .ask label {
    font-weight: var(--weight-bold);
  }

  .note {
    padding: var(--space-5);
    border-radius: var(--radius-xl);
    background: var(--color-ground);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
  }
</style>
