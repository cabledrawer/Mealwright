<script lang="ts">
  // "This recipe has 2 optional ingredients. Will you use them?" (R3, mockup PlanOptional08):
  // each optional line with its amount and where it is in the pantry, a box to tick it, and "Add
  // to plan" (or "Save", when the meal's answer is being changed). Shown over everything by the
  // app layout; optionalAsk.svelte.ts holds the question. A bottom sheet on a phone, a dialog
  // on a computer. Escape or Cancel plans nothing.
  import { optionalAsk } from '#lib/optionalAsk.svelte.js';
  import { optionalQuestionWords } from '#lib/optionalQuestion.js';

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let ticked = $state<number[]>([]);

  const pending = $derived(optionalAsk.current);
  const question = $derived(pending?.question);

  $effect(() => {
    if (question) {
      ticked = [...question.ticked];
      if (!dialog.open) dialog.showModal();
    } else if (dialog.open) {
      dialog.close();
    }
  });

  function toggle(id: number, on: boolean) {
    ticked = on ? [...ticked, id] : ticked.filter((i) => i !== id);
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    optionalAsk.answer(ticked);
  }
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    optionalAsk.dismiss();
  }}
  data-testid="plan-optional"
>
  {#if question}
    <form onsubmit={submit}>
      <span class="handle" aria-hidden="true"></span>
      <header>
        <h2 id="{uid}-title">{question.recipeName} · {question.where}</h2>
        {#if question.serves}<p class="sub">Serves {question.serves}</p>{/if}
      </header>
      <fieldset>
        <legend>{optionalQuestionWords(question.rows.length)}</legend>
        <ul>
          {#each question.rows as row (row.id)}
            <li>
              <label>
                <input
                  type="checkbox"
                  checked={ticked.includes(row.id)}
                  onchange={(e) => toggle(row.id, e.currentTarget.checked)}
                />
                <span class="box" aria-hidden="true"></span>
                <span class="name">
                  <b>{row.words}</b>
                  {#if row.detail}<span>{row.detail}</span>{/if}
                </span>
              </label>
            </li>
          {/each}
        </ul>
        <p class="hint">
          Ticked ones go on the shopping list if you need them and come out of the pantry when you
          cook. You can change this from the meal later.
        </p>
      </fieldset>
      <button type="submit" class="main">{question.button}</button>
      <button type="button" class="quiet" onclick={() => optionalAsk.dismiss()}>Cancel</button>
    </form>
  {/if}
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: none;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    overscroll-behavior: contain;
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
  }

  .handle {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  header {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .sub {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  fieldset {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    margin: 0;
    padding: 0;
    border: none;
  }

  legend {
    padding: 0;
    margin-bottom: var(--space-4);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  ul {
    margin: 0;
    padding: 0 var(--space-6);
    border-radius: var(--radius-lg);
    background: var(--color-fill);
    list-style: none;
  }

  li + li {
    border-top: 1px solid var(--color-divider);
  }

  /* The real checkbox covers the whole row (a 56 px target); a drawn box shows its state. */
  label {
    position: relative;
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: 56px;
    cursor: pointer;
  }

  input[type='checkbox'] {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  .box {
    display: grid;
    flex: none;
    place-items: center;
    width: 22px;
    height: 22px;
    border: 2px solid var(--color-field-border);
    border-radius: 6px;
    background: var(--color-field);
    color: var(--color-inverse-text);
    font-size: var(--text-lg);
    line-height: 1;
  }

  input:checked + .box {
    border-color: var(--color-accent-hover);
    background: var(--color-accent-hover);
  }

  input:checked + .box::after {
    content: '✓';
  }

  input:focus-visible + .box {
    outline: var(--focus-width) solid var(--color-focus);
    outline-offset: 2px;
  }

  .name {
    display: flex;
    flex-direction: column;
    min-width: 0;
    gap: 2px;
    overflow-wrap: anywhere;
  }

  .name b {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .name span {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .hint {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.4;
  }

  button {
    min-height: 52px;
    border-radius: var(--radius-full);
    font: var(--weight-bold) var(--text-xl) var(--font-ui);
    cursor: pointer;
  }

  .main {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  .quiet {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-text);
  }

  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      max-height: min(680px, calc(100dvh - 120px));
      margin: 0;
      padding: var(--space-5) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
      overflow-y: auto;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: min(460px, calc(100vw - 2 * var(--space-7)));
      max-height: calc(100dvh - 2 * var(--space-7));
      margin: auto;
      padding: var(--space-8) 22px;
      border-radius: var(--radius-panel);
      overflow-y: auto;
    }

    .handle {
      display: none;
    }
  }
</style>
