<script lang="ts">
  // Auto · Light · Dark, always in plain sight (UX principle 13).
  //   sidebar: three buttons with icons, at the foot of the desktop sidebar
  //   pill:    three buttons, in Settings (and the phone's way in)
  //   cycle:   one button that steps through the three, for the collapsed sidebar
  import Icon from './Icon.svelte';
  import Segmented from './Segmented.svelte';
  import { THEME_CHOICES, THEME_HINTS, THEME_LABELS, nextTheme, theme } from '#lib/theme.svelte.js';

  let { variant = 'sidebar' }: { variant?: 'sidebar' | 'pill' | 'cycle' } = $props();

  const cycleLabel = $derived(
    `Theme: ${THEME_LABELS[theme.choice]}. Switch to ${THEME_LABELS[nextTheme(theme.choice)]}`
  );
</script>

{#if variant === 'cycle'}
  <button
    type="button"
    class="cycle"
    aria-label={cycleLabel}
    title="Theme: Auto · Light · Dark"
    onclick={() => theme.cycle()}
  >
    <Icon name={theme.choice} size={20} stroke={2.2} />
  </button>
{:else}
  <Segmented
    options={THEME_CHOICES.map((choice) => ({
      value: choice,
      label: THEME_LABELS[choice],
      title: THEME_HINTS[choice]
    }))}
    value={theme.choice}
    onchange={(choice) => theme.set(choice)}
    label="Theme"
    variant={variant === 'pill' ? 'pill' : 'tray'}
  >
    {#snippet segment(option)}
      {#if variant === 'sidebar'}<Icon name={option.value} size={15} stroke={2.2} />{/if}
      {option.label}
    {/snippet}
  </Segmented>
{/if}

<style>
  .cycle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text-soft);
    cursor: pointer;
  }
</style>
