<script lang="ts">
  // "Remove Onion from the shopping list?" (mockups ShopRows-confirm; cabledrawer 20 Oct): the
  // one place on the shopping list that asks first, because a swipe can be an accident. "Keep it"
  // has the focus when it opens, Escape and a tap outside also keep it. Removing still offers Undo
  // in a toast afterwards. Show it only while asking: {#if asking}<RemoveConfirm …/>{/if}.
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
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
  <ButtonRow>
    <!-- The safe choice has the focus. -->
    <Button outline autofocus onclick={onkeep}>Keep it</Button>
    <Button danger onclick={onremove}>Remove</Button>
  </ButtonRow>
</Sheet>

<style>
  p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }
</style>
