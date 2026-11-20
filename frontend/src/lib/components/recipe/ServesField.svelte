<script lang="ts">
  // Serves: a − / + stepper from 1 to 99 that starts at 4 on a new recipe, and can be cleared
  // (for a batter or a powder: cabledrawer 19 Oct, questions 17 and 42).
  import Stepper from '#lib/components/Stepper.svelte';
  import '#lib/styles/fields.css';

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
  <Stepper
    what="servings"
    label="Serves"
    wide
    onless={less}
    onmore={more}
    lessOff={serves === null || serves <= 1}
    moreOff={serves === 99}
  >
    {serves ?? '–'}
  </Stepper>
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
