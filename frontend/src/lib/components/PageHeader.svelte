<script lang="ts">
  // The top of every page: an optional small line above (e.g. the date), the title and
  // an optional line under it. A page inside another (Recipes › Ingredients) gets a
  // back link on phones and a breadcrumb on desktop.
  // On phones it stays put while the page scrolls under it (UX principle 14), and holds
  // the round button to Settings, which is where phones find the theme switch.
  import { resolve } from '$app/paths';
  import type { Snippet } from 'svelte';
  import { initial, session } from '$lib/session.svelte';
  import Icon from './Icon.svelte';

  let {
    title,
    overline,
    subtitle,
    parent,
    actions
  }: {
    title: string;
    overline?: string;
    subtitle?: string;
    /** The page this one sits under. */
    parent?: {
      href: '/(app)/recipes' | '/(app)/recipes/drafts' | '/(app)/settings';
      label: string;
    };
    /** The page's main button(s), beside the title ("+ Add to pantry"). */
    actions?: Snippet;
  } = $props();
</script>

<svelte:head>
  <title>{title} · Mealwright</title>
</svelte:head>

<header class="page-header">
  <div class="titles">
    {#if parent}
      <a class="back" href={resolve(parent.href)}>
        <Icon name="back" size={18} stroke={2.4} />{parent.label}
      </a>
      <nav class="crumbs" aria-label="Breadcrumb">
        <a href={resolve(parent.href)}>{parent.label}</a>
        <span class="sep" aria-hidden="true">›</span>
        <span aria-current="page">{title}</span>
      </nav>
    {/if}
    {#if overline}<p class="overline">{overline}</p>{/if}
    <h1>{title}</h1>
    {#if subtitle}<p class="subtitle">{subtitle}</p>{/if}
  </div>
  {#if actions}<div class="actions">{@render actions()}</div>{/if}
  <a
    class="settings"
    href={resolve('/(app)/settings')}
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

  .actions {
    display: flex;
    flex: none;
    align-items: center;
    gap: var(--space-4);
    margin-left: auto;
  }

  .back {
    display: flex;
    align-items: center;
    align-self: flex-start;
    gap: var(--space-2);
    min-height: var(--touch-target);
    margin-left: calc(-1 * var(--space-2));
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .crumbs {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .crumbs a {
    text-decoration: none;
  }

  .crumbs .sep,
  .crumbs [aria-current] {
    color: var(--color-text-muted);
  }

  .subtitle {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-medium);
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
    word-spacing: normal;
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
    .crumbs {
      display: none;
    }
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
    /* Desktop reaches Settings from the sidebar, and goes up with the breadcrumb. */
    .settings,
    .back {
      display: none;
    }
    .titles {
      gap: var(--space-3);
    }
    .overline + h1,
    h1 + .subtitle {
      margin-top: calc(-1 * var(--space-2));
    }
  }
</style>
