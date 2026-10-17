<script lang="ts">
  // The top of every page: an optional small line above (e.g. the date) and the title.
  // On phones it stays put while the page scrolls under it (UX principle 14), and holds
  // the round button to Settings, which is where phones find the theme switch.
  import { resolve } from '$app/paths';
  import { initial, session } from '$lib/session.svelte';

  let { title, overline }: { title: string; overline?: string } = $props();
</script>

<svelte:head>
  <title>{title} · Mealwright</title>
</svelte:head>

<header class="page-header">
  <div class="titles">
    {#if overline}<p class="overline">{overline}</p>{/if}
    <h1>{title}</h1>
  </div>
  <a
    class="settings"
    href={resolve('/settings')}
    aria-label="{session.me?.name ?? 'You'} · Settings"
    title="Settings"
  >
    {initial(session.me?.name ?? '')}
  </a>
</header>

<style>
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: var(--space-6);
  }

  .titles {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  .overline {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
  }

  h1 {
    font-size: var(--text-title);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
    line-height: 1.15;
    overflow-wrap: anywhere;
  }

  .settings {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: none;
    width: var(--touch-target);
    height: var(--touch-target);
    border-radius: var(--radius-full);
    background: var(--color-avatar);
    color: var(--color-avatar-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .settings:hover {
    color: var(--color-avatar-text);
  }

  @media (max-width: 767px) {
    .page-header {
      position: sticky;
      top: 0;
      z-index: 5;
      margin: 0 calc(-1 * var(--space-8));
      padding: max(var(--space-8), env(safe-area-inset-top)) var(--space-8) var(--space-6);
      background: var(--color-ground);
    }
  }

  @media (min-width: 768px) {
    h1 {
      font-size: var(--text-title-desktop);
    }
    /* Desktop reaches Settings from the sidebar. */
    .settings {
      display: none;
    }
  }
</style>
