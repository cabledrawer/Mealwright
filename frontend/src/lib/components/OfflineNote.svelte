<script lang="ts">
  // What an online-only screen shows while the server can't be reached (spec section 6,
  // "Opening the app offline", cabledrawer 18 Oct). Pantry, Ingredients and Settings need the
  // server in 0.3; the shopping list works from the phone's copy, so point there.
  import { resolve } from '$app/paths';

  let {
    screen
  }: { screen: 'Pantry' | 'Ingredients' | 'Recipes' | 'Drafts' | 'Settings' | 'Privacy' | 'Plan' } =
    $props();
</script>

<section class="offline" aria-labelledby="offline-note-title">
  <h2 id="offline-note-title">You’re offline.</h2>
  <p>{screen} needs your Mealwright server. Your shopping list works offline.</p>
  <a class="shopping" href={resolve('/(app)/shopping')}>Shopping</a>
</section>

<style>
  .offline {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    max-width: 860px;
    padding: var(--space-8);
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

  .shopping {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 54px;
    padding: 0 var(--space-8);
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    text-decoration: none;
  }

  @media (min-width: 768px) {
    .offline {
      padding: 28px;
    }
  }
</style>
