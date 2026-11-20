<script lang="ts">
  // A labelled text box, with an optional hint under it and an error that replaces the
  // hint. Passwords get a Show / Hide button.
  let {
    id,
    label,
    value = $bindable(''),
    type = 'text',
    autocomplete,
    hint,
    error,
    required = true,
    disabled = false
  }: {
    id: string;
    label: string;
    value?: string;
    type?: 'text' | 'password';
    autocomplete: AutoFill;
    hint?: string;
    error?: string;
    required?: boolean;
    disabled?: boolean;
  } = $props();

  let shown = $state(false);
  const isPassword = $derived(type === 'password');
  const message = $derived(error ?? hint);
  const describedBy = $derived(message ? `${id}-message` : undefined);
</script>

<div class="field">
  <label for={id}>{label}</label>
  <div class="box" class:invalid={!!error}>
    <input
      {id}
      type={isPassword && !shown ? 'password' : 'text'}
      bind:value
      {autocomplete}
      {required}
      {disabled}
      autocapitalize={isPassword || autocomplete === 'username' ? 'none' : undefined}
      spellcheck={isPassword || autocomplete === 'username' ? false : undefined}
      aria-invalid={error ? true : undefined}
      aria-describedby={describedBy}
    />
    {#if isPassword}
      <button
        type="button"
        class="show"
        aria-controls={id}
        aria-pressed={shown}
        aria-label={shown ? 'Hide password' : 'Show password'}
        onclick={() => (shown = !shown)}>{shown ? 'Hide' : 'Show'}</button
      >
    {/if}
  </div>
  {#if message}
    <p id={`${id}-message`} class="message" class:error={!!error}>{message}</p>
  {/if}
</div>

<style>
  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  label {
    color: var(--color-label);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  .box {
    display: flex;
    align-items: center;
    min-height: 50px;
    padding: 0 var(--space-3) 0 14px;
    border: 1px solid var(--color-field-border);
    border-radius: var(--radius-field);
    background: var(--color-field);
  }

  .box:focus-within {
    outline: var(--focus-width) solid var(--color-focus);
    outline-offset: 1px;
  }

  .box.invalid {
    border-color: var(--color-warning-text);
  }

  input {
    flex: 1;
    min-width: 0;
    min-height: 48px;
    border: none;
    background: transparent;
    color: var(--color-text);
    /* 16 px stops phones zooming in on the field. */
    font: var(--weight-medium) 1rem var(--font-ui);
  }

  input:focus {
    outline: none;
  }

  .show {
    min-width: var(--touch-target);
    min-height: var(--touch-target);
    padding: 0 var(--space-5);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .message {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-medium);
  }

  .message.error {
    color: var(--color-warning-text);
    font-weight: var(--weight-bold);
  }
</style>
