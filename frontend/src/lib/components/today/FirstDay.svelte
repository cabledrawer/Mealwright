<script lang="ts">
  // The first-day empty state (canvas tweak "firstDay" of the Today mockups): three ways to
  // begin, whichever is easiest. Shown only while the household has no recipe, nothing in the
  // pantry and nothing planned (docs/dev/api-endpoints.md 6.3c). Words from the mockup.
  import { resolve } from '$app/paths';
</script>

<section class="ready" aria-labelledby="first-day-title" data-testid="first-day">
  <h2 id="first-day-title">Your kitchen is ready</h2>
  <p>Nothing planned yet. Start with whichever is easiest — you can do the rest later.</p>
  <a class="step" href={resolve('/(app)/recipes/import')}>
    <span class="n accent" aria-hidden="true">1</span>
    <span class="text"><b>Import a recipe</b><span>Paste a link or the recipe’s text</span></span>
  </a>
  <a class="step" href={resolve('/(app)/pantry')}>
    <span class="n" aria-hidden="true">2</span>
    <span class="text"
      ><b>Add what’s in your cupboards</b><span>Just the main things — staples can wait</span></span
    >
  </a>
  <a class="step" href={resolve('/(app)/plan')}>
    <span class="n" aria-hidden="true">3</span>
    <span class="text"
      ><b>Plan a meal</b><span>Pick a day, add a recipe or just type a dish</span></span
    >
  </a>
</section>

<style>
  .ready {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 860px;
    padding: var(--space-9);
    border-radius: var(--radius-3xl);
    background: var(--color-surface);
  }

  h2 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
    line-height: 1.5;
  }

  .step {
    display: flex;
    align-items: center;
    gap: var(--space-6);
    min-height: var(--touch-target);
    padding: var(--space-5) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-ground);
    color: var(--color-text);
    text-decoration: none;
  }

  .n {
    display: flex;
    flex: none;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border-radius: var(--radius-full);
    background: var(--color-fill-strong);
    color: var(--color-text);
    font-weight: var(--weight-extrabold);
  }

  .n.accent {
    background: var(--color-accent);
    color: var(--color-inverse-text);
  }

  .text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }

  .text b {
    font-size: 1rem;
    font-weight: var(--weight-bold);
    overflow-wrap: anywhere;
  }

  .text span {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }
</style>
