<script lang="ts">
  // The top of every page: an optional small line above (e.g. the date), the title and
  // an optional line under it. A page inside another (Recipes › Ingredients) gets a
  // back link on phones and a breadcrumb on desktop.
  // On phones it stays put while the page scrolls under it (UX principle 14), and holds
  // the round avatar and the cog, one link to Settings, which is where phones find the theme switch.
  import { resolve } from '$app/paths';
  import type { Snippet } from 'svelte';
  import { initial, session } from '#lib/session.svelte.js';
  import Breadcrumb from './Breadcrumb.svelte';
  import Icon from './Icon.svelte';

  let {
    title,
    overline,
    subtitle,
    count,
    parent,
    actions,
    dropActions = false
  }: {
    title: string;
    overline?: string;
    subtitle?: string;
    /**
     * The count line on the phone (F194, cabledrawer 9 Nov; mockups Dark-IngredientsHead08-Phone and
     * Dark-PantryHead08-Phone): the title row holds only the title and its round buttons, and
     * this goes on its own full-width line under it, so nothing squeezes it or the buttons. What
     * it holds is the page's own (Pantry's has Stocktake on the right, dropping under it when
     * the line is too narrow). Leave it out where the page has none.
     */
    count?: Snippet;
    /** The page this one sits under. */
    parent?: {
      href:
        | '/(app)/recipes'
        | '/(app)/recipes/drafts'
        | '/(app)/settings'
        | '/(app)/settings/sign-in'
        | '/(app)/settings/sign-in-everyone'
        | '/(app)/settings/people'
        | '/(app)/settings/your-data'
        | '/(app)/settings/about';
      label: string;
      /** A section of the parent (Settings' "sign-in"): the link lands there (L5). */
      section?: string;
    };
    /** The page's main button(s), beside the title ("+ Add to pantry"). */
    actions?: Snippet;
    /**
     * Let the actions drop under the title, at its left, when the two don't fit on one line,
     * instead of squeezing the title (cabledrawer 9 Nov, the Check header: the three import steps).
     */
    dropActions?: boolean;
  } = $props();

  // resolve()'s answer for the parent, plus its own ?section= (as Settings' phone list does).
  const parentHref = $derived(
    parent ? resolve(parent.href) + (parent.section ? `?section=${parent.section}` : '') : ''
  );
</script>

<svelte:head>
  <title>{title} · Mealwright</title>
</svelte:head>

<header class="page-header" class:has-count={!!count} class:drop={dropActions}>
  <div class="titles">
    {#if parent}
      <Breadcrumb href={parentHref} label={parent.label} current={title} />
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
    <span class="avatar" aria-hidden="true">{initial(session.me?.name ?? '')}</span>
    <span class="cog" aria-hidden="true"><Icon name="cog" size={24} stroke={2} /></span>
  </a>
  {#if count}<div class="count">{@render count()}</div>{/if}
</header>

<style>
  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    gap: var(--space-6);
  }

  /* With a count line: the title row is the first line (the title takes what the buttons leave, as
     before) and the count is its own full-width line under it. */
  .page-header.has-count {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    row-gap: var(--space-3);
  }

  .has-count .actions {
    grid-column: 2;
  }

  .has-count .settings {
    grid-column: 3;
  }

  .count {
    grid-column: 1 / -1;
    min-width: 0;
  }

  /* The actions go under the title, at its left, when there isn't room beside it. */
  .page-header.drop {
    flex-wrap: wrap;
    row-gap: var(--space-4);
  }

  .drop .actions {
    margin-left: 0;
    justify-content: flex-start;
  }

  .titles {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }

  /* The actions give way before Settings is pushed off the screen: when the row is too
     narrow (a 320 px phone at 200% text) they wrap, right-aligned, instead. */
  .actions {
    display: flex;
    flex: 0 1 auto;
    flex-wrap: wrap;
    justify-content: flex-end;
    align-items: center;
    gap: var(--space-4);
    min-width: 0;
    margin-left: auto;
  }

  /* Each action keeps its own size (the round + stays round); only the row wraps. */
  .actions > :global(*) {
    flex: none;
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
    overflow-wrap: break-word;
  }

  /* One link to Settings: the avatar circle and, beside it, the cog (cabledrawer 28 Oct, F2). */
  .settings {
    display: inline-flex;
    align-items: center;
    flex: none;
    gap: var(--space-3);
    text-decoration: none;
  }

  .avatar,
  .cog {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: var(--touch-target);
    border-radius: var(--radius-full);
  }

  .avatar {
    background: var(--color-avatar);
    color: var(--color-avatar-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
  }

  .cog {
    background: var(--color-fill);
    color: var(--color-text-soft);
  }

  .settings:hover .cog {
    color: var(--color-text);
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
    /* Desktop reaches Settings from the sidebar, and goes up with the breadcrumb. */
    .settings {
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
