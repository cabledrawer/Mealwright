<script lang="ts">
  // The one button (FE16). `main` (the default) is the action the page is for: big, dark on light
  // (light on dark). `quiet` is the other choice beside it, on a soft fill (the onboarding
  // mockup's Back). `danger` is for taking something away. `small` is the same button at the
  // 44 px touch size and the width of its words, for a row or a card.
  // Where the screen's own mockup asks for another look, one more variant gives it (kept from the
  // looks before the shared button): `outline` (a line, no fill), `plain` (words only, muted),
  // `soft` (the accent's soft fill), `yes` (green, "Yes, it waits"), `stop` and `warn` (the soft
  // red and amber boxes of Delete everything and Remove from household); `danger` with `outline`
  // or `plain` is words in the warning colour. A Cancel keeps the look it had: `link` (words in the
  // accent colour), `ghost` (words in the text colour, no fill) or `fill` (the light fill). Anything else a button
  // may carry (autofocus, data-testid, aria-*, form, name) is passed straight on.
  import type { Snippet } from 'svelte';
  import type { HTMLButtonAttributes } from 'svelte/elements';

  let {
    type = 'button',
    quiet = false,
    danger = false,
    small = false,
    outline = false,
    plain = false,
    link = false,
    ghost = false,
    fill = false,
    soft = false,
    yes = false,
    stop = false,
    warn = false,
    disabled = false,
    onclick,
    children,
    ...rest
  }: Omit<HTMLButtonAttributes, 'children' | 'class' | 'style'> & {
    type?: 'button' | 'submit';
    quiet?: boolean;
    danger?: boolean;
    small?: boolean;
    outline?: boolean;
    plain?: boolean;
    link?: boolean;
    ghost?: boolean;
    fill?: boolean;
    soft?: boolean;
    yes?: boolean;
    stop?: boolean;
    warn?: boolean;
    disabled?: boolean;
    children: Snippet;
  } = $props();
</script>

<button
  class="mw-button"
  class:quiet
  class:danger
  class:small
  class:outline
  class:plain
  class:link
  class:ghost
  class:fill
  class:soft
  class:yes
  class:stop
  class:warn
  {type}
  {disabled}
  {onclick}
  {...rest}>{@render children()}</button
>

<style>
  .mw-button {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    min-height: 54px;
    padding: 0 var(--space-8);
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .quiet {
    background: var(--color-fill-strong);
    color: var(--color-text);
  }

  .danger {
    background: var(--color-danger);
    color: var(--color-danger-text);
  }

  .outline {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .plain {
    background: transparent;
    color: var(--color-text-muted);
  }

  .link {
    background: transparent;
    color: var(--color-accent);
  }

  .ghost {
    background: transparent;
    color: var(--color-text);
  }

  .fill {
    background: var(--color-fill);
    color: var(--color-text);
  }

  .soft {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
    font-weight: var(--weight-extrabold);
  }

  .yes {
    background: var(--color-wait-yes);
    color: var(--color-wait-yes-text);
  }

  .stop {
    border: 1px solid var(--color-stop-border);
    background: var(--color-stop);
    color: var(--color-stop-title);
  }

  .warn {
    border: 1px solid var(--color-warning-border);
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .danger.outline,
  .danger.plain {
    background: transparent;
    color: var(--color-warning-text);
  }

  .small {
    width: auto;
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
  }

  .mw-button:disabled {
    cursor: progress;
    opacity: 0.7;
  }
</style>
