<script lang="ts">
  // How amounts are shown (0.9 U2; spec "Amounts shown in 1.0": as written, plus grams and
  // millilitres; cups as a display choice come after 1.0, and Onboarding and Settings say so).
  // The same choice in Onboarding's Amounts step and Settings → Amounts. The words are cabledrawer's
  // (12 Nov). Nothing on screen converts yet: the choice is kept for a later version.
  import type { AmountsShown } from '#lib/client/types.js';

  let {
    value,
    disabled = false,
    onchange,
    describedby
  }: {
    value: AmountsShown;
    disabled?: boolean;
    onchange: (value: AmountsShown) => void;
    /** Extra words read with the group (e.g. "Only an admin can change this."). */
    describedby?: string;
  } = $props();

  const uid = $props.id();

  const CHOICES: { value: AmountsShown; label: string }[] = [
    { value: 'as_written', label: 'As the recipe says (cups stay cups)' },
    { value: 'metric', label: 'Metric: grams and ml' }
  ];
</script>

<div
  class="amounts"
  role="radiogroup"
  aria-label="How amounts are shown"
  aria-describedby={[`${uid}-later`, describedby].filter(Boolean).join(' ')}
>
  {#each CHOICES as option (option.value)}
    <label class="choice" class:on={value === option.value}>
      <input
        type="radio"
        name="{uid}-amounts"
        value={option.value}
        checked={value === option.value}
        {disabled}
        onchange={() => onchange(option.value)}
      />
      <span class="dot" aria-hidden="true"></span>
      <span class="name">{option.label}</span>
    </label>
  {/each}
  <p class="later" id="{uid}-later">
    Cups and ounces as a choice come after version 1.0. Grams and millilitres on screen come in a
    later version; your choice is kept.
  </p>
</div>

<style>
  .amounts {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .choice {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: 56px;
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    cursor: pointer;
  }

  .choice.on {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
  }

  /* The real radio is invisible and covers the card (the whole card is the target); the dot draws
     it. */
  .choice input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  .choice input:disabled {
    cursor: not-allowed;
  }

  .dot {
    flex: none;
    width: 22px;
    height: 22px;
    border: 2px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    box-sizing: border-box;
  }

  .choice input:checked + .dot {
    border: 6px solid var(--color-accent);
  }

  .choice input:focus-visible + .dot {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  .name {
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
  }

  .later {
    margin: 0;
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    line-height: 1.45;
  }
</style>
