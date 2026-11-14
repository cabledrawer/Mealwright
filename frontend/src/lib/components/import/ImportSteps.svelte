<script lang="ts">
  // The three steps of an import on a computer (mockups Import05-Desktop and
  // ImportReview05-Desktop, beside the title): 1 · Paste, 2 · Check, 3 · Save. On the review the
  // first step is done ("Link pasted ✓" or "Text pasted ✓"). A phone says "Step 1 of 3" under
  // the title instead (the page does that). A draft from Mealie (0.9.5) says "1 · From Mealie ✓"
  // (proposed, for cabledrawer).
  let { step, pasted }: { step: 1 | 2; pasted?: 'link' | 'text' | 'mealie' } = $props();

  const first = $derived(
    pasted === 'text'
      ? '1 · Text pasted ✓'
      : pasted === 'mealie'
        ? '1 · From Mealie ✓'
        : '1 · Link pasted ✓'
  );
</script>

<ol class="steps" aria-label="Import steps">
  <li class:done={step > 1} aria-current={step === 1 ? 'step' : undefined}>
    {step > 1 ? first : '1 · Paste'}
  </li>
  <li aria-current={step === 2 ? 'step' : undefined}>2 · Check</li>
  <li>3 · Save</li>
</ol>

<style>
  .steps {
    display: flex;
    gap: var(--space-3);
    margin: 0;
    padding: 0;
    list-style: none;
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
  }

  li {
    padding: var(--space-3) var(--space-6);
    border-radius: var(--radius-full);
    background: var(--color-surface);
    color: var(--color-text-muted);
  }

  li.done {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  li[aria-current='step'] {
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }
</style>
