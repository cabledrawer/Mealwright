<script lang="ts">
  // Settings (cabledrawer 15 Nov, F252; mockups Dark-Settings2-Desktop and -Phone). On a computer
  // the main menu folds to its icons (Sidebar does that on any /settings address) and the grouped
  // list of Settings sits beside the page, the open item marked. On the phone /settings is that
  // list and each row opens its own page (the page draws the list; this layout draws nothing but
  // the page). The whole Household group is for admins only: a member isn't shown it, and an
  // address in it shows "Only admins can change this." instead of the page, so nothing of it is
  // loaded. The server still refuses a member's change.
  import { onDestroy, onMount, untrack, type Snippet } from 'svelte';
  import { page } from '$app/state';
  import { resolve } from '$app/paths';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import { session } from '#lib/session.svelte.js';
  import { updates } from '#lib/updates.svelte.js';
  import { UPDATE_AVAILABLE } from '#lib/aboutWords.js';
  import FinishRing from './FinishRing.svelte';
  import { FINISH_SETUP_WORDS, ringWords } from './finishRing.js';
  import { settingsKnown } from './finishSetup.svelte.js';
  import { GROUPS, adminOnly, itemAtRoute, itemsFor } from './items.js';

  let { children }: { children: Snippet } = $props();

  const admin = $derived(session.me?.role === 'admin');
  const here = $derived(itemAtRoute(page.route.id));
  /** An address in the admins-only group, opened by someone who isn't one. */
  const refused = $derived(!!here && adminOnly(here) && !admin);
  const shown = $derived(itemsFor(admin));
  const groups = $derived(
    GROUPS.map((group) => ({
      ...group,
      items: shown.filter((item) => item.group === group.name)
    })).filter((group) => group.items.length > 0)
  );

  const FINISH_SETUP = 'Finish setup';
  const finishSetup = $derived(admin && settingsKnown.onboardingDone === false);

  // Read at the start and each time another page of Settings opens (so the ring is up to date
  // after a step is done).
  $effect(() => {
    void page.url.pathname;
    untrack(() => void settingsKnown.load(admin));
  });
  onMount(() => {
    // An admin sees "Update available" by About once a check has found a newer version.
    if (admin) void updates.load();
  });
  onDestroy(() => settingsKnown.forget());
</script>

<div class="layout">
  <nav class="list" aria-label="Settings">
    <h2 class="list-title">Settings</h2>
    {#if finishSetup}
      <a class="finish" href={resolve('/(app)/onboarding')}
        ><span class="finish-ring"><FinishRing done={settingsKnown.done} /></span><span
          class="finish-text"
          >{FINISH_SETUP}<span class="finish-words">{FINISH_SETUP_WORDS}</span></span
        ><span class="finish-count">{ringWords(settingsKnown.done)}</span></a
      >
    {/if}
    {#each groups as group (group.name)}
      <div class="group" role="group" aria-label={group.label}>
        <div class="group-name">
          {group.name}{#if group.adminOnly}<span class="adm">admins only</span>{/if}
        </div>
        {#each group.items as item (item.id)}
          <a href={resolve(item.route)} aria-current={here?.id === item.id ? 'page' : undefined}
            >{item.label}
            {#if item.id === 'about' && updates.available}<span class="badge"
                >{UPDATE_AVAILABLE}</span
              >{/if}</a
          >
        {/each}
      </div>
    {/each}
  </nav>
  <div class="content">
    {#if refused && here}
      <PageHeader title={here.label} parent={{ href: '/(app)/settings', label: 'Settings' }} />
      <p class="admins-only" role="status">Only admins can change this.</p>
    {:else}
      {@render children()}
    {/if}
  </div>
</div>

<style>
  .layout {
    display: contents;
  }

  .content {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
    min-width: 0;
  }

  /* The phone's list is the /settings page itself. */
  .list {
    display: none;
  }

  .admins-only {
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    font-size: var(--text-lg);
    font-weight: var(--weight-semibold);
  }

  @media (max-width: 767px) {
    .content {
      gap: 22px;
    }
  }

  @media (min-width: 768px) {
    .layout {
      display: grid;
      grid-template-columns: 240px minmax(0, 760px);
      gap: 28px;
      align-items: start;
    }

    .list {
      position: sticky;
      top: var(--space-7);
      display: flex;
      flex-direction: column;
      gap: var(--space-1);
    }

    .list-title {
      margin: 0 0 var(--space-4);
      padding: 0 var(--space-6);
      font-size: var(--text-title-desktop);
      font-weight: var(--weight-extrabold);
      letter-spacing: var(--tracking-tight);
    }
  }

  .group {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .group-name {
    margin-top: var(--space-5);
    padding: 0 var(--space-6);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .adm {
    margin-left: var(--space-4);
    font-weight: var(--weight-medium);
    letter-spacing: 0;
    text-transform: none;
  }

  .group a {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border-radius: var(--radius-field);
    color: var(--color-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .group a:hover {
    background: var(--color-fill);
  }

  .group a[aria-current='page'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  /* "Finish setup" at the top of the list, for an admin who skipped set-up (cabledrawer 12 Nov). */
  .finish {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    padding: var(--space-3) var(--space-6);
    border-radius: var(--radius-field);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  .finish-ring {
    display: grid;
    flex: none;
    place-items: center;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-md);
    background: var(--color-caution);
    color: var(--color-caution-text);
  }

  .finish-text {
    flex: 1;
    min-width: 0;
  }

  .finish-count {
    flex: none;
    font-size: var(--text-sm);
    font-weight: var(--weight-regular);
    white-space: nowrap;
  }

  .finish-words {
    display: block;
    font-size: var(--text-sm);
    font-weight: var(--weight-regular);
  }

  .badge {
    flex: none;
    margin-left: var(--space-3);
    padding: 2px var(--space-3);
    border-radius: var(--radius-full);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.02em;
    white-space: nowrap;
  }

  .group a[aria-current='page'] .badge {
    background: var(--color-surface);
  }
</style>
