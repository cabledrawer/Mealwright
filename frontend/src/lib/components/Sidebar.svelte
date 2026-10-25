<script lang="ts">
  // The desktop and tablet sidebar. Expanded: logo, the five pages (Recipes as a
  // tree: All recipes · Drafts · Ingredients), the theme switch and Settings. Collapsed: icons only, with tooltips (Recipes opens a small pop-out with its pages), a
  // single theme button, and a button to expand it again. Not shown on phones (they get
  // the bottom tabs).
  import { resolve } from '$app/paths';
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import { drafts } from '#lib/drafts.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { PAGES, RECIPES_PAGES, appRoute, isCurrent, isCurrentRecipesPage } from '#lib/nav.js';
  import { initial, session } from '#lib/session.svelte.js';
  import { sidebar } from '#lib/sidebar.svelte.js';
  import ConnectionStatus from './ConnectionStatus.svelte';
  import Icon from './Icon.svelte';
  import Logo from './Logo.svelte';
  import RecipesPopout from './RecipesPopout.svelte';
  import ThemeSwitch from './ThemeSwitch.svelte';

  const settingsCurrent = $derived(page.url.pathname.startsWith('/settings'));

  // The number beside Drafts (mockup Drafts05-Desktop). It is asked for once when the app opens
  // and again when the connection comes back; changes made here update it at once. Another
  // person's drafts show on the next look at Drafts. Offline, or if the server can't say, there
  // is no number rather than a guess.
  let seen = network.backAgain;
  onMount(() => {
    if (!network.offline) void drafts.load();
  });
  $effect(() => {
    const again = network.backAgain;
    if (again !== seen) {
      seen = again;
      void drafts.load();
    }
  });
</script>

<aside class="sidebar" class:collapsed={sidebar.collapsed} aria-label="Sidebar">
  <div class="top">
    <a class="brand" href={resolve('/(app)')} aria-label="Mealwright, Today">
      <Logo size={sidebar.collapsed ? 40 : 32} />
      {#if !sidebar.collapsed}<span class="wordmark">Mealwright</span>{/if}
    </a>
    <button
      type="button"
      class="toggle"
      aria-label={sidebar.collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      aria-expanded={!sidebar.collapsed}
      title={sidebar.collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      onclick={() => sidebar.toggle()}
    >
      <Icon name={sidebar.collapsed ? 'expand' : 'collapse'} size={18} stroke={2.2} />
    </button>
  </div>

  <nav aria-label="Main">
    {#each PAGES as item (item.href)}
      {@const current = isCurrent(item, page.url.pathname)}
      {@const tree = item.href === '/recipes' && !sidebar.collapsed}
      <!-- With the tree showing, the page under Recipes is marked, and Recipes shows
           only that you’re somewhere inside it. -->
      {#if item.href === '/recipes' && sidebar.collapsed}
        <!-- Collapsed, Recipes opens a small pop-out with its pages. -->
        <RecipesPopout pathname={page.url.pathname} {current} />
      {:else}
        <a
          href={resolve(appRoute(item.href))}
          class:section={tree && current}
          aria-current={current && !tree ? 'page' : undefined}
          aria-label={sidebar.collapsed ? item.label : undefined}
          title={sidebar.collapsed ? item.label : undefined}
        >
          <Icon name={item.icon} size={sidebar.collapsed ? 22 : 20} />
          {#if !sidebar.collapsed}<span class="label">{item.label}</span>{/if}
          {#if tree}<Icon name="chevron-down" size={16} stroke={2.4} />{/if}
        </a>
      {/if}
      {#if tree}
        <div class="tree" role="group" aria-label="Recipes">
          {#each RECIPES_PAGES as sub (sub.href)}
            <a
              href={resolve(appRoute(sub.href))}
              aria-current={isCurrentRecipesPage(sub, page.url.pathname) ? 'page' : undefined}
              >{sub.label}{#if sub.href === '/recipes/drafts' && drafts.count}<span class="count"
                  >{drafts.count}</span
                >{/if}</a
            >
          {/each}
        </div>
      {/if}
    {/each}
  </nav>

  <div class="foot">
    <ConnectionStatus layout={sidebar.collapsed ? 'dot' : 'desktop'} />
    <ThemeSwitch variant={sidebar.collapsed ? 'cycle' : 'sidebar'} />
    <a
      class="settings"
      href={resolve('/(app)/settings')}
      aria-current={settingsCurrent ? 'page' : undefined}
      aria-label={`${session.me?.name ?? 'You'} · Settings`}
      title="Settings"
    >
      <span class="avatar" aria-hidden="true">{initial(session.me?.name ?? '')}</span>
      {#if !sidebar.collapsed}
        <span class="who">
          <span class="name">{session.me?.name}</span>
          <span class="settings-label">Settings</span>
        </span>
      {/if}
    </a>
  </div>
</aside>

<style>
  .sidebar {
    position: sticky;
    top: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    width: var(--sidebar-width);
    height: 100dvh;
    padding: var(--space-9) var(--space-7);
    overflow-y: auto;
    scrollbar-width: none;
    background: var(--color-chrome);
    border-right: 1px solid var(--color-border);
  }

  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    padding-left: var(--space-4);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: var(--touch-target);
    color: var(--color-text);
    text-decoration: none;
  }

  .wordmark {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
    word-spacing: normal;
  }

  .toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--touch-target);
    height: 34px;
    padding: 0;
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text-soft);
    cursor: pointer;
  }

  nav {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  nav a {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border-radius: var(--radius-md);
    color: var(--color-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
    text-decoration: none;
  }

  nav a:hover {
    background: var(--color-fill);
    color: var(--color-text);
  }

  nav a[aria-current='page'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
  }

  .label {
    flex: 1;
  }

  /* Recipes, while one of its pages is open. */
  nav a.section {
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
  }

  .tree {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin: var(--space-1) 0 0 21px;
    padding-left: var(--space-5);
    border-left: 2px solid var(--color-border);
  }

  .tree a {
    padding: 0 var(--space-5);
    border-radius: 10px;
    color: var(--color-text-soft);
    font-size: var(--text-base);
  }

  .tree a:has(.count) {
    justify-content: space-between;
  }

  .count {
    font-weight: var(--weight-bold);
  }

  .foot {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    margin-top: auto;
  }

  .settings {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: var(--touch-target);
    padding: var(--space-3) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-ground);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .settings:hover,
  .settings[aria-current='page'] {
    color: var(--color-text);
    background: var(--color-fill);
  }

  .avatar {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-full);
    flex: none;
    background: var(--color-avatar);
    color: var(--color-avatar-text);
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
  }

  .who {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }

  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .settings-label {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  /* Collapsed: a 72 px strip of icons. */
  .collapsed {
    width: var(--sidebar-collapsed-width);
    align-items: center;
    gap: var(--space-6);
    padding: 18px var(--space-5);
  }

  .collapsed .top {
    flex-direction: column;
    gap: var(--space-6);
    padding-left: 0;
  }

  .collapsed nav {
    align-items: center;
    gap: var(--space-3);
  }

  .collapsed nav a {
    justify-content: center;
    width: 48px;
    height: 48px;
    padding: 0;
    border-radius: var(--radius-lg);
    color: var(--color-text-soft);
  }

  .collapsed .foot {
    align-items: center;
  }

  .collapsed .settings {
    justify-content: center;
    width: var(--touch-target);
    padding: 0;
    background: transparent;
  }

  @media (pointer: coarse) {
    .toggle {
      height: var(--touch-target);
    }
  }
</style>
