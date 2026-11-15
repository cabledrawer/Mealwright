<script lang="ts">
  // The app itself, for someone signed in. +layout.ts sends everyone else to sign in.
  import { untrack, type Snippet } from 'svelte';
  import { goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { ApiError, cantReach, saveTheme, setUnauthorizedHandler } from '#lib/api.js';
  import Sidebar from '#lib/components/Sidebar.svelte';
  import TabBar from '#lib/components/TabBar.svelte';
  import ConnectionStatus from '#lib/components/ConnectionStatus.svelte';
  import Toast from '#lib/components/Toast.svelte';
  import IngredientSheet from '#lib/components/IngredientSheet.svelte';
  import AskOnce from '#lib/components/AskOnce.svelte';
  import { lastOwnChange } from '#lib/client/changes.js';
  import { settleHousehold } from '#lib/client/household.js';
  import { drafts } from '#lib/drafts.svelte.js';
  import { forgetAll } from '#lib/forgetAll.js';
  import { forgetToday } from '#lib/today.svelte.js';
  import { askAgain } from '#lib/offline/opening.js';
  import { onWipedElsewhere } from '#lib/offline/otherTabs.js';
  import { askToKeepDataHere } from '#lib/offline/persist.js';
  import { live } from '#lib/live.svelte.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import { optionalAsk } from '#lib/optionalAsk.svelte.js';
  import { network } from '#lib/network.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { forgetLoaded } from '#lib/forgetWhenLoaded.js';
  import { updates } from '#lib/updates.svelte.js';
  import { session } from '#lib/session.svelte.js';
  import { shoppingSync } from '#lib/shopping/sync.svelte.js';
  import { starterPacks } from '#lib/starterPacks.svelte.js';
  import { signInPath } from '#lib/session.svelte.js';
  import { theme } from '#lib/theme.svelte.js';
  import { toasts } from '#lib/toast.svelte.js';
  import { handleUndoKey, undoHistory } from '#lib/undo.svelte.js';
  import { whosThis } from '#lib/whosThis.svelte.js';

  let { children }: { children: Snippet } = $props();
  /** Another tab wiped this browser: nothing of the household shows here any more. */
  let wiped = $state(false);

  // Live updates, the connection bar and the offline queue, for as long as someone is signed
  // in. Waiting changes are sent when the app opens, comes to the foreground or the browser
  // says it's online (shoppingSync.watch), when the connection comes back or on "Try now"
  // (network), and when the event stream reconnects (live's hello). Sync protocol 11.3.
  //
  // Signing out (or a different login starting clean) in another tab wipes this browser.
  // This tab then clears itself at once, stops the stream and sending, never makes the
  // database again, and goes to sign in (cabledrawer 18 Oct; otherTabs.ts).
  $effect(() => {
    // Opened from this device before the server said who is signed in (a slow or offline
    // start): it's asked again once it can be reached (askAgain, opening.ts).
    const stopNetwork = network.start(() => {
      live.reconnect();
      void theme.flush();
      void shoppingSync.tryAgain();
      void askAgain();
    });
    const stopLive = live.start(() => {
      void theme.flush();
      void shoppingSync.send();
      void askAgain();
    });
    const stopSync = shoppingSync.watch();
    void shoppingSync.start();
    let stopped = false;
    const stop = () => {
      if (stopped) return;
      stopped = true;
      stopSync();
      stopLive();
      stopNetwork();
    };
    const stopListening = onWipedElsewhere(() => {
      wiped = true;
      stop();
      session.me = null;
      shoppingSync.forget();
      placesAndShops.forget();
      forgetLoaded('privacy');
      updates.forget();
      drafts.forget();
      forgetToday();
      undoHistory.clear();
      toasts.dismiss();
      forgetAll();
      try {
        sessionStorage.clear();
      } catch {
        // Storage blocked: nothing kept there.
      }
      void goto(resolve('/(auth)/sign-in'), { replace: true, refreshAll: true });
    });
    return () => {
      stopListening();
      stop();
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
      // Nobody signed in here any more: this tab (or another) is signing out, and goes to
      // the sign-in page by itself, without "come back to this page".
      if (!session.me) return;
      // eslint-disable-next-line svelte/no-navigation-without-resolve -- signInPath is always /sign-in plus a checked page
      void goto(signInPath(location.pathname + location.search), { refreshAll: true });
    });
    // Theme changes follow the person to their other devices. Optimistic: the theme
    // changes straight away, and an ended session is handled above.
    // A pick the server hasn't confirmed stays on this device and is sent again when the
    // connection is back (theme.flush: now, and from the network and live callbacks above).
    theme.saveChangesWith(
      async (choice) => {
        try {
          await saveTheme(choice);
          return true;
        } catch (error) {
          if (!(error instanceof ApiError)) throw error;
          // No answer, a server fault or the session has ended: keep it, and send it later.
          // Any other refusal won't change by asking again.
          return !(cantReach(error) || error.status === 401 || error.status >= 500);
        }
      },
      untrack(() => session.me?.id ?? null)
    );
    void theme.flush();
    // A shared login asks "Who's this?" when nobody is picked on this device.
    void whosThis.check().catch(() => {});
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
      whosThis.forget();
    };
  });
</script>

<!-- Ctrl+Z / Cmd+Z undoes your own last change (not while typing in a text box). A shared
     login notes each use, to ask "Who's this?" again after a while without one. -->
<svelte:window
  onkeydown={(event) => {
    whosThis.used();
    handleUndoKey(event);
  }}
  onpointerdown={() => whosThis.used()}
/>

{#if !wiped}
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
  <!-- Which optional ingredients a meal will use (R3); fetched when first asked (size limit). -->
  <!-- Which way of cooking a recipe the meal uses (M2); fetched when first asked too. -->
  {#if optionalAsk.methodOpen}
    {#await import('#lib/components/plan/PlanMethod.svelte') then { default: PlanMethod }}
      <PlanMethod />
    {/await}
  {/if}
  {#if optionalAsk.current}
    {#await import('#lib/components/plan/PlanOptional.svelte') then { default: PlanOptional }}
      <PlanOptional />
    {/await}
  {/if}
  <!-- When a recipe's long wait will be started (M3); fetched when first asked too. -->
  {#if optionalAsk.startOpen}
    {#await import('#lib/components/plan/PlanStart.svelte') then { default: PlanStart }}
      <PlanStart />
    {/await}
  {/if}
  <!-- "Who's this?" on a shared login (0.9 A1); fetched only there. -->
  {#if session.me?.shared}
    {#await import('#lib/components/people/WhosThis.svelte') then { default: WhosThis }}
      <WhosThis />
    {/await}
  {/if}
  <!-- "Pantry keeps it by" (a new ingredient); fetched when first asked, then kept so closing
       it hands focus back as before (size limit). -->
  {#if newIngredient.wanted}
    {#await import('#lib/components/NewIngredient.svelte') then { default: NewIngredient }}
      <NewIngredient />
    {/await}
  {/if}
  <!-- "Add a starter pack" (R4); fetched when first opened, then kept so closing it
       hands focus back as before (size limit). -->
  {#if starterPacks.wanted}
    {#await import('#lib/components/StarterPacks.svelte') then { default: StarterPacks }}
      <StarterPacks />
    {/await}
  {/if}
  <Toast />
{/if}

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

  /* Phone: content between the fixed header and the fixed bottom tabs. The toast floats just
     above the tabs, so the foot of the page leaves room for it too (a long list’s last
     button, "In the trolley", must stay tappable while a toast is up). */
  @media (max-width: 767px) {
    .sidebar-slot {
      display: none;
    }
    main {
      --toast-room: 96px;
      gap: 22px;
      padding: 0 var(--space-8)
        calc(
          var(--tabbar-height) + env(safe-area-inset-bottom) + var(--offline-offset) + 24px +
            var(--toast-room)
        );
    }
  }

  /* The recipe editor is a full page of its own on a phone: no bottom tabs (it has its own bar
     with Cancel and Save), so nothing is lifted above them either. */
  @media (max-width: 767px) {
    :global(html[data-full-page]) {
      --tabbar-height: 0px;
    }
    :global(html[data-full-page]) .tabbar-slot {
      display: none;
    }
  }

  /* Tablet and desktop: sidebar beside the page. */
  @media (min-width: 768px) {
    .shell {
      display: flex;
      align-items: flex-start;
    }
    /* The sidebar (and its theme switch) stays put while the page scrolls. Being sticky makes it
       a layer of its own, so it sits above the page: otherwise the Recipes pop-out, which opens
       out over the page, would be painted under the page's rows (and a click would hit a row). */
    .sidebar-slot {
      position: sticky;
      top: 0;
      z-index: 20;
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
