<script lang="ts">
  // Check screen, F111: a method step or heading as a text box, with Done and Cancel. Enter is
  // Done, Escape is Cancel. Nothing here is saved: the words go to the Check screen's own steps,
  // and Save sends them. Loaded only when a step is first tapped (it stays out of the page's size).
  // Words are proposed, for cabledrawer (docs/dev/words.md section 35).
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import type { ImportFlow } from '#lib/import.svelte.js';
  import { changeStep } from '#lib/importStepEdits.js';
  import '#lib/styles/fields.css';

  let {
    flow,
    step,
    name,
    onclose,
    onremove
  }: {
    flow: ImportFlow;
    step: { kind: 'step' | 'heading'; text: string; optional?: boolean };
    /** "step 3" or "heading": what the box is for. */
    name: string;
    onclose: () => void;
    onremove: () => void;
  } = $props();

  const uid = $props.id();
  const heading = $derived(step.kind === 'heading');
  // The box starts with the words as they are now.
  // svelte-ignore state_referenced_locally
  let text = $state(step.text);
  // An Optional step (R3): kept with Done like the words.
  // svelte-ignore state_referenced_locally
  let optional = $state(!!step.optional);
  let empty = $state(false);
  let box: HTMLTextAreaElement | undefined = $state();

  $effect(() => {
    box?.focus();
  });

  function done() {
    if (changeStep(flow, step, text, optional)) onclose();
    else empty = true;
  }

  function keys(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onclose();
    } else if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      done();
    }
  }
</script>

<div class="edit" role="group" aria-label="Change {name}">
  <label for="{uid}-text" class="visually-hidden">Words of {name}</label>
  <textarea
    id="{uid}-text"
    class="mw-input"
    class:heading
    rows={heading ? 1 : 4}
    maxlength="5000"
    bind:this={box}
    bind:value={text}
    aria-invalid={empty}
    aria-describedby={empty ? `${uid}-empty` : undefined}
    oninput={() => (empty = false)}
    onkeydown={keys}></textarea>
  {#if !heading}
    <p class="optional-row">
      <Switch bind:checked={optional} labelledby="{uid}-optional" />
      <span id="{uid}-optional">Optional step</span>
    </p>
  {/if}
  {#if empty}
    <p id="{uid}-empty" class="problem" role="alert">
      {heading ? 'A heading' : 'A step'} can’t be empty. Write something, or remove it.
    </p>
  {/if}
  <ButtonRow>
    <Button onclick={done}>Done</Button>
    <Button quiet onclick={onclose}>Cancel</Button>
    {#if empty}
      <Button quiet onclick={onremove}>Remove {heading ? 'heading' : 'step'}</Button>
    {/if}
  </ButtonRow>
</div>

<style>
  .edit {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  textarea {
    box-sizing: border-box;
    width: 100%;
    font-size: 1rem;
    line-height: 1.5;
    resize: vertical;
  }

  textarea.heading {
    font-weight: var(--weight-extrabold);
  }

  .optional-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    min-height: var(--touch-target);
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }
</style>
