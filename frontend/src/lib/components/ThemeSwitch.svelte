<script lang="ts">
  // Auto · Light · Dark, always in plain sight (UX principle 13).
  //   sidebar: three buttons with icons, at the foot of the desktop sidebar
  //   pill:    three buttons, in Settings (and the phone's way in)
  //   cycle:   one button that steps through the three, for the collapsed sidebar
  import Icon from './Icon.svelte';
  import { THEME_CHOICES, THEME_HINTS, THEME_LABELS, nextTheme, theme } from '$lib/theme.svelte';

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
  <div class="group {variant}" role="group" aria-label="Theme">
    {#each THEME_CHOICES as choice (choice)}
      <button
        type="button"
        aria-pressed={theme.choice === choice}
        title={THEME_HINTS[choice]}
        onclick={() => theme.set(choice)}
      >
        {#if variant === 'sidebar'}<Icon name={choice} size={15} stroke={2.2} />{/if}
        {THEME_LABELS[choice]}
      </button>
    {/each}
  </div>
{/if}

<style>
  .group {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: var(--space-1);
    padding: 3px;
    background: var(--color-fill);
    border-radius: var(--radius-md);
  }

  .group button {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    min-height: 34px;
    padding: 0 var(--space-2);
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-semibold);
    cursor: pointer;
  }

  .group button[aria-pressed='true'] {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-bold);
  }

  .pill {
    display: inline-flex;
    gap: 0;
    background: var(--color-fill-strong);
    border-radius: var(--radius-full);
  }

  .pill button {
    min-height: 32px;
    padding: 0 var(--space-6);
    border-radius: var(--radius-full);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  :global([data-theme='dark']) .pill button[aria-pressed='true'] {
    background: var(--color-surface);
  }

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

  /* Bigger targets for fingers (touch screens, tablets). */
  @media (pointer: coarse) {
    .group button,
    .pill button {
      min-height: var(--touch-target);
    }
  }
</style>
