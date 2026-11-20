<script lang="ts">
  import Icon from '../Icon.svelte';
  // "Did you buy 2?" (mockup Shop): a card, never a pop-up. The first answer settles it for
  // everyone. The words come from the server (sync-protocol section 8).
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import type { Question } from '#lib/shopping/types.js';
  import Button from '#lib/components/Button.svelte';
  import ButtonRow from '#lib/components/ButtonRow.svelte';

  let { model, question }: { model: ShoppingModel; question: Question } = $props();
  const uid = $props.id();
</script>

<section class="card" aria-labelledby="{uid}-t">
  <div class="top">
    <span class="badge" aria-hidden="true">
      <Icon name="people" size={18} />
    </span>
    <div class="words">
      <span class="title" id="{uid}-t">{question.title}</span>
      <span class="text">{question.text}</span>
    </div>
  </div>
  <ButtonRow>
    <Button quiet onclick={() => void model.answerCard(question.id, 'one')}>{question.no}</Button>
    <Button onclick={() => void model.answerCard(question.id, 'two')}>{question.yes}</Button>
  </ButtonRow>
</section>

<style>
  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    padding: 14px;
    border: 1.5px solid #9fcdb4;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .top {
    display: flex;
    align-items: flex-start;
    gap: var(--space-6);
  }

  .badge {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    border-radius: var(--radius-xl);
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .words {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .title {
    font-size: 1rem;
    font-weight: var(--weight-extrabold);
  }

  .text {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    line-height: 1.45;
  }
</style>
