<script lang="ts">
  // The toast at the bottom of the screen (see toast.svelte.ts). Above the bottom tabs
  // on phones; bottom right on desktop. The live region is always on the page, so
  // screen readers hear each new message. Its button can be reached with the keyboard
  // (and Ctrl+Z works too), and it stays while focused or hovered.
  import { toasts } from '$lib/toast.svelte';
</script>

<div class="region" role="status" aria-live="polite" aria-atomic="true">
  {#if toasts.current}
    {@const toast = toasts.current}
    {#key toast.id}
      <!-- svelte-ignore a11y_no_static_element_interactions -->
      <div
        class="toast"
        class:problem={toast.tone === 'problem'}
        onmouseenter={() => toasts.pause()}
        onmouseleave={() => toasts.resume()}
        onfocusin={() => toasts.pause()}
        onfocusout={() => toasts.resume()}
      >
        <p class="message">{toast.message}</p>
        {#if toast.action}
          <button type="button" class="action" onclick={() => toasts.act()}>
            {toast.action.label}
          </button>
        {/if}
      </div>
    {/key}
  {/if}
</div>

<style>
  .region {
    position: fixed;
    z-index: 50;
    pointer-events: none;
  }

  .toast {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 52px;
    padding: var(--space-2) var(--space-3) var(--space-2) 14px;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    box-shadow: var(--shadow-toast);
    pointer-events: auto;
    animation: rise 180ms ease-out;
  }

  .message {
    flex: 1;
    min-width: 0;
    padding: var(--space-4) 0;
    font-size: var(--text-base);
    font-weight: var(--weight-semibold);
    line-height: 1.35;
  }

  .action {
    flex: none;
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--color-inverse-text);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .problem .action {
    color: var(--color-toast-action);
  }

  .action:hover {
    background: var(--color-toast-hover);
  }

  .action:focus-visible {
    outline-color: var(--color-inverse-text);
    outline-offset: -2px;
  }

  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
  }

  /* Phone: full width, just above the bottom tabs. */
  @media (max-width: 767px) {
    .region {
      left: var(--space-7);
      right: var(--space-7);
      bottom: calc(var(--tabbar-height) + env(safe-area-inset-bottom) + var(--space-6));
    }
  }

  /* Desktop: bottom right, out of the way of the sidebar. */
  @media (min-width: 768px) {
    .region {
      right: var(--space-10);
      bottom: var(--space-10);
      width: min(420px, calc(100vw - 2 * var(--space-10)));
    }
  }

  @media (forced-colors: active) {
    .toast {
      border: 1px solid CanvasText;
    }
  }
</style>
