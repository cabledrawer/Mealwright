<script lang="ts">
  // The Recipes icon in the collapsed sidebar: a button that opens a small pop-out with
  // the pages under Recipes (All recipes · Import · Drafts), the current one
  // marked. A menu button (WAI-ARIA): Enter, Space or the Down arrow open it; Up and
  // Down move between the pages (Home and End jump); Esc closes it and puts focus back
  // on the icon; clicking elsewhere, or Tab-ing away, closes it too.
  import { resolve } from '$app/paths';
  import { RECIPES_PAGES, appRoute, isCurrentRecipesPage } from '#lib/nav.js';
  import Icon from './Icon.svelte';

  let { pathname, current }: { pathname: string; current: boolean } = $props();

  const uid = $props.id();
  let open = $state(false);
  let wrap: HTMLElement;
  let trigger: HTMLButtonElement;
  let menu = $state<HTMLElement>();

  const items = () => [...(menu?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];

  /** Open it, with focus on the current page (or `at`: the first or last page). */
  function show(at?: 'first' | 'last') {
    open = true;
    // The pop-out is fixed to the window, so the sidebar's own scrolling never clips it.
    requestAnimationFrame(() => {
      const box = trigger.getBoundingClientRect();
      if (!menu) return;
      const top = Math.min(box.top, innerHeight - menu.offsetHeight - 8);
      menu.style.left = `${box.right + 8}px`;
      menu.style.top = `${Math.max(8, top)}px`;
      const all = items();
      const target =
        at === 'last'
          ? all.at(-1)
          : at === 'first'
            ? all[0]
            : (all.find((a) => a.getAttribute('aria-current') === 'page') ?? all[0]);
      target?.focus();
    });
  }

  /** Close it. `refocus`: put focus back on the icon (Esc, clicking elsewhere). */
  function hide(refocus: boolean) {
    open = false;
    if (refocus) trigger.focus();
  }

  function onTriggerKeydown(event: KeyboardEvent) {
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      show('first');
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      show('last');
    }
  }

  function onKeydown(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      hide(true);
      return;
    }
    const all = items();
    const here = all.indexOf(event.target as HTMLElement);
    if (here === -1) return;
    let to: number | null = null;
    if (event.key === 'ArrowDown') to = (here + 1) % all.length;
    else if (event.key === 'ArrowUp') to = (here - 1 + all.length) % all.length;
    else if (event.key === 'Home') to = 0;
    else if (event.key === 'End') to = all.length - 1;
    else if (event.key === 'Tab' && event.shiftKey) {
      // Back to the icon, closed. (Tab forward leaves; focusout below closes it.)
      event.preventDefault();
      hide(true);
      return;
    }
    if (to === null) return;
    event.preventDefault();
    all[to]!.focus();
  }

  /** Focus left the icon and the pop-out (Tab away): close without taking focus back. */
  function onFocusout(event: FocusEvent) {
    const next = event.relatedTarget as Node | null;
    if (open && next && !wrap.contains(next)) hide(false);
  }

  function onWindowPointerdown(event: PointerEvent) {
    if (!open || wrap.contains(event.target as Node)) return;
    hide(false);
    // If that click didn't land on something that takes focus, focus goes to the icon.
    setTimeout(() => {
      if (!document.activeElement || document.activeElement === document.body) trigger.focus();
    });
  }
</script>

<svelte:window onpointerdown={onWindowPointerdown} />

<!-- The keydown/focusout handlers sit on the wrapper so they see the icon and the pop-out. -->
<div
  class="wrap"
  bind:this={wrap}
  onkeydown={onKeydown}
  onfocusout={onFocusout}
  role="presentation"
>
  <button
    type="button"
    class="trigger"
    class:current
    bind:this={trigger}
    aria-label="Recipes"
    title={open ? undefined : 'Recipes'}
    aria-haspopup="menu"
    aria-expanded={open}
    aria-controls={open ? `${uid}-menu` : undefined}
    onclick={() => (open ? hide(true) : show())}
    onkeydown={onTriggerKeydown}
  >
    <Icon name="recipes" size={24} />
  </button>
  {#if open}
    <div class="menu" id="{uid}-menu" role="menu" aria-label="Recipes" bind:this={menu}>
      {#each RECIPES_PAGES as sub (sub.href)}
        {@const here = isCurrentRecipesPage(sub, pathname)}
        <a
          href={resolve(appRoute(sub.href))}
          role="menuitem"
          tabindex="-1"
          aria-current={here ? 'page' : undefined}
          onclick={() => hide(false)}>{sub.label}</a
        >
      {/each}
    </div>
  {/if}
</div>

<style>
  .wrap {
    display: flex;
  }

  .trigger {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 48px;
    height: 48px;
    padding: 0;
    border: none;
    border-radius: var(--radius-lg);
    background: transparent;
    color: var(--color-text-soft);
    cursor: pointer;
  }

  .trigger:hover {
    background: var(--color-fill);
    color: var(--color-text);
  }

  /* Somewhere under Recipes: marked like the other current pages. */
  .trigger.current {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .menu {
    position: fixed;
    z-index: 60;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 11rem;
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    box-shadow: var(--shadow-toast);
  }

  .menu a {
    display: flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border-radius: var(--radius-md);
    color: var(--color-text);
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    text-decoration: none;
  }

  .menu a:hover {
    background: var(--color-fill);
  }

  .menu a[aria-current='page'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
  }
</style>
