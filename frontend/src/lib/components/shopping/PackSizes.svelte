<script lang="ts">
  import '#lib/styles/fields.css';
  import Loading from '#lib/components/Loading.svelte';
  // "Which size?" for one Shopping line (mockup Dark-ShopPackAlt08-Phone; F183 + F204, cabledrawer
  // 9 Nov): every size the line could be bought in and how much each leaves over, with the one
  // that leaves least marked. Picking one changes the line to that many of that size ("Use
  // this"); a switch makes it the ingredient's usual size too. Loaded the first time a row's
  // size is tapped (the page size limit).
  import { onMount, tick } from 'svelte';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';
  import Sheet from '#lib/components/Sheet.svelte';
  import { getPackSizes, type PackChoice, type PackSizes } from '#lib/client/foods.js';
  import { network } from '#lib/network.svelte.js';
  import { radioKeys } from '#lib/radioKeys.js';
  import { useSize } from '#lib/shopping/useSize.js';
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import type { ListItem, ShopFood } from '#lib/shopping/types.js';
  import Switch from '../Switch.svelte';
  import { couldntLoad } from '#lib/errorWords.js';

  let {
    model,
    item,
    food,
    onclose
  }: { model: ShoppingModel; item: ListItem; food: ShopFood; onclose: () => void } = $props();

  let body: HTMLElement | undefined;
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
  const needsServer = $derived(
    !!choice && (choice.size_id === null || (makeUsual && !choice.usual))
  );

  function over(c: PackChoice): string {
    const parts = [];
    if (c.usual) parts.push('Your usual');
    parts.push(
      c.over === 'nothing left over' ? 'Nothing over' : c.over.replace(' left over', ' over')
    );
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

  onMount(() => {
    void tick().then(() => body?.querySelector<HTMLElement>('[role="radio"]')?.focus());
  });
</script>

<Sheet
  title="{food.name}{sheet?.need ? ` · ${sheet.need}` : ''}"
  label="{food.name}: which size?"
  size="small"
  {onclose}
>
  <div class="body" bind:this={body}>
    <p class="sub">Sizes sold in UK shops</p>
    {#if failed}
      <p class="mw-error" role="alert">{couldntLoad('the sizes')}</p>
    {:else if !sheet}
      <Loading />
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
            {#if c.chosen}<span class="tag">On the list</span>{:else if c.least}<span
                class="tag good">Least left over</span
              >{/if}
          </button>
        {/each}
      </div>
      <label class="usual">
        <Switch bind:checked={makeUsual} label="Make the one I pick my usual size" />
        <span>Make the one I pick my usual size</span>
      </label>
    {/if}
    {#if problem}<p class="mw-error" role="alert">{problem}</p>{/if}
    {#if needsServer && network.offline}
      <p class="sub">A new size needs your Mealwright server. Try again when it answers.</p>
    {/if}
    <ButtonRow>
      <Button
        disabled={!choice || busy || (needsServer && network.offline)}
        onclick={() => void use()}>Use this</Button
      >
      <Button quiet onclick={onclose}>Cancel</Button>
    </ButtonRow>
  </div>
</Sheet>

<style>
  .body {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
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
</style>
