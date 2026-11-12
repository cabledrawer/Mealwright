<script lang="ts">
  // A person's round initial (0.9 A1, mockups Household09, Person09 and WhosThis09), in their
  // colour. Someone with no colour chosen gets one from their number, so two people side by
  // side rarely match (cabledrawer 12 Nov). The name is said next to it, so it is hidden
  // from screen readers.
  import { COLOURS, initial, type Colour } from '#lib/client/people.js';

  let {
    id,
    name,
    colour,
    size = 36
  }: { id: number; name: string; colour: Colour | null; size?: 36 | 52 | 56 } = $props();

  const shown: Colour = $derived(colour ?? COLOURS[Math.abs(id) % COLOURS.length] ?? 'green');
</script>

<span
  class="avatar"
  aria-hidden="true"
  data-colour={shown}
  style:--size="{size}px"
  style:background="var(--person-{shown})"
  style:color="var(--person-{shown}-text)">{initial(name)}</span
>

<style>
  .avatar {
    display: grid;
    flex: none;
    place-items: center;
    width: var(--size);
    height: var(--size);
    border-radius: 50%;
    font-size: calc(var(--size) * 0.39);
    font-weight: var(--weight-extrabold);
    line-height: 1;
  }
</style>
