<script lang="ts">
  // "Ask once" (askOnce.svelte.ts): the server needs a figure it doesn't know, e.g.
  // "About how much does 1 cup of toor dal weigh?". Suggested answer filled in, and a
  // "Remember for next time" switch, on by default. A modal dialog: Escape = Not now.
  import { askOnce } from '#lib/askOnce.svelte.js';
  import Button from './Button.svelte';
  import ButtonRow from './ButtonRow.svelte';
  import Sheet from './Sheet.svelte';
  import Switch from './Switch.svelte';

  const uid = $props.id();
  let value = $state('');
  let remember = $state(true);

  const pending = $derived(askOnce.current);
  const ask = $derived(pending?.ask);
  const number = $derived(Number(value.replace(',', '.')));
  const valid = $derived(value.trim() !== '' && number > 0);

  $effect(() => {
    if (ask) {
      // The suggestion only fills the box; it's sent only if the person presses Save.
      // No good guess: the box starts empty, and Save waits for a number.
      value = ask.suggested === null ? '' : String(ask.suggested);
      remember = true;
    }
  });

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (valid) askOnce.answer(number, ask?.kind === 'size' ? true : remember);
  }

  const unitLabel = $derived(ask?.kind === 'size' ? (ask.unit ?? '') : (ask?.unit ?? 'g'));
</script>

{#if ask}
  <Sheet title={ask.question} size="small" outside={false} onclose={() => askOnce.dismiss()}>
    <form onsubmit={submit}>
      <div class="amount">
        <input
          aria-label={unitLabel ? `Your answer, in ${unitLabel}` : 'Your answer'}
          type="text"
          inputmode="decimal"
          maxlength="20"
          bind:value
          aria-describedby="{uid}-hint"
        />
        {#if unitLabel}<span class="unit" aria-hidden="true">{unitLabel}</span>{/if}
      </div>
      <p id="{uid}-hint" class="hint">
        A rough figure is fine{ask.per === 'cup' && ask.cup_ml ? ` (a ${ask.cup_ml} ml cup)` : ''}.
      </p>
      {#if ask.kind !== 'size'}
        <div class="remember">
          <span id="{uid}-remember">Remember for next time</span>
          <Switch bind:checked={remember} labelledby="{uid}-remember" />
        </div>
      {/if}
      <ButtonRow>
        <Button quiet onclick={() => askOnce.dismiss()}>Not now</Button>
        <Button type="submit" disabled={!valid}>Save</Button>
      </ButtonRow>
    </form>
  </Sheet>
{/if}

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
  }

  .amount {
    display: flex;
    align-items: center;
    gap: var(--space-4);
  }

  input {
    width: 8rem;
    min-height: 50px;
    padding: 0 14px;
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
    color: var(--color-text);
    font: var(--weight-bold) 1.25rem var(--font-ui);
  }

  .unit {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
  }

  .hint {
    margin-top: calc(-1 * var(--space-4));
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .remember {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-6);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }
</style>
