<script lang="ts">
  import '@fontsource-variable/plus-jakarta-sans';
  import '@fontsource-variable/newsreader';
  import '$lib/styles/tokens.css';
  import '$lib/styles/base.css';

  import type { Snippet } from 'svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import TabBar from '$lib/components/TabBar.svelte';
  import { theme } from '$lib/theme.svelte';

  let { children }: { children: Snippet } = $props();

  $effect(() => theme.start());
</script>

<a class="skip" href="#main">Skip to content</a>

<div class="shell">
  <div class="sidebar-slot"><Sidebar /></div>
  <main id="main" tabindex="-1">
    {@render children()}
  </main>
  <div class="tabbar-slot"><TabBar /></div>
</div>

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
