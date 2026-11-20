<script lang="ts">
  // Change on a Check row (F214, cabledrawer 10 Nov: "each ingredient row, matched or not, has Change:
  // one sheet to pick an existing ingredient, edit the name read, or make a new one"). It opens
  // under the row. Pick an ingredient and New ingredient are the row's own parts (the pick-list
  // and the form); Edit the name read corrects what the reader found and looks for an ingredient
  // by that name. Cancel leaves the row as it was. The buttons' words are cabledrawer's; the
  // hint and the box's label are accepted, cabledrawer 11 Nov.
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import { focusOnMount } from '#lib/focusOnMount.js';

  function focusFirst(node: HTMLElement) {
    node.focus();
  }

  import '#lib/styles/fields.css';
  let {
    name,
    words,
    chosen,
    onpick,
    onnew,
    onname,
    onback,
    oncancel
  }: {
    /** What the row shows in bold now. */
    name: string;
    /** The name the reader found (what the box starts with). */
    words: string;
    /** The row has a choice on it (Same as, New ingredient, …): it can be taken back. */
    chosen: boolean;
    onpick: () => void;
    onnew: () => void;
    /** The corrected name; false when it can't be used (empty), so the box says so. */
    onname: (name: string) => Promise<boolean>;
    onback: () => void;
    oncancel: () => void;
  } = $props();

  const uid = $props.id();
  let mode = $state<'menu' | 'name'>('menu');
  // svelte-ignore state_referenced_locally
  let typed = $state(words);
  let error = $state(false);
  let busy = $state(false);

  async function done() {
    if (busy) return;
    busy = true;
    error = !(await onname(typed));
    busy = false;
  }
</script>

<div class="sheet" role="group" aria-label="Change {name}">
  {#if mode === 'menu'}
    <p class="title">Change <b>{name}</b></p>
    <p class="buttons">
      <button type="button" class="chip" use:focusFirst onclick={onpick}>Pick an ingredient</button>
      <button type="button" class="chip" onclick={() => (mode = 'name')}>Edit the name read</button>
      <button type="button" class="chip" onclick={onnew}>+ New ingredient</button>
      {#if chosen}
        <button type="button" class="chip" onclick={onback}>Back to how it was read</button>
      {/if}
      <Button quiet small onclick={oncancel}>Cancel</Button>
    </p>
  {:else}
    <label class="field" for="{uid}-name">
      <span>Name read</span>
      <input
        id="{uid}-name"
        class="mw-input"
        type="text"
        maxlength="100"
        autocomplete="off"
        aria-invalid={error ? true : undefined}
        bind:value={typed}
        use:focusOnMount
        onkeydown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault();
            void done();
          } else if (e.key === 'Escape') {
            e.stopPropagation();
            oncancel();
          }
        }}
      />
    </label>
    {#if error}<p class="error" role="alert">Type a name.</p>{/if}
    <p class="hint">Mealwright looks for an ingredient with this name.</p>
    <ButtonRow>
      <Button disabled={busy} onclick={() => void done()}>Done</Button>
      <Button quiet onclick={oncancel}>Cancel</Button>
    </ButtonRow>
  {/if}
</div>

<style>
  .sheet {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-4);
    border: 1px dashed var(--color-border-strong);
    border-radius: var(--radius-lg);
  }

  .title {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    overflow-wrap: anywhere;
  }

  .title b {
    color: var(--color-text);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    flex: none;
    max-width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }
</style>
