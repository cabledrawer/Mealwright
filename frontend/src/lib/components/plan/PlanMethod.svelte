<script lang="ts">
  import Sheet from '#lib/components/Sheet.svelte';
  // "Which way will you cook it?" (M2, cabledrawer 9 Nov): each way of cooking the recipe with its
  // time, the one used last picked, and "Add to plan" (or "Save", when the meal's way is being
  // changed). Shown over everything by the app layout, fetched when first asked (size limit);
  // methodAsk.svelte.ts holds the question. A bottom sheet on a phone, a dialog on a computer.
  // Words are proposed, for cabledrawer (docs/dev/words.md, two cooking methods).
  import { methodAsk } from '#lib/methodAsk.svelte.js';
  import { timeWithWait } from '#lib/timeWords.js';

  const uid = $props.id();
  let picked = $state(0);

  const pending = $derived(methodAsk.current);
  const question = $derived(pending?.question);

  $effect(() => {
    if (question) {
      picked = question.picked;
    }
  });

  function submit(event: SubmitEvent) {
    event.preventDefault();
    methodAsk.answer(picked);
  }
</script>

{#if question}
  <Sheet
    title="{question.recipeName} · {question.where}"
    testid="plan-method"
    outside={false}
    onclose={() => methodAsk.dismiss()}
  >
    <form onsubmit={submit}>
      <fieldset>
        <legend>Which way will you cook it?</legend>
        <ul class="ways">
          {#each question.methods as way (way.id)}
            <li>
              <label class="way">
                <input type="radio" name="{uid}-way" value={way.id} bind:group={picked} />
                <b>{way.name}</b>
                <span
                  >{timeWithWait(way.time_minutes, way.wait)}{way.used_last
                    ? ' · last time'
                    : ''}</span
                >
              </label>
            </li>
          {/each}
        </ul>
        <p class="hint">
          The shopping list and Cooked it follow it. You can change it from the meal later.
        </p>
      </fieldset>
      <button type="submit" class="main">{question.button}</button>
      <button type="button" class="quiet" onclick={() => methodAsk.dismiss()}>Cancel</button>
    </form>
  </Sheet>
{/if}

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
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

  .way {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-height: 64px;
    padding: 0 var(--space-5);
    justify-content: center;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    cursor: pointer;
  }

  .way:has(input:checked) {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .way input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }

  .way:has(input:focus-visible) {
    outline: var(--focus-width) solid var(--color-focus);
    outline-offset: 2px;
  }

  .way b {
    font-size: var(--text-lg);
  }

  .way span {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .way:has(input:checked) span {
    color: inherit;
  }

  .ways {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }
</style>
