<script lang="ts">
  // The one on/off switch used everywhere (UX principle 15): click or tap to switch,
  // the same on phone and desktop. Green when on.
  //
  // Give it a visible label with `labelledby` (the id of the text next to it), or an
  // accessible name with `label`.

  let {
    checked = $bindable(false),
    label,
    labelledby,
    describedby,
    disabled = false,
    large = false,
    onchange
  }: {
    checked?: boolean;
    label?: string;
    labelledby?: string;
    describedby?: string;
    disabled?: boolean;
    /** 52 × 32 px, for a box where the switch stands alone (Cook mode, F148). */
    large?: boolean;
    onchange?: (checked: boolean) => void;
  } = $props();

  function toggle() {
    if (disabled) return;
    checked = !checked;
    onchange?.(checked);
  }
</script>

<button
  type="button"
  role="switch"
  class="switch"
  class:large
  aria-checked={checked}
  aria-label={labelledby ? undefined : label}
  aria-labelledby={labelledby}
  aria-describedby={describedby}
  {disabled}
  onclick={toggle}
>
  <span class="knob"></span>
</button>

<style>
  .switch {
    position: relative;
    flex: none;
    width: 46px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: 14px;
    background: var(--color-switch-off);
    cursor: pointer;
    transition: background-color 150ms ease;
  }

  /* A touch area of at least 44 × 44 px around the smaller visible switch. */
  .switch::before {
    content: '';
    position: absolute;
    inset: -8px -4px;
  }

  .switch[aria-checked='true'] {
    background: var(--color-switch-on);
  }

  .switch:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .switch.large {
    width: 52px;
    height: 32px;
    border-radius: 16px;
  }

  .knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 24px;
    height: 24px;
    border-radius: 12px;
    background: var(--color-switch-knob);
    box-shadow: var(--shadow-switch-knob);
    transition: transform 150ms ease;
  }

  .switch[aria-checked='true'] .knob {
    transform: translateX(18px);
  }

  .large .knob {
    top: 3px;
    left: 3px;
    width: 26px;
    height: 26px;
    border-radius: 13px;
  }

  .large[aria-checked='true'] .knob {
    transform: translateX(20px);
  }

  @media (forced-colors: active) {
    .switch {
      border: 1px solid ButtonText;
    }
    .switch[aria-checked='true'] {
      background: Highlight;
    }
    .knob {
      background: ButtonText;
    }
  }
</style>
