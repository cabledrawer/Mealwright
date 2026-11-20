<script lang="ts">
  // The shopping list on paper (mockup Print-ShoppingList095-A4; proposed, for cabledrawer): a
  // plain sheet of what is still to buy, every shop under its own heading and every aisle
  // under that, an empty box beside each line. Lines in the trolley are left out. Drawn only
  // while printing (lib/printing.svelte.ts); the page hides its screen parts on paper.
  import { printedOn } from '#lib/printing.svelte.js';
  import { packParts } from '#lib/shopping/packLine.js';
  import type { ShopGroup } from '#lib/shopping/view.js';
  import { plural } from '#lib/words.js';

  let {
    groups,
    builtFrom = null
  }: {
    groups: ShopGroup[];
    /** `planWords(...)` when the plan made some of the lines ("this week’s plan"). */
    builtFrom?: string | null;
  } = $props();

  const FOOT =
    'Printed from Mealwright. Ticks on paper stay on paper: tick things on your phone too, so the pantry knows.';
  const shops = $derived(groups.filter((g) => g.toBuy > 0));
  const total = $derived(shops.reduce((n, g) => n + g.toBuy, 0));
  /** One shop: its name goes in the title, as the mockup has it. */
  const single = $derived(shops.length === 1 ? shops[0]!.name : null);
  const meta = $derived(
    [
      builtFrom ? `For ${builtFrom}` : null,
      `${total} ${plural(total, 'thing', 'things')}`,
      `printed ${printedOn()}`
    ]
      .filter(Boolean)
      .join(' · ')
  );
</script>

<div class="printsheet" data-print-sheet>
  <h1>Shopping list{single ? ` · ${single}` : ''}</h1>
  {#if total === 0}
    <p class="meta">printed {printedOn()}</p>
    <h2 class="aisle">Nothing to buy</h2>
    <p class="meta">Add an item above. Ticking it puts it in the pantry.</p>
  {:else}
    <p class="meta">{meta}</p>
    {#each shops as shop (shop.shopId ?? 'any')}
      {#if !single}<h2 class="shop">{shop.name}</h2>{/if}
      {#each shop.aisles as aisle (aisle.key)}
        {#if aisle.items.length}
          <svelte:element this={single ? 'h2' : 'h3'} class="aisle">{aisle.name}</svelte:element>
          <table>
            <tbody>
              {#each aisle.items as view (view.item.id)}
                <tr>
                  <td class="box"><span aria-hidden="true"></span></td>
                  <td>{view.food.name}</td>
                  <td class="qty"
                    >{packParts(view.food, view.item.amount, view.item.size_id)?.buy ??
                      view.item.display ??
                      ''}</td
                  >
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      {/each}
    {/each}
    <div class="foot">{FOOT}</div>
  {/if}
</div>

<style>
  .printsheet {
    display: none;
  }

  @media print {
    .printsheet {
      display: block;
      font-family: var(--font-ui);
      color: #1a1f1c;
      background: #fff;
      font-size: 16px;
      line-height: 1.55;
    }
    h1 {
      margin: 0;
      font-size: 32px;
      font-weight: 800;
      letter-spacing: -0.02em;
      text-wrap: balance;
      break-after: avoid;
    }
    .meta {
      margin: 6px 0 0;
      font-size: var(--text-md);
      color: #4a524d;
    }
    h2,
    h3 {
      margin: 28px 0 8px;
      font-size: var(--text-2xl);
      font-weight: 800;
      text-wrap: balance;
      break-after: avoid;
    }
    /* A shop's name is bigger than an aisle's; it never sits alone at the foot of a page. */
    h2.shop {
      margin-top: 36px;
      padding-top: 10px;
      border-top: 2px solid #1a1f1c;
      font-size: 22px;
    }
    h2.shop + h3 {
      margin-top: 12px;
    }
    table {
      border-collapse: collapse;
      width: 100%;
    }
    tr {
      break-inside: avoid;
    }
    td {
      padding: 7px 6px;
      border-bottom: 1px solid #c9cfcb;
      vertical-align: top;
      font-size: var(--text-lg);
    }
    td.box {
      width: 22px;
    }
    .box span {
      display: inline-block;
      width: 14px;
      height: 14px;
      margin-top: 3px;
      border: 1.5px solid #1a1f1c;
      border-radius: 3px;
    }
    td.qty {
      width: 120px;
      text-align: right;
      white-space: nowrap;
      color: #2f3632;
    }
    .foot {
      margin-top: 32px;
      padding-top: 10px;
      border-top: 1px solid #c9cfcb;
      font-size: var(--text-sm);
      color: #4a524d;
      break-inside: avoid;
    }
  }
</style>
