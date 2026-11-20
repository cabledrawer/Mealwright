<script lang="ts">
  import '#lib/styles/fields.css';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import Loading from '#lib/components/Loading.svelte';
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
  import { plural } from '#lib/words.js';
  import { couldntLoad } from '#lib/errorWords.js';

  const uid = $props.id();

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
      problem = error instanceof ApiError ? error.detail : couldntLoad('the starter packs');
    }
  }

  $effect(() => {
    if (starterPacks.open) {
      pickedId = null;
      unticked = new Set();
      loaded = false;
      void load();
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
    const many = `${keys.length} ${plural(keys.length, 'ingredient', 'ingredients')}`;
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

<!-- Only while open: a closed dialog keeps no words in the page. -->
{#if starterPacks.open}
  <Sheet
    title={picked ? `${picked.name} starter pack` : 'Add a starter pack'}
    outside={false}
    onclose={() => starterPacks.close()}
  >
    <form
      onsubmit={(event) => {
        event.preventDefault();
        add();
      }}
    >
      {#if problem}
        <p class="mw-error" role="alert">{problem}</p>
        <ButtonRow>
          <Button fill onclick={() => starterPacks.close()}>Close</Button>
          <Button onclick={() => void load()}>Try again</Button>
        </ButtonRow>
      {:else if !loaded}
        <Loading />
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
                  >{pack.items.length} ingredients{pack.already_have
                    ? ` · ${pack.already_have} already here`
                    : ''}</span
                >
              </button>
            </li>
          {/each}
        </ul>
        <ButtonRow>
          <Button fill onclick={() => starterPacks.close()}>Cancel</Button>
        </ButtonRow>
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
        <ButtonRow>
          <Button fill onclick={() => (pickedId = null)}>Back</Button>
          <Button
            type="submit"
            aria-describedby={network.offline ? `${uid}-down` : undefined}
            disabled={!chosen.length || network.offline}
            >{chosen.length === 1 ? 'Add 1 ingredient' : `Add ${chosen.length} ingredients`}</Button
          >
        </ButtonRow>
        {#if network.offline}<p class="hint" id="{uid}-down">{offlineReason}</p>{/if}
      {/if}
    </form>
  </Sheet>
{/if}

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-regular);
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
    font-size: var(--text-base);
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
    outline: var(--focus-width) solid var(--color-focus);
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
</style>
