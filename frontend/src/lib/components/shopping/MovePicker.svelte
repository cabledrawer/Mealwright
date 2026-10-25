<script lang="ts">
  // "Move Coriander to…" (mockups ShopMovePicker-Phone, ShopMove-Desktop; cabledrawer 22 Oct,
  // question 3): another shop on this list, or another list (the shop stays). One tap moves it,
  // never ticks it, and a toast offers Undo. A sheet from the bottom on a phone, a small menu by
  // the row on a computer. A real modal dialog: focus stays inside, Esc closes it, and focus
  // goes back to where it was opened from.
  import { tick } from 'svelte';
  import { radioKeys } from '#lib/radioKeys.js';

  let {
    open,
    name,
    shops,
    lists,
    anchor = null,
    fallback = null,
    onpick,
    onclose
  }: {
    open: boolean;
    /** The ingredient's name: "Move Coriander to…". */
    name: string;
    /** Every shop and Any shop, `now` marking where the line is. */
    shops: { id: number | null; name: string; now: boolean }[];
    /** The other lists. */
    lists: { id: string; name: string; main: boolean; toBuy: number }[];
    /** The row's button, which a computer's menu sits by and focus goes back to. */
    anchor?: HTMLElement | null;
    /** Where focus goes on Cancel or Esc if the anchor has gone or can't take it (the row). */
    fallback?: HTMLElement | null;
    onpick: (to: { shopId: number | null } | { listId: string }) => void;
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;

  $effect(() => {
    if (open && !dialog.open) {
      dialog.showModal();
      placeBy(anchor);
      void tick().then(() => dialog.querySelector<HTMLElement>('[data-first]')?.focus());
    } else if (!open && dialog.open) {
      dialog.close();
    }
  });

  /** Computer: just under the button (above it if there's no room), inside the window. */
  function placeBy(button: HTMLElement | null) {
    if (!button || matchMedia('(max-width: 767px)').matches) {
      dialog.style.removeProperty('top');
      dialog.style.removeProperty('left');
      return;
    }
    const box = button.getBoundingClientRect();
    const menu = dialog.getBoundingClientRect();
    const below = box.bottom + 4;
    const top =
      below + menu.height > innerHeight - 8 ? Math.max(8, box.top - menu.height - 4) : below;
    const left = Math.min(Math.max(8, box.right - menu.width), innerWidth - menu.width - 8);
    dialog.style.top = `${top}px`;
    dialog.style.left = `${left}px`;
  }

  function close() {
    onclose();
    queueMicrotask(() => {
      const back = anchor?.isConnected && anchor.offsetParent !== null ? anchor : fallback;
      back?.focus();
    });
  }

  function pick(to: { shopId: number | null } | { listId: string }) {
    onpick(to);
    onclose();
  }
</script>

<dialog
  bind:this={dialog}
  class="move-picker"
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    close();
  }}
  onclick={(event) => {
    if (event.target === dialog) close();
  }}
>
  {#if open}
    <div class="body">
      <span class="grab" aria-hidden="true"></span>
      <p class="title" id="{uid}-title">Move {name} to…</p>
      <p class="overline" id="{uid}-shops">Another shop</p>
      <div
        class="choices"
        role="radiogroup"
        aria-labelledby="{uid}-shops"
        use:radioKeys={{ select: false }}
      >
        {#each shops as shop, i (shop.id)}
          <button
            type="button"
            role="radio"
            aria-checked={shop.now}
            data-first={i === 0 ? '' : undefined}
            onclick={() => (shop.now ? close() : pick({ shopId: shop.id }))}
          >
            {shop.name}{#if shop.now}<span class="now">now</span>{/if}
          </button>
        {/each}
      </div>
      {#if lists.length}
        <p class="overline" id="{uid}-lists">Another list</p>
        <div class="choices" role="group" aria-labelledby="{uid}-lists">
          {#each lists as list (list.id)}
            <button type="button" onclick={() => pick({ listId: list.id })}>
              {list.name}<span class="sub"
                >{list.main ? 'Main list' : 'Extra list'} · {list.toBuy}</span
              >
            </button>
          {/each}
        </div>
      {/if}
      <button type="button" class="cancel" onclick={close}>Cancel</button>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: min(90dvh, 40rem);
    margin: 0;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-toast);
    overflow-y: auto;
  }

  dialog::backdrop {
    background: transparent;
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .grab {
    display: none;
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .title {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .overline {
    padding-top: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  .choices {
    display: flex;
    flex-direction: column;
    border: 1px solid var(--color-divider);
    border-radius: 16px;
    overflow: hidden;
  }

  .choices button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    min-height: 52px;
    padding: 0 var(--space-8);
    border: none;
    border-bottom: 1px solid var(--color-divider);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) 1rem var(--font-ui);
    text-align: left;
    overflow-wrap: anywhere;
    cursor: pointer;
  }

  .choices button:last-child {
    border-bottom: none;
  }

  .choices button:hover {
    background: var(--color-fill);
  }

  .choices button[aria-checked='true'] {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-bold);
  }

  .now,
  .sub {
    flex: none;
    font-size: var(--text-md);
  }

  .sub {
    color: var(--color-text-muted);
  }

  .cancel {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }

  /* Phone: a sheet from the bottom. */
  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      padding: var(--space-4) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    }

    dialog::backdrop {
      background: var(--color-overlay);
    }

    .grab {
      display: block;
    }
  }

  /* Computer: a small menu by the ⋯ button. */
  @media (min-width: 768px) {
    dialog {
      position: fixed;
      width: 280px;
      padding: var(--space-5);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
    }
  }
</style>
