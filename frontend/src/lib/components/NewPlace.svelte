<script lang="ts" module>
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
  import { cantReach } from '#lib/api.js';
  import type { Place, PlaceKind } from '#lib/client/types.js';
  import { network } from '#lib/network.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';

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

  function focusOnShow(node: HTMLInputElement) {
    node.focus();
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
      problem = cantReach(error) ? NEEDS_SERVER : 'Couldn’t add that place. Try again.';
    } finally {
      busy = false;
    }
  }

  function keys(event: KeyboardEvent) {
    if (event.key === 'Enter') {
      event.preventDefault();
      void add();
    } else if (event.key === 'Escape') {
      // Closes this box only, not the sheet it is in.
      event.preventDefault();
      event.stopPropagation();
      oncancel();
    }
  }
</script>

<div class="new-place" role="group" aria-labelledby="{uid}-t">
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
  {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
  <div class="buttons">
    <button type="button" class="main" disabled={busy} onclick={() => void add()}>Add place</button>
    <button type="button" class="quiet" onclick={oncancel}>Cancel</button>
  </div>
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

  .problem {
    margin: 0;
    color: var(--color-warning-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .buttons {
    display: flex;
    gap: var(--space-3);
  }

  .buttons button {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-full);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .main {
    border-color: transparent;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .main:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .quiet {
    background: var(--color-surface);
    color: var(--color-text);
  }
</style>
