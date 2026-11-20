<script lang="ts">
  // "No portions left" for a "Leftovers here" drop or the one-day picker (cabledrawer 28 Oct): the
  // same two choices as the Leftovers on… sheet. Cook more makes the batch bigger (amounts and
  // the shopping list follow); Add anyway plans the meal for one serving and leaves the batch.
  import Button from '#lib/components/Button.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import type { PlanActions } from '#lib/planActions.js';
  import { dayWords } from '#lib/planDates.js';

  let { actions }: { actions: PlanActions } = $props();
  const model = $derived(actions.model);
  const asked = $derived(model.noPortions);

  const words = $derived(
    asked
      ? `No portions left for ${dayWords(asked.day)} ${model.slotName(asked.slotId).toLowerCase()}.`
      : ''
  );

  function choose(choice: 'cook_more' | 'add_anyway') {
    const now = model.noPortions;
    if (!now) return;
    model.noPortions = null;
    void model.drop(now.what, now.day, now.slotId, 'leftovers', choice);
  }

  const close = () => (model.noPortions = null);
</script>

{#if asked}
  <Sheet title="No portions left" testid="no-portions" onclose={close}>
    <p class="what">{asked.name}</p>
    <p role="alert">{words}</p>
    <div class="choices">
      <button
        type="button"
        class="more"
        disabled={actions.readonly}
        onclick={() => choose('cook_more')}
      >
        Cook more<small>A bigger batch · list updates</small>
      </button>
      <button
        type="button"
        class="anyway"
        disabled={actions.readonly}
        onclick={() => choose('add_anyway')}
      >
        Add anyway<small>Plans it; the batch stays the same</small>
      </button>
    </div>
    <Button quiet onclick={close}>Cancel</Button>
  </Sheet>
{/if}

<style>
  .what {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: break-word;
  }

  p[role='alert'] {
    margin: 0;
    padding: var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-tub-chip);
    color: var(--color-tub-chip-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .choices {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(9.5rem, 1fr));
    gap: var(--space-3);
  }

  .choices button {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 2px;
    min-height: 64px;
    padding: var(--space-3);
    border-radius: var(--radius-lg);
    font: inherit;
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
    cursor: pointer;
    text-align: center;
  }

  small {
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
  }

  .more {
    border: 2px solid var(--batch-4);
    background: var(--batch-4);
    color: var(--color-batch-on);
  }

  .anyway {
    border: 2px solid var(--color-check-border);
    background: var(--color-surface);
    color: var(--color-tub-chip-text);
  }

  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
