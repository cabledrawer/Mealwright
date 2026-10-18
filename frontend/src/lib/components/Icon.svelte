<script lang="ts" module>
  // Line icons from the mockups, drawn on a 24 × 24 grid in the current text colour.
  // Always decorative: the text or aria-label next to it says what it is.
  export type Name =
    | 'today'
    | 'plan'
    | 'shopping'
    | 'pantry'
    | 'recipes'
    | 'auto'
    | 'light'
    | 'dark'
    | 'expand'
    | 'collapse'
    | 'back'
    | 'chevron-down'
    | 'search'
    | 'pencil'
    | 'calendar';
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
  {:else if name === 'auto'}
    <circle cx="12" cy="12" r="8" />
    <path d="M12 4a8 8 0 0 1 0 16z" fill="currentColor" />
  {:else if name === 'light'}
    <circle cx="12" cy="12" r="4" />
    <path
      d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
    />
  {:else if name === 'dark'}
    <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />
  {:else if name === 'expand'}
    <path d="M9 6l6 6-6 6" />
    <path d="M4 4v16" />
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
  {:else if name === 'search'}
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  {/if}
</svg>
