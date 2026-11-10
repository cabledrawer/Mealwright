<script lang="ts">
  // "Which size?" for one Shopping line (mockup Dark-ShopPackAlt08-Phone; F183 + F204, cabledrawer
  // 9 Nov): every size the line could be bought in and how much each leaves over, with the one
  // that leaves least marked. Picking one changes the line to that many of that size ("Use
  // this"); a switch makes it the ingredient's usual size too. Loaded the first time a row's
  // size is tapped (the page size limit).
  import { tick } from 'svelte';
  import { getPackSizes, type PackChoice, type PackSizes } from '#lib/client/foods.js';
  import { network } from '#lib/network.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import { useSize } from '#lib/shopping/useSize.js';
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import type { ListItem, ShopFood } from '#lib/shopping/types.js';
  import Switch from '../Switch.svelte';

  let {
    model,
    item,
    food,
    onclose
  }: { model: ShoppingModel; item: ListItem; food: ShopFood; onclose: () => void } = $props();

  const uid = $props.id();
  let dialog: HTMLDialogElement;
  let sheet = $state<PackSizes | null>(null);
  let failed = $state(false);
  let picked = $state<number | null>(null);
  let makeUsual = $state(false);
  let busy = $state(false);
  let problem = $state<string | null>(null);

  $effect(() => {
    void getPackSizes(item.id)
      .then((answer) => {
        sheet = answer;
        const current = answer.choices.findIndex((c) => c.chosen);
        picked = current >= 0 ? current : 0;
      })
      .catch(() => (failed = true));
  });

  const choice = $derived<PackChoice | null>(
    sheet && picked !== null ? (sheet.choices[picked] ?? null) : null
  );
  /** Making a size, or the usual size, needs the server; a size the ingredient has doesn't. */
  const needsServer = $derived(!!choice && (choice.size_id === null || (makeUsual && !choice.usual)));

  function over(c: PackChoice): string {
    const parts = [];
    if (c.usual) parts.push('Your usual');
    parts.push(c.over === 'nothing left over' ? 'Nothing over' : c.over.replace(' left over', ' over'));
    return parts.join(' · ');
  }

  async function use() {
    if (!choice || busy) return;
    busy = true;
    problem = null;
    try {
      await useSize(model, item, food.id, choice, makeUsual);
      onclose();
    } catch {
      problem = 'Couldn’t change the size. Try again.';
      busy = false;
    }
  }

  $effect(() => {
    if (!dialog.open) {
      dialog.showModal();
      void tick().then(() => dialog.querySelector<HTMLElement>('[role="radio"]')?.focus());
    }
  });
</script>

<dialog
  bind:this={dialog}
  class="sizes-sheet"
  aria-label="{food.name}: which size?"
  oncancel={(event) => {
    event.preventDefault();
    onclose();
  }}
  onclick={(event) => {
    if (event.target === dialog) onclose();
  }}
>
  <div class="body">
    <span class="grab" aria-hidden="true"></span>
    <div class="head">
      <p class="title">{food.name}{sheet?.need ? ` · ${sheet.need}` : ''}</p>
      <p class="sub">Sizes sold in UK shops</p>
    </div>
    {#if failed}
      <p class="problem" role="alert">Couldn’t load the sizes. Try again.</p>
    {:else if !sheet}
      <p class="sub" aria-busy="true">Loading…</p>
    {:else}
      <div class="choices" role="radiogroup" aria-label="Sizes" use:radioKeys>
        {#each sheet.choices as c, index (c.name + c.amount)}
          <button
            type="button"
            role="radio"
            aria-checked={picked === index}
            onclick={() => (picked = index)}
          >
            <span class="what">
              <b>{c.buy}</b>
              <span>{over(c)}</span>
            </span>
            {#if c.chosen}<span class="tag">On the list</span>{:else if c.least}<span class="tag good"
                >Least left over</span
              >{/if}
          </button>
        {/each}
      </div>
      <label class="usual">
        <Switch bind:checked={makeUsual} label="Make the one I pick my usual size" />
        <span>Make the one I pick my usual size</span>
      </label>
    {/if}
    {#if problem}<p class="problem" role="alert">{problem}</p>{/if}
    <button
      type="button"
      class="put"
      disabled={!choice || busy || (needsServer && network.offline)}
      onclick={() => void use()}>Use this</button
    >
    {#if needsServer && network.offline}
      <p class="sub">A new size needs your Mealwright server. Try again when it answers.</p>
    {/if}
    <button type="button" class="cancel" onclick={onclose}>Cancel</button>
  </div>
</dialog>

<style>
  dialog {
    max-width: none;
    max-height: min(90dvh, 40rem);
    margin: 0;
    padding: 0;
    border: none;
    background: var(--color-surface);
    color: var(--color-text);
    box-shadow: var(--shadow-toast);
    overflow-y: auto;
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
    display: none;
    align-self: center;
    width: 40px;
    height: 5px;
    border-radius: 3px;
    background: var(--color-border-strong);
  }

  .title {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    overflow-wrap: anywhere;
  }

  .sub {
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .choices {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .choices button {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-4);
    min-height: var(--touch-target);
    padding: var(--space-3) var(--space-6);
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-lg);
    background: var(--color-surface);
    color: var(--color-text);
    font: var(--weight-semibold) var(--text-base) var(--font-ui);
    text-align: left;
    cursor: pointer;
  }

  .choices button[aria-checked='true'] {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .what {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .what span {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-regular, 400);
  }

  .tag {
    flex: none;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .tag.good {
    color: var(--color-accent);
  }

  .usual {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    min-height: var(--touch-target);
    color: var(--color-text);
    font-size: var(--text-base);
  }

  .problem {
    color: var(--color-warning-text);
    font-size: var(--text-md);
  }

  .put {
    min-height: 52px;
    border: none;
    border-radius: var(--radius-lg);
    background: var(--color-text);
    color: var(--color-surface);
    font: var(--weight-extrabold) 1rem var(--font-ui);
    cursor: pointer;
  }

  .put:disabled {
    opacity: 0.5;
    cursor: default;
  }

  .cancel {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }

  @media (max-width: 767px) {
    dialog {
      inset: auto 0 0 0;
      width: 100%;
      padding: var(--space-4) var(--space-8) max(28px, env(safe-area-inset-bottom));
      border-radius: var(--radius-sheet) var(--radius-sheet) 0 0;
    }

    .grab {
      display: block;
    }
  }

  @media (min-width: 768px) {
    dialog {
      width: 380px;
      margin: auto;
      padding: var(--space-8);
      border: 1px solid var(--color-border);
      border-radius: var(--radius-lg);
    }
  }
</style>
