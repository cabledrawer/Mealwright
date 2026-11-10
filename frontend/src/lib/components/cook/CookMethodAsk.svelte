<script lang="ts">
  // "How are you cooking it today?" (M2, mockup CookMethod08, cabledrawer 9 Nov): each way of cooking
  // the recipe with its time, step count and "last time", one picked, and "Start · Stovetop". Steps,
  // timers and the time follow the pick, and the meal is set to it so Cooked it follows. Loaded
  // when Cook mode first has a recipe with two ways (size limit). Words are proposed, for cabledrawer,
  // except the question (docs/dev/words.md).
  import type { Recipe } from '#lib/client/recipes.js';
  import { setMealWay } from '#lib/cookWays.js';
  import { network } from '#lib/network.svelte.js';
  import { timeWithWait } from '#lib/timeWords.js';
  import { toasts } from '#lib/toast.svelte.js';

  let {
    recipe,
    item,
    current,
    onstart,
    onchanged
  }: {
    recipe: Recipe;
    /** This recipe's item in the meal Cooked it would review, if there is one. */
    item: { id: number; method_id?: number | null } | null;
    /** The way on now (switching on the first step); null the first time. */
    current: number | null;
    onstart: (id: number) => void;
    /** The meal was set to another way. */
    onchanged: () => void;
  } = $props();

  const ways = $derived(
    (recipe.methods ?? []).map((m, i) => {
      const steps = (i === 0 ? recipe.steps : recipe.second_method?.steps) ?? [];
      const count = steps.filter((s) => s.kind === 'step').length;
      return {
        id: m.id,
        name: m.name,
        detail: [
          timeWithWait(m.time_minutes, m.wait),
          `${count} ${count === 1 ? 'step' : 'steps'}`,
          m.used_last ? 'last time' : ''
        ]
          .filter(Boolean)
          .join(' · ')
      };
    })
  );
  /** Pre-picked: the way on now, else the meal's, else the one used last, else the first. */
  const picked = $derived(
    current ??
      item?.method_id ??
      recipe.methods?.find((m) => m.used_last)?.id ??
      recipe.methods?.[0]?.id ??
      0
  );

  /** The meal cooks the way that was picked: the list, Can cook now and Cooked it follow it. */
  async function start(id: number) {
    onstart(id);
    // Offline, nothing is said here: Cooked it sets the way again before it opens.
    if (!item || item.method_id === id || network.offline) return;
    if (await setMealWay(item, id)) onchanged();
    else {
      toasts.show('Couldn’t change how the meal is cooked. Try again from the Plan.', {
        tone: 'problem'
      }); // proposed, for cabledrawer
    }
  }

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
    void start(now); // closed: the way that was on (or pre-picked) stays
  }}
  data-testid="cook-method"
>
  <form
    onsubmit={(event) => {
      event.preventDefault();
      void start(now);
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
