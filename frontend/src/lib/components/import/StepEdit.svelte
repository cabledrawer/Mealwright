<script lang="ts">
  // Check screen, F111: a method step or heading as a text box, with Done and Cancel. Enter is
  // Done, Escape is Cancel. Nothing here is saved: the words go to the Check screen's own steps,
  // and Save sends them. Loaded only when a step is first tapped (it stays out of the page's size).
  // Words are proposed, for cabledrawer (docs/dev/words.md section 35).
  import type { ImportFlow } from '#lib/import.svelte.js';
  import { changeStep } from '#lib/importStepEdits.js';
  import '#lib/styles/fields.css';

  let {
    flow,
    at,
    name,
    onclose,
    onremove
  }: {
    flow: ImportFlow;
    at: number;
    /** "step 3" or "heading": what the box is for. */
    name: string;
    onclose: () => void;
    onremove: () => void;
  } = $props();

  const uid = $props.id();
  const heading = $derived(flow.review?.steps[at]?.kind === 'heading');
  // The box starts with the words as they are now.
  // svelte-ignore state_referenced_locally
  let text = $state(flow.review?.steps[at]?.text ?? '');
  let empty = $state(false);
  let box: HTMLTextAreaElement | undefined = $state();

  $effect(() => {
    box?.focus();
  });

  function done() {
    if (changeStep(flow, at, text)) onclose();
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
  {#if empty}
    <p id="{uid}-empty" class="problem" role="alert">
      {heading ? 'A heading' : 'A step'} can’t be empty. Write something, or remove it.
    </p>
  {/if}
  <div class="buttons">
    <button type="button" class="done" onclick={done}>Done</button>
    <button type="button" class="cancel" onclick={onclose}>Cancel</button>
    {#if empty}
      <button type="button" class="cancel" onclick={onremove}>
        Remove {heading ? 'heading' : 'step'}
      </button>
    {/if}
  </div>
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

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .buttons {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .done,
  .cancel {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border-radius: var(--radius-full);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .done {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  .cancel {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }
</style>
