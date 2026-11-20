<script lang="ts">
  // "Eat it on…" for a leftover tub on Pantry's Use soon strip (cabledrawer 7 Nov; mockup
  // Dark-Pantry08-Desktop): the next free meals up to the tub's use-by (F128), one button
  // each; pressing one puts the tub's soonest tub in that meal, with Undo. The same meals
  // "Any left over?" offers (planMeals.nextFreeMeals). A phone sheet; a box on a computer. A
  // real modal dialog: Esc closes it and the focus goes back where it came from.
  import { tick } from 'svelte';
  import { getMealSlots, getPlan, type MealSlot, type Plan } from '#lib/client/plan.js';
  import type { UseSoonTub } from '#lib/client/types.js';
  import { nextFreeMeals } from '#lib/planMeals.js';
  import { dayWords } from '#lib/todayWords.js';

  let {
    tub,
    today,
    onpick,
    onclose
  }: {
    /** The tub card whose meal is being chosen, or null when closed. */
    tub: UseSoonTub | null;
    /** The household's today. */
    today: string;
    onpick: (day: string, slotId: number, slotName: string) => void;
    onclose: () => void;
  } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let slots = $state<MealSlot[]>([]);
  let plan = $state<Plan | null>(null);
  let loading = $state(true);
  let failed = $state(false);

  $effect(() => {
    if (tub && !dialog.open) {
      dialog.showModal();
      void load(tub);
      void tick().then(() => dialog.querySelector<HTMLElement>('[data-first]')?.focus());
    } else if (!tub && dialog.open) {
      dialog.close();
    }
  });

  async function load(wanted: UseSoonTub) {
    loading = true;
    failed = false;
    try {
      [slots, plan] = await Promise.all([getMealSlots(), getPlan(today, wanted.use_by)]);
    } catch {
      failed = true;
    } finally {
      loading = false;
    }
  }

  /** The next free meals, from today to the tub's use-by day, and no more. */
  const options = $derived.by(() => {
    if (!tub || !plan) return [];
    const open = slots
      .filter((s) => s.enabled)
      .sort((a, b) => a.position - b.position || a.id - b.id);
    return nextFreeMeals(plan, open, { date: today, slot_id: -1 }, today, 6, tub.use_by).map(
      (found) => {
        const name = open.find((s) => s.id === found.slotId)?.name ?? '';
        return { ...found, name, label: `${dayWords(found.day, today)} · ${name}` };
      }
    );
  });
</script>

<dialog
  bind:this={dialog}
  class="eat-sheet"
  aria-labelledby="{uid}-title"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={(event) => {
    if (event.target === dialog) onclose();
  }}
>
  {#if tub}
    <div class="body">
      <span class="grab" aria-hidden="true"></span>
      <p class="title" id="{uid}-title">Eat {tub.recipe_name} on…</p>
      {#if loading}
        <p class="hint">Looking for free meals…</p>
      {:else if failed}
        <p class="hint" role="alert">Couldn’t load the plan. Try again.</p>
      {:else if options.length === 0}
        <p class="hint">No free meal before its use-by day.</p>
      {:else}
        <ul class="meals">
          {#each options as option, i (`${option.day}-${option.slotId}`)}
            <li>
              <button
                type="button"
                data-first={i === 0 ? '' : undefined}
                onclick={() => onpick(option.day, option.slotId, option.name)}
                >{option.label}</button
              >
            </li>
          {/each}
        </ul>
      {/if}
      <button type="button" class="cancel" onclick={onclose}>Cancel</button>
    </div>
  {/if}
</dialog>

<style>
  dialog {
    inset: auto 0 0 0;
    width: 100%;
    max-width: none;
    max-height: none;
    margin: 0;
    padding: var(--space-4) var(--space-8) max(28px, env(safe-area-inset-bottom));
    border: none;
    border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-toast);
  }

  dialog::backdrop {
    background: var(--color-overlay);
  }

  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
  }

  .grab {
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .title {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
  }

  .hint {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .meals {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .meals button {
    width: 100%;
    min-height: 52px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: transparent;
    color: var(--color-text);
    font: var(--weight-bold) 1rem var(--font-ui);
    cursor: pointer;
  }

  .cancel {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-md) var(--font-ui);
    cursor: pointer;
  }

  /* A computer: a box in the middle of the screen, not a sheet the width of it. */
  @media (min-width: 768px) {
    dialog {
      inset: 0;
      width: min(420px, 100%);
      margin: auto;
      border-radius: var(--radius-xl);
    }

    .grab {
      display: none;
    }
  }
</style>
