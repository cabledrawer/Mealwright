<script lang="ts" generics="T extends { id: number; name: string }">
  // A list of named rows that can be put in order (drag the grip, or Move up / Move down, which
  // work from the keyboard and on a phone), renamed in place and, when asked, removed. Used by
  // Settings for meal slots, shops and places. It changes nothing itself: it says what was
  // asked (onorder, onrename, onremove) and the screen sends it.
  import type { Snippet } from 'svelte';
  import Icon from '#lib/components/Icon.svelte';

  let {
    items,
    noun,
    disabled = false,
    onorder,
    onrename,
    onremove,
    removeBlocked,
    after
  }: {
    items: T[];
    /** "shop", "place", "meal": used in the buttons' names ("Rename shop Aldi" is just "Rename Aldi"). */
    noun: string;
    disabled?: boolean;
    onorder: (ids: number[]) => void;
    /** Resolves true when the new name was taken (the box closes), false to keep it open. */
    onrename: (item: T, name: string) => Promise<boolean> | boolean;
    onremove?: (item: T) => void;
    /** A reason this row can't be removed (its Remove is greyed out and says so). */
    removeBlocked?: (item: T) => string | null;
    /** What goes after the name: a kind, a switch. */
    after?: Snippet<[T]>;
  } = $props();

  let editing = $state<number | null>(null);
  let draft = $state('');
  let dragging = $state<number | null>(null);
  let over = $state<number | null>(null);

  function move(id: number, by: -1 | 1) {
    const at = items.findIndex((i) => i.id === id);
    const to = at + by;
    if (at === -1 || to < 0 || to >= items.length) return;
    const ids = items.map((i) => i.id);
    [ids[at], ids[to]] = [ids[to]!, ids[at]!];
    onorder(ids);
  }

  function drop(target: number) {
    const from = dragging;
    dragging = over = null;
    if (from === null || from === target) return;
    const ids = items.map((i) => i.id).filter((id) => id !== from);
    ids.splice(
      ids.indexOf(target) +
        (items.findIndex((i) => i.id === from) < items.findIndex((i) => i.id === target) ? 1 : 0),
      0,
      from
    );
    onorder(ids);
  }

  function startEdit(item: T) {
    editing = item.id;
    draft = item.name;
  }

  async function save(item: T) {
    const name = draft.trim();
    if (!name || name === item.name) {
      editing = null;
      return;
    }
    if (await onrename(item, name)) editing = null;
  }

  function focusOnMount(node: HTMLInputElement) {
    node.focus();
    node.select();
  }
</script>

<ul class="rows">
  {#each items as item, index (item.id)}
    {@const blocked = removeBlocked?.(item) ?? null}
    <li
      class:over={over === item.id && dragging !== item.id}
      class:dragging={dragging === item.id}
      draggable={!disabled && editing === null}
      ondragstart={(event) => {
        dragging = item.id;
        event.dataTransfer?.setData('text/plain', String(item.id));
      }}
      ondragover={(event) => {
        if (dragging === null) return;
        event.preventDefault();
        over = item.id;
      }}
      ondragend={() => (dragging = over = null)}
      ondrop={(event) => {
        event.preventDefault();
        drop(item.id);
      }}
    >
      <span class="grip" aria-hidden="true"><Icon name="grip" size={18} /></span>
      {#if editing === item.id}
        <form
          class="edit"
          onsubmit={(event) => {
            event.preventDefault();
            void save(item);
          }}
        >
          <label class="sr" for="rename-{noun}-{item.id}">Name of {item.name}</label>
          <input
            id="rename-{noun}-{item.id}"
            type="text"
            maxlength="60"
            bind:value={draft}
            use:focusOnMount
            onkeydown={(event) => {
              if (event.key === 'Escape') editing = null;
            }}
          />
          <button type="submit" class="solid">Save</button>
        </form>
      {:else}
        <span class="name">{item.name}</span>
        {#if after}{@render after(item)}{/if}
        <span class="buttons">
          <button
            type="button"
            class="icon"
            aria-label="Move {item.name} up"
            disabled={disabled || index === 0}
            onclick={() => move(item.id, -1)}
          >
            <span class="flip"><Icon name="chevron-down" size={18} stroke={2.4} /></span>
          </button>
          <button
            type="button"
            class="icon"
            aria-label="Move {item.name} down"
            disabled={disabled || index === items.length - 1}
            onclick={() => move(item.id, 1)}
          >
            <Icon name="chevron-down" size={18} stroke={2.4} />
          </button>
          <button
            type="button"
            class="icon"
            aria-label="Rename {item.name}"
            {disabled}
            onclick={() => startEdit(item)}
          >
            <Icon name="pencil" size={18} />
          </button>
          {#if onremove}
            <button
              type="button"
              class="icon"
              aria-label="Remove {item.name}"
              disabled={disabled || blocked !== null}
              title={blocked ?? undefined}
              onclick={() => onremove(item)}
            >
              <Icon name="close" size={18} stroke={2.4} />
            </button>
          {/if}
        </span>
      {/if}
    </li>
  {/each}
</ul>

<style>
  .rows {
    display: flex;
    flex-direction: column;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  li {
    display: flex;
    align-items: center;
    gap: var(--space-4);
    min-height: 54px;
    padding: var(--space-1) 0;
    border-top: 1px solid var(--color-divider);
  }

  li:first-child {
    border-top: none;
  }

  li.over {
    box-shadow: 0 -2px 0 var(--color-accent);
  }

  li.dragging {
    opacity: 0.5;
  }

  .grip {
    flex: none;
    color: var(--color-text-muted);
    cursor: grab;
  }

  .name {
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .buttons {
    display: flex;
    flex: none;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    cursor: pointer;
  }

  .icon:disabled {
    opacity: 0.35;
    cursor: default;
  }

  .icon:not(:disabled):hover {
    color: var(--color-text);
  }

  .flip {
    display: inline-flex;
    transform: rotate(180deg);
  }

  .edit {
    display: flex;
    flex: 1;
    gap: var(--space-3);
    min-width: 0;
  }

  .edit input {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: 1px solid var(--color-accent);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: inherit;
    font-weight: var(--weight-semibold);
  }

  .solid {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-field);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
    cursor: pointer;
  }

  .sr {
    position: absolute;
    left: -9999px;
  }
</style>
