<script lang="ts">
  // "+ New recipe": a button that opens a small choice, Add by hand · Import recipe
  // (spec section 6, N1, cabledrawer 28 Oct). A menu button (WAI-ARIA), like the Recipes pop-out:
  // Enter, Space or the Down arrow open it, with focus on the first choice; Up and Down move
  // (Home and End jump); Esc closes it and puts focus back on the button; clicking elsewhere or
  // Tab-ing away closes it too.
  import { resolve } from '$app/paths';
  import Icon from './Icon.svelte';

  const uid = $props.id();
  let open = $state(false);
  let wrap: HTMLElement;
  let trigger: HTMLButtonElement;
  let menu = $state<HTMLElement>();

  const items = () => [...(menu?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];

  function show(at: 'first' | 'last' = 'first') {
    open = true;
    requestAnimationFrame(() => {
      const all = items();
      (at === 'last' ? all.at(-1) : all[0])?.focus();
    });
  }

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
      event.preventDefault();
      hide(true);
      return;
    }
    if (to === null) return;
    event.preventDefault();
    all[to]!.focus();
  }

  function onFocusout(event: FocusEvent) {
    const next = event.relatedTarget as Node | null;
    if (open && next && !wrap.contains(next)) hide(false);
  }

  function onWindowPointerdown(event: PointerEvent) {
    if (open && !wrap.contains(event.target as Node)) hide(false);
  }
</script>

<svelte:window onpointerdown={onWindowPointerdown} />

<div
  class="wrap"
  bind:this={wrap}
  onkeydown={onKeydown}
  onfocusout={onFocusout}
  role="presentation"
>
  <button
    type="button"
    class="new"
    bind:this={trigger}
    aria-haspopup="menu"
    aria-expanded={open}
    aria-controls={open ? `${uid}-menu` : undefined}
    onclick={() => (open ? hide(true) : show())}
    onkeydown={onTriggerKeydown}
  >
    <Icon name="plus" size={20} stroke={2.4} />New recipe
  </button>
  {#if open}
    <div class="menu" id="{uid}-menu" role="menu" aria-label="New recipe" bind:this={menu}>
      <a
        href={resolve('/(app)/recipes/new')}
        role="menuitem"
        tabindex="-1"
        onclick={() => hide(false)}>Add by hand</a
      >
      <a
        href={resolve('/(app)/recipes/import')}
        role="menuitem"
        tabindex="-1"
        onclick={() => hide(false)}>Import recipe</a
      >
    </div>
  {/if}
</div>

<style>
  .wrap {
    position: relative;
  }

  /* The mockups' dark button, as wide as the column. */
  .new {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-3);
    width: 100%;
    min-height: 52px;
    padding: 0 18px;
    border: none;
    border-radius: var(--radius-field);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .menu {
    position: absolute;
    inset: calc(100% + var(--space-2)) 0 auto;
    z-index: 30;
    display: flex;
    flex-direction: column;
    padding: var(--space-2);
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

  .menu a:hover,
  .menu a:focus-visible {
    background: var(--color-fill);
    color: var(--color-text);
  }
</style>
