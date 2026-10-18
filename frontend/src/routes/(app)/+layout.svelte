<script lang="ts">
  // The app itself, for someone signed in. +layout.ts sends everyone else to sign in.
  import type { Snippet } from 'svelte';
  import { goto } from '$app/navigation';
  import { ApiError, saveTheme, setUnauthorizedHandler } from '$lib/api';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import TabBar from '$lib/components/TabBar.svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import Toast from '$lib/components/Toast.svelte';
  import IngredientSheet from '$lib/components/IngredientSheet.svelte';
  import AskOnce from '$lib/components/AskOnce.svelte';
  import NewIngredient from '$lib/components/NewIngredient.svelte';
  import { lastOwnChange } from '$lib/client/changes';
  import { settleHousehold } from '$lib/client/household';
  import { askToKeepDataHere } from '$lib/offline/persist';
  import { live } from '$lib/live.svelte';
  import { network } from '$lib/network.svelte';
  import { session } from '$lib/session.svelte';
  import { shoppingSync } from '$lib/shopping/sync.svelte';
  import { signInPath } from '$lib/session.svelte';
  import { theme } from '$lib/theme.svelte';
  import { handleUndoKey, undoHistory } from '$lib/undo.svelte';

  let { children }: { children: Snippet } = $props();

  // Live updates, the connection bar and the offline queue, for as long as someone is signed
  // in. Waiting changes are sent when the app opens, comes to the foreground or the browser
  // says it's online (shoppingSync.watch), when the connection comes back or on "Try now"
  // (network), and when the event stream reconnects (live's hello). Sync protocol 11.3.
  $effect(() => {
    const stopNetwork = network.start(() => {
      live.reconnect();
      void shoppingSync.tryAgain();
    });
    const stopLive = live.start(() => void shoppingSync.send());
    const stopSync = shoppingSync.watch();
    void shoppingSync.start();
    return () => {
      stopSync();
      stopLive();
      stopNetwork();
    };
  });

  // Installed to the home screen: ask the browser to keep our stored data (once, quietly).
  $effect(() => {
    void askToKeepDataHere();
  });

  // The phone's offline bar lifts the toast and the page's end above the bottom tabs.
  $effect(() => {
    document.documentElement.toggleAttribute('data-offline', network.offline);
    return () => document.documentElement.removeAttribute('data-offline');
  });

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
    // Ctrl+Z after a reload: your latest change, from the server.
    undoHistory.fallback = lastOwnChange;
    // First run: tell the server the household's time zone and cup size (admins, once).
    if (session.me) settleHousehold(session.me).catch(() => {});
    return () => {
      undoHistory.fallback = null;
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
  <div class="tabbar-slot">
    <ConnectionStatus layout="phone" />
    <TabBar />
  </div>
</div>

<!-- The one ingredient editor, opened from anywhere with ingredientEditor.open(). -->
<IngredientSheet />
<AskOnce />
<NewIngredient />
<Toast />

<style>
  .skip {
    position: absolute;
    top: var(--space-4);
    left: var(--space-4);
    z-index: 100;
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
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
      padding: 0 var(--space-8)
        calc(var(--tabbar-height) + env(safe-area-inset-bottom) + var(--offline-offset) + 24px);
    }
  }

  /* Tablet and desktop: sidebar beside the page. */
  @media (min-width: 768px) {
    .shell {
      display: flex;
      align-items: flex-start;
    }
    /* The sidebar (and its theme switch) stays put while the page scrolls. */
    .sidebar-slot {
      position: sticky;
      top: 0;
      align-self: flex-start;
      height: 100dvh;
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
