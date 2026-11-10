<script lang="ts">
  // "How are you cooking it today?" (M2, mockup CookMethod08, cabledrawer 9 Nov): each way of cooking
  // the recipe with its time, step count and "last time", one picked, and "Start · Stovetop". Steps,
  // timers and the time follow the pick. Loaded when Cook mode first has a recipe with two ways
  // (size limit). Words are proposed, for cabledrawer, except the question (docs/dev/words.md).
  export interface Way {
    id: number;
    name: string;
    /** "45 min active · 3 steps · last time". */
    detail: string;
  }

  let {
    ways,
    picked,
    onstart,
    onclose
  }: {
    ways: Way[];
    /** The way ticked to begin with. */
    picked: number;
    onstart: (id: number) => void;
    /** Escape: keeps the way that was on (the first time, the pre-picked one). */
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  // The start state is the prop; the person's tap changes this copy.
  let chosen = $state<number | null>(null);
  const now = $derived(chosen ?? picked);
  const name = $derived(ways.find((w) => w.id === now)?.name ?? '');

  $effect(() => {
    if (!dialog.open) dialog.showModal();
  });
</script>

<dialog
  bind:this={dialog}
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  data-testid="cook-method"
>
  <form
    onsubmit={(event) => {
      event.preventDefault();
      onstart(now);
    }}
  >
    <span class="handle" aria-hidden="true"></span>
    <h2 id="{uid}-title">How are you cooking it today?</h2>
    <ul>
      {#each ways as way (way.id)}
        <li>
          <label class="way">
            <input
              type="radio"
              name="{uid}-way"
              value={way.id}
              checked={now === way.id}
              onchange={() => (chosen = way.id)}
            />
            <b>{way.name}</b>
            <span>{way.detail}</span>
          </label>
        </li>
      {/each}
    </ul>
    <p class="hint">
      Steps, timers and the time follow your pick. You can switch on the first step.
    </p>
    <button type="submit" class="main">Start · {name}</button>
  </form>
</dialog>

<style>
  dialog {
    position: fixed;
    inset: auto 0 0 0;
    width: 100%;
    max-width: 560px;
    margin: 0 auto;
    padding: var(--space-5) var(--space-9) var(--space-9);
    border: none;
    border-radius: var(--radius-xl) var(--radius-xl) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
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

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .way {
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 2px;
    min-height: 64px;
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    cursor: pointer;
  }

  .way:has(input:checked) {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .way:has(input:focus-visible) {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  .way input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
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

  .hint {
    margin: 0;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .main {
    min-height: 52px;
    border: none;
    border-radius: var(--radius-lg);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-extrabold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }
</style>
