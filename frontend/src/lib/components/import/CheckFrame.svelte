<script lang="ts">
  // The phone's own page for Check (F141, mockups Dark-ImportCheckFocus07-Phone and
  // Dark-ImportCheckOne07-Phone): a compact header on top, the list in the middle (the only part
  // that scrolls), and the buttons at the bottom, with the app's menu hidden. The header and the
  // bar stay put, so the ingredients get the screen (the iPhone hand test found the title and the
  // save area left them about half of it). Used for Focus and One at a time, on a phone only.
  import type { Snippet } from 'svelte';

  let { header, children, footer }: { header: Snippet; children: Snippet; footer: Snippet } =
    $props();

  let footHeight = $state(0);

  // The app's bottom tabs go (the same page-of-its-own switch the recipe editor uses), and the
  // toast with its Undo floats just above this bar instead of over its buttons.
  $effect(() => {
    const root = document.documentElement;
    root.setAttribute('data-full-page', '');
    return () => root.removeAttribute('data-full-page');
  });
  $effect(() => {
    const root = document.documentElement;
    root.style.setProperty('--tabbar-height', `${footHeight}px`);
    return () => root.style.removeProperty('--tabbar-height');
  });
</script>

<div class="frame">
  <header class="head">{@render header()}</header>
  <div class="body">{@render children()}</div>
  <div class="foot" bind:offsetHeight={footHeight}>{@render footer()}</div>
</div>

<style>
  .frame {
    position: fixed;
    inset: 0;
    z-index: 30;
    display: flex;
    flex-direction: column;
    background: var(--color-ground);
  }

  .head {
    flex: none;
    padding: var(--space-6) var(--space-7) var(--space-5);
    padding-top: calc(var(--space-6) + env(safe-area-inset-top));
    border-bottom: 1px solid var(--color-border);
  }

  .body {
    flex: 1;
    min-height: 0;
    padding: var(--space-6) var(--space-7);
    overflow-y: auto;
    overscroll-behavior: contain;
  }

  .foot {
    flex: none;
    padding: var(--space-5) var(--space-7);
    padding-bottom: calc(var(--space-5) + env(safe-area-inset-bottom));
    border-top: 1px solid var(--color-border);
    background: var(--color-surface);
  }
</style>
