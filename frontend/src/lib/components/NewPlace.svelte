<script lang="ts" module>
  import '#lib/styles/fields.css';
  import { couldntAdd } from '#lib/errorWords.js';
  /** The value of the "+ Place" choice at the end of a place picker. */
  export const NEW_PLACE = 'new-place';
  export const NEEDS_SERVER =
    'A new place needs your Mealwright server. Try again when it answers.';
</script>

<script lang="ts">
  // "+ Place" (F101, cabledrawer 31 Oct): type a new place wherever a place is picked. A name box
  // and "Kept cold?" (Cupboard · Fridge · Freezer), then the new place is handed back to be
  // picked. The same box in every picker: Add to pantry, the ingredient's "Lives in", a
  // recipe import line's "Usually kept in", Put away and a Shopping tick, and a packet's
  // "Move to". Not a <form>, so it can sit inside one. Renaming, reordering and deleting
  // places stay in Settings (0.8).
  //
  // A new place is not queued: it needs the server (the safest; proposed, for cabledrawer).
  import { ApiError, cantReach } from '#lib/api.js';
  import type { Place, PlaceKind } from '#lib/client/types.js';
  import { network } from '#lib/network.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';

  let { onadded, oncancel }: { onadded: (place: Place) => void; oncancel: () => void } = $props();

  const uid = $props.id();
  const KINDS: { kind: PlaceKind; label: string }[] = [
    { kind: 'cupboard', label: 'Cupboard' },
    { kind: 'fridge', label: 'Fridge' },
    { kind: 'freezer', label: 'Freezer' }
  ];

  let name = $state('');
  let kind = $state<PlaceKind>('cupboard');
  let problem = $state<string | null>(null);
  let busy = $state(false);

  /** The picker that opened this box (it had focus): focus goes back to it on Escape/Cancel. */
  const opener = typeof document === 'undefined' ? null : document.activeElement;

  function focusOnShow(node: HTMLInputElement) {
    node.focus();
  }

  function cancel() {
    oncancel();
    if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
  }

  async function add() {
    if (busy) return;
    if (!name.trim()) {
      problem = 'Type a name.';
      return;
    }
    if (network.offline) {
      problem = NEEDS_SERVER;
      return;
    }
    busy = true;
    problem = null;
    try {
      onadded(await placesAndShops.addPlace(name, kind));
    } catch (error) {
      problem = cantReach(error)
        ? NEEDS_SERVER
        : error instanceof ApiError && error.code === 'too_many_places'
          ? error.detail
          : couldntAdd('that place');
    } finally {
      busy = false;
    }
  }

  function escapeCloses(node: HTMLElement) {
    const onkey = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      event.preventDefault();
      event.stopPropagation();
      cancel();
    };
    node.addEventListener('keydown', onkey);
    return { destroy: () => node.removeEventListener('keydown', onkey) };
  }

  function keys(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      void add();
    }
  }
</script>

<!-- Escape from anywhere in the box (the buttons too) closes it, not the sheet around it. A
  plain listener on the box itself, so it stops the key before anything above it (or the
  page's delegated handlers) sees it. -->
<div class="new-place" role="group" aria-labelledby="{uid}-t" use:escapeCloses>
  <span class="title" id="{uid}-t">New place</span>
  <label class="name">
    Place’s name
    <input
      maxlength={40}
      autocomplete="off"
      bind:value={name}
      use:focusOnShow
      onkeydown={keys}
      aria-invalid={problem === 'Type a name.' ? true : undefined}
    />
  </label>
  <span class="legend" id="{uid}-kind">Kept cold?</span>
  <div class="kinds" role="radiogroup" aria-labelledby="{uid}-kind" use:radioKeys>
    {#each KINDS as option (option.kind)}
      <button
        type="button"
        role="radio"
        aria-checked={kind === option.kind}
        onclick={() => (kind = option.kind)}
        onkeydown={keys}>{option.label}</button
      >
    {/each}
  </div>
  {#if problem}<p class="mw-error" role="alert">{problem}</p>{/if}
  <ButtonRow>
    <Button ghost onclick={cancel}>Cancel</Button>
    <Button disabled={busy} onclick={() => void add()}>Add place</Button>
  </ButtonRow>
</div>

<style>
  .new-place {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin-top: var(--space-3);
    padding: var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-surface);
  }

  .title {
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .name,
  .legend {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .name input {
    width: 100%;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
  }

  .kinds {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .kinds button {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .kinds button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }
</style>
