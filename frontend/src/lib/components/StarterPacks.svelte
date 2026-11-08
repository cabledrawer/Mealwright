<script lang="ts">
  // "Add a starter pack" (0.8 R4; spec section 2): pick one of the seven packs, see its
  // ingredients with every one ticked, untick any, then "Add N ingredients". Ingredients that
  // are already here (by name or another name) show "Already have" and are skipped. One toast
  // with one Undo takes the whole addition away. A modal dialog: Escape = Cancel.
  import { ApiError } from '#lib/api.js';
  import { serverUndo } from '#lib/client/changes.js';
  import { addStarterPack, getStarterPacks, type StarterPack } from '#lib/client/starterPacks.js';
  import { cantReachText, needsServer } from '#lib/downWords.js';
  import { kitchen } from '#lib/freshness.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { save } from '#lib/save.js';
  import { starterPacks } from '#lib/starterPacks.svelte.js';

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  let packs = $state<StarterPack[]>([]);
  let loaded = $state(false);
  let problem = $state<string | null>(null);
  /** The pack whose list is showing; null while the packs are listed. */
  let pickedId = $state<string | null>(null);
  let unticked = $state(new Set<string>());

  const picked = $derived(packs.find((p) => p.id === pickedId) ?? null);
  const fresh = $derived(picked ? picked.items.filter((i) => !i.already_have) : []);
  const chosen = $derived(fresh.filter((i) => !unticked.has(i.key)));
  const offlineReason = $derived(needsServer(network.deviceOffline, cantReachText(true)));

  async function load() {
    problem = null;
    try {
      packs = (await getStarterPacks()).packs;
      loaded = true;
    } catch (error) {
      problem = error instanceof ApiError ? error.detail : 'Couldn’t load the starter packs.';
    }
  }

  $effect(() => {
    if (starterPacks.open) {
      pickedId = null;
      unticked = new Set();
      loaded = false;
      void load();
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  });

  function pick(id: string) {
    pickedId = id;
    unticked = new Set();
  }

  function toggle(key: string) {
    unticked = unticked.has(key)
      ? new Set([...unticked].filter((k) => k !== key))
      : new Set([...unticked, key]);
  }

  function add() {
    if (!picked || !chosen.length || network.offline) return;
    const pack = picked;
    const keys = chosen.map((item) => item.key);
    const many = `${keys.length} ${keys.length === 1 ? 'ingredient' : 'ingredients'}`;
    starterPacks.close();
    let undoer: (() => Promise<string | void>) | null = null;
    void save({
      apply: () => {},
      rollback: () => {},
      send: (changeId) => addStarterPack(pack.id, keys, changeId),
      saved: () => kitchen.changed({ elsewhere: true }),
      undo: {
        label: `Added the ${pack.name} starter pack: ${many}`,
        labelFrom: (result) => result.change.summary,
        run: (result) => (undoer ??= serverUndo(result.change.id))()
      }
    });
  }
</script>

<dialog bind:this={dialog} aria-labelledby="{uid}-title" oncancel={() => starterPacks.close()}>
  <!-- Only while open: a closed dialog keeps no words in the page (its "Loading…" was found by
       other screens' tests, and is read by nothing while shut). -->
  {#if starterPacks.open}
    <form
      onsubmit={(event) => {
        event.preventDefault();
        add();
      }}
    >
      <h2 id="{uid}-title">{picked ? `${picked.name} starter pack` : 'Add a starter pack'}</h2>

      {#if problem}
        <p class="problem" role="alert">{problem}</p>
        <div class="buttons">
          <button type="button" class="quiet" onclick={() => starterPacks.close()}>Close</button>
          <button type="button" class="main" onclick={() => void load()}>Try again</button>
        </div>
      {:else if !loaded}
        <p class="hint">Loading…</p>
      {:else if !picked}
        <p class="hint">
          Pick a pack. You’ll see its ingredients first and can untick any. Only ingredients are
          added, never anything in your pantry or on your list.
        </p>
        <ul class="packs">
          {#each packs as pack (pack.id)}
            <li>
              <button type="button" class="pack" onclick={() => pick(pack.id)}>
                <span class="label">{pack.name}</span>
                <span class="hint"
                  >{pack.items.length} ingredients{#if pack.already_have}
                    · {pack.already_have} already here{/if}</span
                >
              </button>
            </li>
          {/each}
        </ul>
        <div class="buttons">
          <button type="button" class="quiet" onclick={() => starterPacks.close()}>Cancel</button>
        </div>
      {:else}
        {#if picked.items.some((i) => i.staple)}
          <p class="hint">These are added as “Don’t count it”: always assumed to be in stock.</p>
        {/if}
        {#if fresh.length === 0}
          <p class="hint">You already have every ingredient in this pack.</p>
        {:else}
          <div class="all">
            <span class="hint" aria-live="polite">{chosen.length} of {fresh.length} ticked</span>
            <button
              type="button"
              class="link"
              onclick={() =>
                (unticked = chosen.length ? new Set(fresh.map((i) => i.key)) : new Set())}
              >{chosen.length ? 'Untick all' : 'Tick all'}</button
            >
          </div>
        {/if}
        <ul class="items" aria-label="{picked.name} ingredients">
          {#each picked.items as item (item.key)}
            <li class:have={item.already_have}>
              <label>
                <input
                  type="checkbox"
                  checked={!item.already_have && !unticked.has(item.key)}
                  disabled={item.already_have}
                  onchange={() => toggle(item.key)}
                />
                <span class="box" aria-hidden="true"></span>
                <span class="what">{item.name}</span>
                {#if item.already_have}
                  <span class="tag"
                    >{item.have_as ? `Already have as “${item.have_as}”` : 'Already have'}</span
                  >
                {/if}
              </label>
            </li>
          {/each}
        </ul>
        <div class="buttons">
          <button type="button" class="quiet" onclick={() => (pickedId = null)}>Back</button>
          <button
            type="submit"
            class="main"
            aria-describedby={network.offline ? `${uid}-down` : undefined}
            disabled={!chosen.length || network.offline}
            >{chosen.length === 1 ? 'Add 1 ingredient' : `Add ${chosen.length} ingredients`}</button
          >
        </div>
        {#if network.offline}<p class="hint" id="{uid}-down">{offlineReason}</p>{/if}
      {/if}
    </form>
  {/if}
</dialog>

<style>
  dialog {
    width: min(520px, calc(100vw - 2 * var(--space-7)));
    max-height: calc(100dvh - 2 * var(--space-7));
    padding: var(--space-9);
    border: none;
    border-radius: var(--radius-panel);
    background: var(--color-surface);
    color: var(--color-text);
    overflow-y: auto;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-regular);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  ul {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .packs {
    gap: var(--space-3);
  }

  .pack {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-5) var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    text-align: left;
    cursor: pointer;
  }

  .pack:hover {
    border-color: var(--color-accent);
  }

  .pack .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .all {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .items {
    max-height: min(52dvh, 480px);
    overflow-y: auto;
    border-top: 1px solid var(--color-divider);
  }

  .items li {
    border-bottom: 1px solid var(--color-divider);
  }

  label {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: var(--touch-target);
    padding: var(--space-2) var(--space-2);
  }

  /* The real checkbox covers the whole row (a 44 px target); a drawn box shows its state. */
  input[type='checkbox'] {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  input[type='checkbox']:disabled {
    cursor: default;
  }

  .box {
    flex: none;
    display: grid;
    place-items: center;
    width: 20px;
    height: 20px;
    border: 2px solid var(--color-field-border);
    border-radius: 6px;
    background: var(--color-field);
    color: var(--color-inverse-text);
    font-size: 14px;
    line-height: 1;
  }

  input:checked + .box {
    border-color: var(--color-accent-hover);
    background: var(--color-accent-hover);
  }

  input:checked + .box::after {
    content: '✓';
  }

  input:focus-visible + .box {
    outline: 3px solid var(--color-focus);
    outline-offset: 2px;
  }

  .what {
    flex: 1 1 8rem;
    font-weight: var(--weight-semibold);
    overflow-wrap: anywhere;
  }

  .have .what,
  .have .box {
    opacity: 0.6;
  }

  .tag {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .link {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .buttons {
    display: flex;
    justify-content: flex-end;
    gap: var(--space-4);
  }

  .buttons button {
    min-height: var(--touch-target);
    padding: 0 var(--space-8);
    border: none;
    border-radius: var(--radius-full);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .quiet {
    background: var(--color-fill);
    color: var(--color-text);
  }

  .main {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .main:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }
</style>
