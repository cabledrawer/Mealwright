<script lang="ts">
  // "Keep screen awake" (mockup Recipe; cabledrawer 19 Oct, question 32): the one Switch, off every
  // time the page opens. Not drawn at all where the browser can't do it.
  import { untrack } from 'svelte';
  import type { ScreenAwake } from '$lib/screenAwake.svelte';
  import Icon from './Icon.svelte';
  import Switch from './Switch.svelte';

  let { awake }: { awake: ScreenAwake } = $props();
  const id = $props.id();
  const supported = untrack(() => awake.supported);
</script>

{#if supported}
  <div class="row">
    <span class="what" id="{id}-label"><Icon name="light" size={18} />Keep screen awake</span>
    <Switch
      checked={awake.on}
      labelledby="{id}-label"
      describedby={awake.refused ? `${id}-refused` : undefined}
      onchange={(on) => void awake.set(on)}
    />
  </div>
  {#if awake.refused}
    <p class="refused" id="{id}-refused" role="status">Couldn’t keep the screen awake.</p>
  {/if}
{/if}

<style>
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: var(--touch-target);
    padding: 0 14px;
    border-radius: var(--radius-lg);
    background: var(--color-surface);
  }

  .what {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .refused {
    margin-top: calc(-1 * var(--space-4));
    padding: 0 14px;
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }
</style>
