<script lang="ts">
  // "Keep screen awake", now in Cook mode (spec "Cook mode timers"; cabledrawer 31 Oct): the one Switch.
  // Where the browser can't do it the switch is greyed and says why, instead of vanishing. When the
  // browser says no, Cook mode shows "Couldn't keep the screen awake." under its progress bar (F148).
  import { untrack } from 'svelte';
  import type { ScreenAwake } from '#lib/screenAwake.svelte.js';
  import Icon from './Icon.svelte';
  import Switch from './Switch.svelte';

  let { awake }: { awake: ScreenAwake } = $props();
  const id = $props.id();
  const supported = untrack(() => awake.supported);
</script>

<div class="row" class:grey={!supported}>
  <span class="what" id="{id}-label"><Icon name="light" size={18} />Keep screen awake</span>
  <Switch
    checked={awake.on}
    disabled={!supported}
    labelledby="{id}-label"
    describedby={!supported ? `${id}-cant` : undefined}
    onchange={(on) => void awake.set(on)}
  />
</div>
{#if !supported}
  <p class="refused" id="{id}-cant">This browser can’t keep the screen on</p>
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
    background: var(--reading-chip, var(--color-surface));
  }

  .grey .what {
    color: var(--color-text-muted);
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
