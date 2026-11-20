<script lang="ts">
  // "Remove Onion from the shopping list?" (mockups ShopRows-confirm; cabledrawer 20 Oct): the
  // one place on the shopping list that asks first, because a swipe can be an accident. "Keep it"
  // has the focus when it opens, Escape and a tap outside also keep it. Removing still offers Undo
  // in a toast afterwards. Show it only while asking: {#if asking}<RemoveConfirm …/>{/if}.
  import Sheet from '#lib/components/Sheet.svelte';

  let {
    name,
    onremove,
    onkeep
  }: {
    /** The ingredient's name: "Remove Onion from the shopping list?". */
    name: string;
    onremove: (event: MouseEvent) => void;
    onkeep: () => void;
  } = $props();

  const uid = $props.id();
</script>

<Sheet
  title="Remove {name} from the shopping list?"
  size="small"
  role="alertdialog"
  describedby="{uid}-d"
  onclose={onkeep}
>
  <p id="{uid}-d">Nothing goes into the pantry.</p>
  <div class="buttons">
    <!-- The safe choice has the focus. -->
    <!-- svelte-ignore a11y_autofocus -->
    <button type="button" class="keep" autofocus onclick={onkeep}>Keep it</button>
    <button type="button" class="remove" onclick={onremove}>Remove</button>
  </div>
</Sheet>

<style>
  p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .buttons {
    display: flex;
    gap: var(--space-4);
  }

  button {
    min-height: var(--touch-target);
    padding: 0 18px;
    border-radius: var(--radius-lg);
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }

  .keep {
    border: 1px solid var(--color-border-strong);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .remove {
    border: none;
    background: var(--color-danger);
    color: var(--color-danger-text);
  }

  /* Phone: Remove on top and big. */
  @media (max-width: 767px) {
    .buttons {
      flex-direction: column-reverse;
    }

    button {
      min-height: 52px;
      font-size: var(--text-xl);
    }
  }

  /* Computer: Keep it then Remove on the right. */
  @media (min-width: 768px) {
    .buttons {
      justify-content: flex-end;
    }
  }
</style>
