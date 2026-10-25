<script lang="ts">
  // "Did you buy 2?" (mockup Shop): a card, never a pop-up. The first answer settles it for
  // everyone. The words come from the server (sync-protocol section 8).
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import type { Question } from '#lib/shopping/types.js';

  let { model, question }: { model: ShoppingModel; question: Question } = $props();
  const uid = $props.id();
</script>

<section class="card" aria-labelledby="{uid}-t">
  <div class="top">
    <span class="badge" aria-hidden="true">
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        ><circle cx="9" cy="8" r="3.2" /><path d="M3 20a6 6 0 0 1 12 0" /><circle
          cx="17"
          cy="9"
          r="2.6"
        /><path d="M15.5 14.2A5 5 0 0 1 21 19" /></svg
      >
    </span>
    <div class="words">
      <span class="title" id="{uid}-t">{question.title}</span>
      <span class="text">{question.text}</span>
    </div>
  </div>
  <div class="buttons">
    <button type="button" class="yes" onclick={() => void model.answerCard(question.id, 'two')}
      >{question.yes}</button
    >
    <button type="button" class="no" onclick={() => void model.answerCard(question.id, 'one')}
      >{question.no}</button
    >
  </div>
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
    border-radius: 18px;
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

  .buttons {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .buttons button {
    min-height: var(--touch-target);
    border: none;
    border-radius: var(--radius-lg);
    font: var(--weight-bold) var(--text-lg) var(--font-ui);
    cursor: pointer;
  }

  .yes {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .no {
    background: var(--color-fill);
    color: var(--color-text);
  }
</style>
