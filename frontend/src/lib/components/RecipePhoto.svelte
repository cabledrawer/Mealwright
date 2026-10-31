<script lang="ts">
  // The recipe's photo on its page (mockups Recipe and Dark-Phone-Recipe: a box 170 px tall
  // under the top row; Desktop-Recipe and Dark-Recipe: a box beside the nutrition figures).
  // It is the large copy (`url`), cropped to fill the box and never stretched. A recipe with no
  // photo has no box at all, and neither has one whose photo can't be fetched (offline, or
  // deleted meanwhile): never a broken-image icon. If only the large copy fails, the list copy
  // (the one All recipes shows) fills the box instead (0.5.1: cabledrawer saw a photo in All recipes
  // but none here). It tries again when the connection comes back (network.backAgain). Only ever
  // our own server's address.
  import type { PhotoOut } from '#lib/client/recipes.js';
  import { PhotoFallback } from '#lib/photoFallback.svelte.js';
  import ZoomPhoto from './ZoomPhoto.svelte';

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

  const copy = new PhotoFallback(() => photo);
  const shown = $derived(copy.shown);
</script>

{#if shown}
  <div class="frame" class:beside>
    <ZoomPhoto
      src={shown.url}
      alt="Photo of {name}"
      {name}
      width={shown.width}
      height={shown.height}
      onerror={() => copy.fail(shown.url)}
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
</style>
