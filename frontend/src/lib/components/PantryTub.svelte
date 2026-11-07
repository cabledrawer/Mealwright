<script lang="ts">
  // The tubs left of one batch in one place, as one row on the Pantry page (F131, 0.8):
  // "Lemon rice · 2 tubs · use by Tue". Tubs are put in a meal, eaten or moved on Today and
  // Plan, so this row only shows them where they are kept.
  import type { TubRow } from '#lib/client/types.js';
  import { whenWords } from '#lib/dates.js';

  let { tub, capital = false }: { tub: TubRow; capital?: boolean } = $props();

  const when = $derived(whenWords('use_by', tub.use_by, tub.days_left, { capital }));
</script>

<li class="tub">
  <span class="name">{tub.recipe_name}</span>
  <span class="amount">{tub.words}</span>
  <span class="date" class:late={when.tone === 'late'} class:soon={tub.use_soon && !when.passed}
    >{when.text}</span
  >
</li>

<style>
  .tub {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    column-gap: var(--space-4);
    align-items: center;
    min-height: 52px;
    padding: var(--space-3) 0;
    border-top: 1px solid var(--color-divider);
    list-style: none;
  }

  .name {
    grid-column: 1;
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .amount {
    grid-column: 1;
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .date {
    grid-column: 2;
    grid-row: 1 / span 2;
    max-width: 14rem;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    text-align: right;
  }

  .date.soon {
    padding: 3px 9px;
    border-radius: var(--radius-full);
    background: var(--color-use-soon-chip);
    color: var(--color-use-soon-text);
    font-weight: var(--weight-bold);
  }

  .date.late {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-bold);
  }

  /* A computer: one line, name · amount · date. */
  @media (min-width: 768px) {
    .tub {
      grid-template-columns: minmax(0, 1fr) auto auto;
      min-height: var(--touch-target);
    }

    .name {
      grid-column: auto;
      overflow: hidden;
      font-size: var(--text-base);
      font-weight: var(--weight-semibold);
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .amount {
      grid-column: auto;
      font-size: var(--text-sm);
      white-space: nowrap;
    }

    .date {
      grid-column: auto;
      grid-row: auto;
      font-size: var(--text-xs);
      white-space: nowrap;
    }
  }
</style>
