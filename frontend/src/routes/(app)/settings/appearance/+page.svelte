<script lang="ts">
  import PageHeader from '#lib/components/PageHeader.svelte';
  import ThemeSwitch from '#lib/components/ThemeSwitch.svelte';
  import { checkMode, type CheckMode } from '#lib/checkMode.svelte.js';

  /** The two ways Check can look on the phone (F141; words are the mockup's). */
  const CHECK_MODE_CHOICES: { value: CheckMode; label: string; hint: string }[] = [
    {
      value: 'focus',
      label: 'Focus',
      hint: 'The whole list, with the app’s menu hidden. Close keeps it in Drafts.'
    },
    {
      value: 'one',
      label: 'One at a time',
      hint: 'Each line that needs you, then every step of the method. Back and Next.'
    }
  ];
</script>

<PageHeader
  title="Appearance"
  overline="You"
  subtitle="Theme and how the app looks on this device."
  parent={{ href: '/(app)/settings', label: 'Settings' }}
/>

<!-- Appearance works offline: the theme is saved on this device (cabledrawer 18 Oct: "Keep it
     visible"). -->
<section class="section" aria-label="Appearance">
  <div class="card">
    <div class="row">
      <span class="label">Theme</span>
      <ThemeSwitch variant="pill" />
    </div>
    <!-- F141 (cabledrawer 3 Nov), mockup Dark-SettingsCheckMode07-Phone: how Check looks on the
         phone, kept on this device. Shown at every width; the line under it says a computer
         always shows the whole list (the mockup is phone-only, so showing it on a computer too is
         cabledrawer 5 Nov). -->
    <fieldset class="check-mode">
      <legend>Checking a recipe on the phone</legend>
      <span class="detail">How the Check screen looks after an import.</span>
      {#each CHECK_MODE_CHOICES as option (option.value)}
        <label class="choice" class:on={checkMode.choice === option.value}>
          <input
            type="radio"
            name="checkmode"
            value={option.value}
            checked={checkMode.choice === option.value}
            onchange={() => checkMode.set(option.value)}
          />
          <span class="dot" aria-hidden="true"></span>
          <span class="choice-words">
            <span class="choice-name">{option.label}</span>
            <span class="choice-hint">{option.hint}</span>
          </span>
        </label>
      {/each}
      <span class="detail small">On a computer, Check always shows the whole list.</span>
    </fieldset>
  </div>
</section>

<style>
  .section {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 760px;
  }

  .card {
    padding: var(--space-1) var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-6);
    min-height: 54px;
    padding: var(--space-4) 0;
  }

  .detail {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .label {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .check-mode {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
    margin: 0;
    padding: var(--space-5) 0 var(--space-6);
    border: none;
    border-top: 1px solid var(--color-border);
  }

  .check-mode legend {
    padding: 0;
    margin-bottom: var(--space-2);
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .check-mode .small {
    font-size: var(--text-xs);
  }

  .choice {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: var(--space-6);
    min-height: var(--touch-target);
    padding: var(--space-6);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    cursor: pointer;
  }

  .choice.on {
    border-color: var(--color-accent);
    background: var(--color-accent-soft);
  }

  /* The real radio is invisible and covers the card (so the whole card is the target); the dot
     draws it. */
  .choice input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  .dot {
    flex: none;
    width: 22px;
    height: 22px;
    margin-top: 2px;
    border: 2px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    box-sizing: border-box;
  }

  .choice input:checked + .dot {
    border: 6px solid var(--color-accent);
  }

  .choice input:focus-visible + .dot {
    outline: 2px solid var(--color-accent);
    outline-offset: 2px;
  }

  .choice-words {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .choice-name {
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
  }

  .choice-hint {
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    line-height: 1.45;
  }
</style>
