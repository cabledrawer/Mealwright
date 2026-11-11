<script lang="ts">
  // The boxes for one step's timing in the recipe editor (Batch cook, Experimental; mockup
  // Dark-BatchSteps08): Hands-on or Waiting, Minutes, and what it Uses. The first change takes
  // all three as the person's ("set by you"); "Guess again" gives them back. Loaded when a step's
  // timing is first opened. Words are the mockup's; "Guess again" is proposed, for cabledrawer.
  import '#lib/styles/fields.css';
  import { radioKeys } from '#lib/radioKeys.js';
  import type { StepEquipment, StepHands } from '#lib/client/recipes.js';
  import type { DraftStep } from '#lib/recipes/draft.svelte.js';
  import {
    EQUIPMENT_CHOICES,
    guessAgain,
    HANDS_CHOICES,
    minutesFrom,
    shownTiming,
    takeAsYours
  } from '#lib/recipes/stepTiming.js';

  let { step, name }: { step: DraftStep; name: string } = $props();

  const uid = $props.id();
  const shown = $derived(shownTiming(step));
  /** What the minutes box holds while it is typed in; follows the step when that changes. */
  let typed = $state<string | null>(null);
  let problem = $state('');
  const minutesText = $derived(typed ?? (shown.minutes === null ? '' : String(shown.minutes)));

  function chooseHands(value: StepHands) {
    takeAsYours(step);
    step.timing.hands = value;
  }

  function chooseEquipment(value: StepEquipment) {
    takeAsYours(step);
    step.timing.equipment = value;
  }

  function typeMinutes(text: string) {
    typed = text;
    const minutes = minutesFrom(text);
    if (minutes === null) {
      problem = 'Type the minutes as a whole number, such as 10.';
      step.timingInvalid = true;
      return;
    }
    problem = '';
    step.timingInvalid = false;
    takeAsYours(step);
    step.timing.minutes = minutes;
  }

  function again() {
    guessAgain(step);
    typed = null;
    problem = '';
    step.timingInvalid = false;
  }
</script>

<div class="timing-fields" data-timing-fields>
  <div class="seg" role="radiogroup" aria-label="Hands-on or waiting, {name}" use:radioKeys>
    {#each HANDS_CHOICES as choice (choice.value)}
      <button
        type="button"
        role="radio"
        aria-checked={shown.hands === choice.value}
        class:on={shown.hands === choice.value}
        onclick={() => chooseHands(choice.value)}>{choice.name}</button
      >
    {/each}
  </div>
  <div class="minutes">
    <label for="{uid}-minutes">Minutes<span class="visually-hidden">, {name}</span></label>
    <input
      id="{uid}-minutes"
      class="mw-input num"
      type="text"
      inputmode="numeric"
      maxlength="5"
      aria-invalid={problem ? true : undefined}
      value={minutesText}
      oninput={(event) => typeMinutes(event.currentTarget.value)}
    />
  </div>
  {#if problem}<p class="mw-error" role="alert">{problem}</p>{/if}
  <span class="uses" id="{uid}-uses">Uses</span>
  <div class="chips" role="radiogroup" aria-labelledby="{uid}-uses" use:radioKeys>
    {#each EQUIPMENT_CHOICES as choice (choice.value)}
      <button
        type="button"
        role="radio"
        aria-checked={shown.equipment === choice.value}
        class="chip"
        class:on={shown.equipment === choice.value}
        onclick={() => chooseEquipment(choice.value)}>{choice.name}</button
      >
    {/each}
  </div>
  <p class="note">
    Guessed from the step. Change anything that’s wrong; Batch cook uses it to fit steps around each
    other.
  </p>
  {#if shown.mark !== 'guessed'}
    <button type="button" class="mw-add again" onclick={again}>Guess again</button>
  {/if}
</div>

<style>
  .timing-fields {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .seg {
    display: grid;
    grid-template-columns: 1fr 1fr;
    padding: 3px;
    border-radius: var(--radius-full);
    background: var(--color-fill);
  }

  .seg button {
    min-height: 44px;
    border: none;
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text-muted);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .seg button.on {
    background: var(--color-segment-active);
    color: var(--color-text);
    font-weight: var(--weight-extrabold);
    box-shadow: 0 0 0 1px var(--color-border);
  }

  .minutes {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
  }

  .minutes label,
  .uses {
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .uses {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .num {
    width: 5.5rem;
    text-align: center;
    font-weight: var(--weight-bold);
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .chip {
    min-height: 44px;
    padding: 0 var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  .chip.on {
    border-color: var(--color-inverse);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-bold);
  }

  .note {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.45;
  }

  .again {
    align-self: flex-start;
  }
</style>
