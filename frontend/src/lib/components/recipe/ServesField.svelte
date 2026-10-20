<script lang="ts">
  // Serves: a − / + stepper from 1 to 99 that starts at 4 on a new recipe, and can be cleared
  // (for a batter or a powder: cabledrawer 19 Oct, questions 17 and 42).
  import '$lib/styles/fields.css';

  let { serves = $bindable(), error }: { serves: number | null; error?: string } = $props();

  const uid = $props.id();

  const less = () => {
    if (serves !== null && serves > 1) serves -= 1;
  };
  const more = () => {
    serves = serves === null ? 4 : Math.min(99, serves + 1);
  };
</script>

<div class="serves">
  <span id="{uid}-label" class="mw-label">Serves</span>
  <div class="stepper" role="group" aria-labelledby="{uid}-label">
    <button
      type="button"
      aria-label="Fewer servings"
      disabled={serves === null || serves <= 1}
      onclick={less}>−</button
    >
    <output class="value" aria-live="polite">{serves ?? '–'}</output>
    <button type="button" aria-label="More servings" disabled={serves === 99} onclick={more}
      >+</button
    >
  </div>
  {#if serves !== null}
    <button type="button" class="clear" onclick={() => (serves = null)}>
      Clear (for a batter or a powder)
    </button>
  {/if}
  {#if error}<p class="mw-error">{error}</p>{/if}
</div>

<style>
  .serves {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    min-width: 0;
  }

  .stepper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    min-height: 52px;
    padding: var(--space-2);
    border-radius: var(--radius-md);
    background: var(--color-fill);
  }

  button:not(.clear) {
    flex: none;
    width: var(--touch-target);
    height: var(--touch-target);
    border: none;
    border-radius: 10px;
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-bold) 1.125rem var(--font-ui);
    cursor: pointer;
  }

  button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .value {
    color: var(--color-text);
    font-size: 1rem;
    font-weight: var(--weight-extrabold);
  }

  .clear {
    align-self: flex-start;
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    text-align: left;
    cursor: pointer;
  }
</style>
