<script lang="ts">
  // One ingredient line on the recipe page (mockups Recipe and Dark-Phone-Recipe): a dot, the
  // amount in bold and the line's own words, and at the end where it is ("Cupboard", "On
  // list", "Staple"). The ingredient's own name shows in small text only when it differs from
  // the words (cabledrawer 19 Oct, question 14); words that are only the start of its name ("thu")
  // show as the name itself ("Toor Dal", cabledrawer 25 Oct). A line linked to an ingredient opens the
  // ingredient editor; a line that uses another recipe opens that recipe; a line linked to
  // nothing is plain text.
  import { resolve } from '$app/paths';
  import type { RecipeLine } from '#lib/client/recipes.js';
  import type { Mark } from '#lib/recipeStock.js';
  import { linkedWords } from '#lib/recipes/linkedWords.js';

  let {
    line,
    amount,
    mark,
    onopen
  }: {
    line: RecipeLine;
    /** "200 g", "1½ cups" (already scaled), or null. */
    amount: string | null;
    mark: Mark | null;
    /** Open the ingredient editor for the linked ingredient. */
    onopen: (foodId: number) => void;
  } = $props();

  /** Between the bold amount and the words (a plain space). */
  const SPACE = ' ';
  const words = $derived(linkedWords(line.words, line.food));
  const ownName = $derived(line.food?.name ?? line.recipe?.name ?? null);
  /** The name in small text: only when it is not what the line already says. */
  const smallName = $derived(
    ownName && ownName.trim().toLowerCase() !== words.trim().toLowerCase() ? ownName : null
  );
  /** A link that has gone: the line keeps its words, and says why it opens nothing. */
  const gone = $derived(
    line.link === 'recipe_removed' ? 'recipe removed' : line.link === 'none' ? 'not linked' : null
  );
  const small = $derived(gone ?? smallName);
</script>

{#snippet inside()}
  <span class="dot {mark?.kind ?? 'none'}" aria-hidden="true"></span>
  <span class="text">
    <span class="main"
      >{#if amount}<b>{amount}</b>{SPACE}{/if}{words}{#if line.note}<span class="note"
          >, {line.note}</span
        >{/if}</span
    >
    {#if small}<span class="small">{small}</span>{/if}
  </span>
  {#if line.optional}<span class="opt">Optional</span>{/if}
  {#if mark}
    <span class="label {mark.kind}"
      >{#if mark.label}{mark.label}{:else}<span class="visually-hidden">Missing</span>{/if}</span
    >
  {/if}
{/snippet}

{#if line.link === 'ingredient' && line.food}
  {@const food = line.food}
  <button type="button" class="line" onclick={() => onopen(food.id)}>{@render inside()}</button>
{:else if line.link === 'recipe' && line.recipe}
  <a class="line" href={resolve('/(app)/recipes/[id]', { id: String(line.recipe.id) })}
    >{@render inside()}</a
  >
{:else}
  <div class="line plain">{@render inside()}</div>
{/if}

<style>
  .line {
    display: flex;
    align-items: center;
    gap: var(--space-5);
    width: 100%;
    min-height: var(--touch-target);
    padding: var(--space-3) 0;
    border: none;
    background: transparent;
    color: var(--color-text);
    font: inherit;
    text-align: left;
    text-decoration: none;
  }

  button.line,
  a.line {
    cursor: pointer;
  }

  .dot {
    flex: none;
    width: 10px;
    height: 10px;
    border-radius: 5px;
    box-sizing: border-box;
  }

  .dot.in {
    background: var(--color-accent);
  }

  .dot.list {
    background: var(--color-on-list-dot);
  }

  .dot.staple {
    border: 2px solid var(--color-field-border);
  }

  .dot.short,
  .dot.missing {
    border: 2px dashed var(--color-use-soon-text);
  }

  /* A line the stock check skips (no amount, nothing linked): the space stays, for alignment. */
  .dot.none {
    visibility: hidden;
  }

  .text {
    display: flex;
    flex: 1;
    flex-direction: column;
    min-width: 0;
  }

  .main {
    font-size: var(--text-lg);
    overflow-wrap: anywhere;
  }

  .main b {
    font-weight: var(--weight-bold);
  }

  .note {
    color: var(--color-text-muted);
  }

  .small {
    color: var(--color-text-muted);
    font-size: var(--text-md);
    overflow-wrap: anywhere;
  }

  /* The "Optional" pill (R3, mockup RecipeOptional08). */
  .opt {
    flex: none;
    padding: 2px var(--space-4);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .label {
    flex: none;
    max-width: 40%;
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
    text-align: right;
    overflow-wrap: anywhere;
  }

  .label.in {
    color: var(--color-accent);
  }

  .label.list {
    color: var(--color-on-list);
  }

  .label.staple {
    color: var(--color-text-muted);
  }

  .label.short {
    color: var(--color-use-soon-text);
  }

  /* On paper: no pantry dots or marks, and the line is not a button. */
  @media print {
    .dot,
    .label {
      display: none;
    }
  }
</style>
