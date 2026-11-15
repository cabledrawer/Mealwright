<script lang="ts" module>
  // Line icons from the mockups, drawn on a 24 × 24 grid in the current text colour.
  // Always decorative: the text or aria-label next to it says what it is.
  export type Name =
    | 'today'
    | 'plan'
    | 'shopping'
    | 'pantry'
    | 'recipes'
    | 'ingredients'
    | 'auto'
    | 'light'
    | 'dark'
    | 'expand'
    | 'full-size'
    | 'collapse'
    | 'back'
    | 'chevron-down'
    | 'search'
    | 'pencil'
    | 'calendar'
    | 'check'
    | 'plus'
    | 'trash'
    | 'grip'
    | 'close'
    | 'photo'
    | 'info'
    | 'alert'
    | 'cloud-off'
    | 'link'
    | 'note'
    | 'arrow-right'
    | 'place-fridge'
    | 'place-freezer'
    | 'place-cupboard'
    | 'place-spice'
    | 'flask'
    | 'batch'
    | 'pan'
    | 'plate'
    | 'play'
    | 'cog'
    | 'shield';
</script>

<script lang="ts">
  let { name, size = 24, stroke = 2 }: { name: Name; size?: number; stroke?: number } = $props();
</script>

<svg
  aria-hidden="true"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={stroke}
  stroke-linecap="round"
  stroke-linejoin="round"
>
  {#if name === 'today'}
    <path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z" />
  {:else if name === 'plan'}
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  {:else if name === 'shopping'}
    <path d="M5 8h14l-1 12H6z" />
    <path d="M9 8V6a3 3 0 0 1 6 0v2" />
  {:else if name === 'pantry'}
    <path d="M3 4h18v4H3z" />
    <path d="M5 8v11a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8" />
    <path d="M10 12h4" />
  {:else if name === 'recipes'}
    <path d="M5 4h12a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2z" />
    <path d="M9 9h6M9 13h4" />
  {:else if name === 'ingredients'}
    <!-- Ingredients in the main menu (F251; the icon the Settings mockup draws): a round token with a plus. -->
    <circle cx="12" cy="12" r="8" />
    <path d="M12 8v8M8 12h8" />
  {:else if name === 'auto'}
    <circle cx="12" cy="12" r="8" />
    <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
  {:else if name === 'light'}
    <circle cx="12" cy="12" r="4" />
    <path
      d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
    />
  {:else if name === 'flask'}
    <!-- Experimental (cabledrawer 28 Oct, mockup Experimental07): a small flask, in pink. -->
    <path d="M9 3h6" />
    <path d="M10 3v6.2L5.2 18.4A1.8 1.8 0 0 0 6.8 21h10.4a1.8 1.8 0 0 0 1.6-2.6L14 9.2V3" />
    <path d="M7.3 15h9.4" />
  {:else if name === 'batch'}
    <!-- Batch cook (mockup BatchPick08-Desktop): a pot with its lid steaming. -->
    <path d="M4 11h13v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z" />
    <path d="M17 13h3" />
    <path d="M8 4v3M12 4v3" />
  {:else if name === 'dark'}
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
  {:else if name === 'expand'}
    <path d="M9 6l6 6-6 6" />
    <path d="M4 4v16" />
  {:else if name === 'full-size'}
    <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
  {:else if name === 'collapse'}
    <path d="M15 6l-6 6 6 6" />
    <path d="M20 4v16" />
  {:else if name === 'back'}
    <path d="M15 6l-6 6 6 6" />
  {:else if name === 'chevron-down'}
    <path d="M6 9l6 6 6-6" />
  {:else if name === 'pencil'}
    <path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16z" />
    <path d="M13.5 6.5l4 4" />
  {:else if name === 'calendar'}
    <rect x="4" y="5" width="16" height="15" rx="2.5" />
    <path d="M4 10h16M8.5 3v4M15.5 3v4" />
    <path d="M8.5 14.5h.01M12 14.5h.01M15.5 14.5h.01" />
  {:else if name === 'plus'}
    <path d="M12 5v14M5 12h14" />
  {:else if name === 'trash'}
    <path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" />
  {:else if name === 'check'}
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  {:else if name === 'grip'}
    <path d="M9 6h.01M15 6h.01M9 12h.01M15 12h.01M9 18h.01M15 18h.01" stroke-width="3" />
  {:else if name === 'close'}
    <path d="M6 6l12 12M18 6L6 18" />
  {:else if name === 'photo'}
    <path d="M4 8h3l2-3h6l2 3h3v11H4z" />
    <circle cx="12" cy="13" r="3.5" />
  {:else if name === 'shield'}
    <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" />
  {:else if name === 'info'}
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 8h.01" />
  {:else if name === 'alert'}
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v6M12 16.5h.01" />
  {:else if name === 'cloud-off'}
    <path d="M3 3l18 18" />
    <path d="M8.5 8.6A5 5 0 0 0 6 18h11" />
    <path d="M10.7 6.2A6 6 0 0 1 18 11a4 4 0 0 1 2.5 6.3" />
  {:else if name === 'cog'}
    <path
      d="M9.9 5.1 L10.3 2.5 L13.7 2.5 L14.1 5.1 L15.4 5.6 L17.5 4.1 L19.9 6.5 L18.4 8.6 L18.9 9.9 L21.5 10.3 L21.5 13.7 L18.9 14.1 L18.4 15.4 L19.9 17.5 L17.5 19.9 L15.4 18.4 L14.1 18.9 L13.7 21.5 L10.3 21.5 L9.9 18.9 L8.6 18.4 L6.5 19.9 L4.1 17.5 L5.6 15.4 L5.1 14.1 L2.5 13.7 L2.5 10.3 L5.1 9.9 L5.6 8.6 L4.1 6.5 L6.5 4.1 L8.6 5.6Z"
    />
    <circle cx="12" cy="12" r="3" />
  {:else if name === 'link'}
    <path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" />
    <path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" />
  {:else if name === 'note'}
    <path d="M6 3h9l4 4v14H6z" />
    <path d="M9 12h7M9 16h5" />
  {:else if name === 'place-fridge'}
    <rect x="6" y="3" width="12" height="18" rx="2" />
    <path d="M6 10h12M9 6v2M9 13v3" />
  {:else if name === 'place-freezer'}
    <path d="M12 3v18M4.2 7.5l15.6 9M4.2 16.5l15.6-9" />
  {:else if name === 'place-cupboard'}
    <rect x="4" y="4" width="16" height="16" rx="2" />
    <path d="M12 4v16M10 11v2M14 11v2" />
  {:else if name === 'place-spice'}
    <path d="M9 3h6v3H9zM8 6h8l1 3v10a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V9z" />
  {:else if name === 'arrow-right'}
    <path d="M4 12h12M12 6l6 6-6 6" />
  {:else if name === 'pan'}
    <path d="M4 11h13v5a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4z" />
    <path d="M17 13h3" />
  {:else if name === 'plate'}
    <circle cx="12" cy="13" r="7" />
    <path d="M5 13h14" />
  {:else if name === 'play'}
    <path d="M8 5v14l11-7z" fill="currentColor" />
  {:else if name === 'search'}
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  {/if}
</svg>
