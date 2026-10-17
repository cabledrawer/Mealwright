<script lang="ts">
  // The app itself, for someone signed in. +layout.ts sends everyone else to sign in.
  import type { Snippet } from 'svelte';
  import { goto } from '$app/navigation';
  import { ApiError, saveTheme, setUnauthorizedHandler } from '$lib/api';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import TabBar from '$lib/components/TabBar.svelte';
  import Toast from '$lib/components/Toast.svelte';
  import { signInPath } from '$lib/session.svelte';
  import { theme } from '$lib/theme.svelte';
  import { handleUndoKey, undoHistory } from '$lib/undo.svelte';

  let { children }: { children: Snippet } = $props();

  $effect(() => {
    // A session that ends (expired, or signed out elsewhere) leads back to sign in,
    // and then back here.
    setUnauthorizedHandler(() => {
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- signInPath is always /sign-in plus a checked page
      void goto(signInPath(location.pathname + location.search), { invalidateAll: true });
    });
    // Theme changes follow the person to their other devices. Optimistic: the theme
    // changes straight away, and an ended session is handled above.
    theme.saveChangesWith((choice) => {
      saveTheme(choice).catch((error: unknown) => {
        if (!(error instanceof ApiError)) throw error;
      });
    });
    return () => {
      setUnauthorizedHandler(null);
      theme.saveChangesWith(null);
      // Signed out: this person's changes can't be undone from here any more.
      undoHistory.clear();
    };
  });
</script>

<!-- Ctrl+Z / Cmd+Z undoes your own last change (not while typing in a text box). -->
<svelte:window onkeydown={handleUndoKey} />

<a class="skip" href="#main">Skip to content</a>

<div class="shell">
  <div class="sidebar-slot"><Sidebar /></div>
  <main id="main" tabindex="-1">
    {@render children()}
  </main>
  <div class="tabbar-slot"><TabBar /></div>
</div>

<Toast />

<style>
  .skip {
    position: absolute;
    top: var(--space-4);
    left: var(--space-4);
    z-index: 100;
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-md);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
    transform: translateY(-200%);
  }

  .skip:focus {
    transform: none;
  }

  main {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
    min-width: 0;
    outline: none;
  }

  /* Phone: content between the fixed header and the fixed bottom tabs. */
  @media (max-width: 767px) {
    .sidebar-slot {
      display: none;
    }
    main {
      gap: 22px;
      padding: 0 var(--space-8) calc(var(--tabbar-height) + env(safe-area-inset-bottom) + 24px);
    }
  }

  /* Tablet and desktop: sidebar beside the page. */
  @media (min-width: 768px) {
    .shell {
      display: flex;
      align-items: flex-start;
    }
    .tabbar-slot {
      display: none;
    }
    main {
      flex: 1;
      padding: var(--space-10) var(--space-11);
    }
  }
</style>
