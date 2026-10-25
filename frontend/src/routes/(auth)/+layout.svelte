<script lang="ts">
  // Sign in and first-run setup: the logo, one card, and the reminder that everything
  // stays on the household's own server (from the SignIn-* mockups).
  import type { Snippet } from 'svelte';
  import Logo from '#lib/components/Logo.svelte';

  let { children }: { children: Snippet } = $props();
</script>

<div class="page">
  <div class="brand">
    <Logo size={56} />
    <span class="wordmark">Mealwright</span>
  </div>

  <main class="card">
    {@render children()}
  </main>

  <p class="private">
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2.2"
      stroke-linecap="round"
      stroke-linejoin="round"
    >
      <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z" />
      <path d="M9 12l2 2 4-4" />
    </svg>
    Your own server · nothing is sent anywhere else
  </p>
</div>

<style>
  .page {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 22px;
    min-height: 100dvh;
    padding: max(48px, env(safe-area-inset-top)) var(--space-9)
      max(var(--space-9), env(safe-area-inset-bottom));
  }

  .brand {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-5);
  }

  .wordmark {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-tight);
    word-spacing: normal;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: 18px;
    width: 100%;
    max-width: 440px;
  }

  .private {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    margin-top: auto;
    color: var(--color-note-text);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    text-align: center;
  }

  @media (min-width: 768px) {
    .page {
      justify-content: center;
      gap: var(--space-9);
      padding: var(--space-11) var(--space-9);
    }

    .brand {
      flex-direction: row;
      gap: var(--space-6);
    }

    .wordmark {
      font-size: 1.75rem;
    }

    .card {
      padding: var(--space-10);
      border-radius: 28px;
      background: var(--color-surface);
      box-shadow: 0 1px 0 var(--color-border);
    }

    .private {
      margin-top: 0;
    }
  }
</style>
