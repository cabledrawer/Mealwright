<script lang="ts">
  // One recipe in the All recipes list (mockups Recipes-Phone, Dark-Recipes-Phone): a
  // square, the name, and a quiet line "50 min · 320 kcal · all in stock but 1". The square
  // is plain and warm; the recipe's photo fills it when it has one (the small copy, `list_url`,
  // made for this square at 3×). A photo that can't be fetched (offline, deleted) leaves the
  // plain square, and tries again when the connection comes back. The whole row opens the recipe.
  import { resolve } from '$app/paths';
  import type { RecipeRow } from '#lib/client/recipes.js';
  import { network } from '#lib/network.svelte.js';
  import { recipePeek } from '#lib/recipePeek.js';
  import { recipeParts } from '#lib/recipeLine.js';

  let {
    recipe,
    pane = false,
    current = false,
    search = ''
  }: {
    recipe: RecipeRow;
    /** In the desktop's middle pane: the row has its own card to light up. */
    pane?: boolean;
    /** The recipe open beside the list. */
    current?: boolean;
    /** The list's own query ("?filter=use-soon"), kept in the recipe's address in the panes. */
    search?: string;
  } = $props();
  /** Between the parts; a normal space each side, so a long line wraps there. */
  const SEP = ' · ';
  const parts = $derived(recipeParts(recipe));

  // The address of a photo that failed, and when: a different photo (a new id) gets another go,
  // and the same one tries again once the connection comes back.
  let failed = $state<{ url: string; back: number } | null>(null);
  const photo = $derived(
    recipe.photo && (recipe.photo.list_url !== failed?.url || network.backAgain !== failed.back)
      ? recipe.photo
      : null
  );
</script>

<a
  class="recipe"
  class:pane
  href="{resolve('/(app)/recipes/[id]', { id: String(recipe.id) })}{search}"
  aria-current={current ? 'page' : undefined}
  onclick={() => recipePeek.hold(recipe)}
>
  <span class="square" aria-hidden="true">
    {#if photo}
      <!-- Decorative: the row already says the name. Only ever our own server's address. -->
      <img
        src={photo.list_url}
        alt=""
        width={photo.list_width}
        height={photo.list_height}
        loading="lazy"
        decoding="async"
        onerror={(event) => {
          // The address this picture tried, not the photo shown by the time the error arrives.
          const tried = event.currentTarget.getAttribute('src');
          if (tried) failed = { url: tried, back: network.backAgain };
        }}
      />
    {/if}
  </span>
  <span class="text">
    <span class="name">{recipe.name}</span>
    <span class="line"
      >{#each parts as part, i (i)}{#if i > 0}{SEP}{/if}<span class:soon={part.soon}
          >{part.text}</span
        >{/each}</span
    >
  </span>
</a>

<style>
  .recipe {
    position: relative;
    color: var(--color-text);
    text-decoration: none;
    display: flex;
    /* A name that wraps keeps the square at the top of the row (cabledrawer 20 Oct, #44). */
    align-items: flex-start;
    gap: var(--space-6);
    min-height: 72px;
    /* 52 + 2 × 10 = the row's 72: the square is centred in a one-line row and, when the name
       wraps, stays at the top while the text grows. */
    padding: var(--space-5) 0;
  }

  /* In the middle pane each row is a card of its own (mockup Desktop-Recipe); the open one is
     lifted white, the others show a faint fill under the pointer. */
  .pane {
    padding: var(--space-5);
    border-radius: var(--radius-lg);
  }

  .pane:hover {
    background: var(--color-fill);
  }

  .pane[aria-current='page'] {
    background: var(--color-surface);
    box-shadow: 0 1px 0 var(--color-border);
  }

  .square {
    flex: none;
    width: 52px;
    height: 52px;
    border-radius: var(--radius-md);
    background: var(--color-recipe-square);
    overflow: hidden;
  }

  /* Cropped to fill, never stretched. */
  .square img {
    display: block;
    width: 100%;
    height: 100%;
    object-fit: cover;
  }

  .text {
    /* Centred beside the square when it is shorter; taller, it sets the row's height. */
    align-self: center;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-width: 0;
  }

  .name {
    font-size: 1rem;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .line {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    overflow-wrap: anywhere;
  }

  .soon {
    color: var(--color-use-soon-text);
    font-weight: var(--weight-semibold);
  }
</style>
