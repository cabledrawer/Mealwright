<script lang="ts">
  // Desktop only (mockup Desktop-Shop): "Put away", beside the list. Ticked items go straight
  // into the pantry; choose where the last one went, or Undo last tick. The phone has the
  // toast ("Coriander → Fridge · Change · Undo") instead.
  import type { ShoppingModel } from '$lib/shopping/store.svelte';

  let { model }: { model: ShoppingModel } = $props();
  const uid = $props.id();

  const last = $derived(model.lastTicked);
  const item = $derived(last ? model.item(last.itemId) : undefined);
  const standing = $derived(item?.ticks.some((t) => t.standing) ?? false);
  // Offline the tick has no place yet: where it will go (its usual place) shows meanwhile.
  const placeId = $derived(item ? model.placeOf(item, last?.tickId) : null);

  /** The same Undo as the toast's, so "Undone: …" shows here too. */
  function undo() {
    return model.undoLastTick();
  }
</script>

<section class="panel" aria-labelledby="{uid}-t">
  <h2 id="{uid}-t">Put away</h2>
  <p class="hint">Ticked items go straight into the pantry.</p>
  {#if last && item && standing}
    <div class="row">
      <span class="what">{last.name}{item.display ? `, ${item.display}` : ''}</span>
      {#if placeId !== null}
        <label>
          Where
          <select
            value={placeId}
            onchange={(event) => void model.putAway(item, Number(event.currentTarget.value))}
          >
            {#each model.copy.places as place (place.id)}
              <option value={place.id}>{place.name}</option>
            {/each}
          </select>
        </label>
      {/if}
    </div>
    <button type="button" class="link" onclick={() => void undo()}>Undo last tick</button>
  {/if}
</section>

<style>
  .panel {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-7) 18px;
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  h2 {
    font-size: 1rem;
    font-weight: var(--weight-extrabold);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-4);
    min-height: 44px;
    border-top: 1px solid var(--color-divider);
  }

  .what {
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
  }

  label {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  select {
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-md);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
  }

  .link {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }
</style>
