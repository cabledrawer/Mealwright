<script lang="ts">
  // The recipe's photo on its page (mockups Recipe and Dark-Phone-Recipe: a box 170 px tall
  // under the top row; Desktop-Recipe and Dark-Recipe: a box beside the nutrition figures).
  // It is the large copy (`url`), cropped to fill the box and never stretched. A recipe with no
  // photo has no box at all, and neither has one whose photo can't be fetched (offline, or
  // deleted meanwhile): never a broken-image icon. Only ever our own server's address.
  import type { PhotoOut } from '$lib/client/recipes';

  let {
    photo,
    name,
    beside = false
  }: {
    photo: PhotoOut | null;
    /** The recipe's name, for the screen reader's words. */
    name: string;
    /** Beside the nutrition figures (the computer's reading pane), not above the name. */
    beside?: boolean;
  } = $props();

  // The address of a photo that failed: another photo (a new id) gets its own go.
  let failed = $state<string | null>(null);
  const shown = $derived(photo && photo.url !== failed ? photo : null);
</script>

{#if shown}
  <div class="frame" class:beside>
    <img
      src={shown.url}
      alt="Photo of {name}"
      width={shown.width}
      height={shown.height}
      decoding="async"
      onerror={() => (failed = shown.url)}
    />
  </div>
{/if}

<style>
  /* The warm colour shows while the photo comes in, so nothing jumps. */
  .frame {
    position: relative;
    height: 170px;
    border-radius: var(--radius-2xl);
    background: var(--color-recipe-square);
    overflow: hidden;
  }

  .beside {
    flex: 1 1 260px;
    height: auto;
    min-height: 150px;
  }

  img {
    position: absolute;
    inset: 0;
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
</style>
