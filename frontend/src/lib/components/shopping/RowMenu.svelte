<script lang="ts">
  // The ⋯ menu on a computer's shopping row (mockup ShopMove-Desktop): Change amount · Move to… ·
  // Remove from list…. A menu you open with the button, move through with the arrow keys, choose
  // from with Enter, and leave with Esc (focus goes back to the button). Each choice closes it
  // and does the thing the row's own buttons do. The recipe page uses it too (Delete recipe).
  import { tick } from 'svelte';

  let {
    name,
    items
  }: {
    /** The ingredient: "More for Coriander". */
    name: string;
    items: {
      label: string;
      danger?: boolean;
      /** A thin rule above this choice (not drawn when it is the first). */
      divider?: boolean;
      run: (opener: HTMLElement) => void;
    }[];
  } = $props();

  const uid = $props.id();
  let open = $state(false);
  let button = $state<HTMLButtonElement>();
  let menu = $state<HTMLElement>();

  const entries = () => [...(menu?.querySelectorAll<HTMLElement>('[role="menuitem"]') ?? [])];

  async function toggle() {
    open = !open;
    if (open) {
      await tick();
      entries()[0]?.focus();
    }
  }

  function close(refocus = true) {
    open = false;
    if (refocus) button?.focus();
  }

  function onkeydown(event: KeyboardEvent) {
    if (!open) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }
    const all = entries();
    const at = all.indexOf(document.activeElement as HTMLElement);
    const step = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
    if (step) {
      event.preventDefault();
      all[(at + step + all.length) % all.length]?.focus();
    } else if (event.key === 'Home' || event.key === 'End') {
      event.preventDefault();
      all[event.key === 'Home' ? 0 : all.length - 1]?.focus();
    } else if (event.key === 'Tab') {
      close(false);
    }
  }
</script>

<svelte:window
  onpointerdown={(event) => {
    if (open && !(event.target as Node).parentElement?.closest('.row-menu')) close(false);
  }}
/>

<span class="row-menu" {onkeydown} role="presentation">
  <button
    type="button"
    class="more"
    bind:this={button}
    aria-label="More for {name}"
    aria-haspopup="menu"
    aria-expanded={open}
    aria-controls={open ? `${uid}-menu` : undefined}
    onclick={() => void toggle()}>⋯</button
  >
  {#if open}
    <div class="menu" id="{uid}-menu" role="menu" aria-label={name} bind:this={menu}>
      {#each items as item, i (item.label)}
        {#if item.divider && i > 0}<span class="rule" aria-hidden="true"></span>{/if}
        <button
          type="button"
          role="menuitem"
          class:danger={item.danger}
          tabindex="-1"
          onclick={() => {
            close(false);
            item.run(button!);
          }}>{item.label}</button
        >
      {/each}
    </div>
  {/if}
</span>

<style>
  .row-menu {
    position: relative;
    display: inline-flex;
    flex: none;
  }

  .more {
    width: var(--touch-target);
    height: var(--touch-target);
    padding: 0;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-extrabold) 1.125rem var(--font-ui);
    cursor: pointer;
  }

  .more[aria-expanded='true'],
  .more:hover {
    background: var(--color-chip);
    color: var(--color-text);
  }

  .menu {
    position: absolute;
    top: calc(100% + 4px);
    right: 0;
    z-index: 5;
    display: flex;
    flex-direction: column;
    width: 250px;
    padding: 6px;
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-button);
    background: var(--color-surface);
    box-shadow: var(--shadow-toast);
  }

  .menu button {
    min-height: var(--touch-target);
    padding: 0 12px;
    border: none;
    border-radius: 10px;
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-lg) var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .menu button:hover,
  .menu button:focus-visible {
    background: var(--color-chip);
  }

  .menu .danger {
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-weight: var(--weight-bold);
  }

  .rule {
    height: 1px;
    margin: 4px 6px;
    background: var(--color-divider);
  }
</style>
