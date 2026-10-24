<script lang="ts">
  // "Import a recipe", step 1 (mockups Import05-Phone and Import05-Desktop and their dark
  // versions, spec section 6 "One box"): one box that takes a link or pasted recipe text, and
  // Mealwright works out which. A link needs "Recipe import from links" to be on; pasted text
  // never goes online. Online only: offline, the box says it needs the server and nothing is
  // queued. Under "How it works", a note says photos aren't downloaded while that switch is
  // off (`photosOff`: true only when the server has said so, never on a guess).
  import { tick } from 'svelte';
  import Icon from '$lib/components/Icon.svelte';
  import { network } from '$lib/network.svelte';
  import { OFFLINE_NOTE, type ImportFlow } from '$lib/import.svelte';

  import '$lib/styles/fields.css';
  let { flow, photosOff = false }: { flow: ImportFlow; photosOff?: boolean } = $props();

  const uid = $props.id();
  let box = $state<HTMLTextAreaElement>();
  const reading = $derived(flow.phase === 'reading');
  const typed = $derived(flow.text.trim() !== '');
  const kind = $derived(!typed ? null : flow.isLink ? 'link' : 'text');

  /** "Paste text instead": empty the box of the link and put the cursor back in it. */
  async function pasteInstead() {
    flow.text = '';
    flow.problem = null;
    await tick();
    box?.focus();
  }
</script>

<form
  class="start"
  onsubmit={(e) => {
    e.preventDefault();
    void flow.read();
  }}
>
  <div class="card">
    <label class="mw-label big" for="{uid}-box">Paste a link or the recipe’s text</label>
    <textarea
      id="{uid}-box"
      bind:this={box}
      class="mw-input box"
      rows="6"
      placeholder="https://… or the title, ingredients and method"
      aria-describedby="{uid}-kind"
      aria-invalid={flow.problem && !flow.problem.switchedOff ? true : undefined}
      readonly={reading}
      bind:value={flow.text}></textarea>

    <p class="kind" id="{uid}-kind" aria-live="polite">
      {#if kind === 'link'}
        <span class="chip good"
          ><Icon name="link" size={18} stroke={2.2} />A link · your server visits this page once</span
        >
      {:else if kind === 'text'}
        <span class="chip"
          ><Icon name="note" size={18} stroke={2.2} />Pasted text · nothing goes online</span
        >
      {/if}
    </p>

    {#if network.offline}
      <p class="offline" role="status">{OFFLINE_NOTE}</p>
    {/if}

    {#if flow.problem}
      {#if flow.problem.switchedOff}
        <div class="alert" role="alert">
          <p class="title">Importing from links is switched off</p>
          <p>
            Nothing was fetched.
            {#if flow.problem.admin}Switch it on in Settings → Privacy, or paste the recipe’s text
              instead; pasted text never goes online.{:else}An admin can switch it on in Settings →
              Privacy. You can paste the recipe’s text instead; pasted text never goes online.{/if}
          </p>
          <p class="actions">
            {#if flow.problem.admin}
              <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- Settings → Privacy is built beside this page -->
              <a class="button" href="/settings/privacy">Open Settings</a>
            {/if}
            <button type="button" class="ghost" onclick={() => void pasteInstead()}
              >Paste text instead</button
            >
          </p>
        </div>
      {:else}
        <div class="alert plain" role="alert">
          <p class="title">{flow.problem.message}</p>
          {#if flow.problem.code === 'import_switched_off' || /^(bad_link|not_a_page|no_recipe|cant_read)$/.test(flow.problem.code)}
            <p class="actions">
              <button type="button" class="ghost" onclick={() => void pasteInstead()}
                >Paste text instead</button
              >
            </p>
          {/if}
        </div>
      {/if}
    {/if}

    <button class="read" type="submit" disabled={reading || !typed || network.offline}>
      {reading ? 'Reading…' : 'Read the recipe'}
    </button>
    <p class="visually-hidden" role="status">{reading ? 'Reading the recipe' : ''}</p>
  </div>

  <aside class="how" aria-label="How it works">
    <p class="overline">How it works</p>
    <p>
      <b>A link:</b> your Mealwright server reads the page and shows you what it found. Nothing is saved
      until you choose.
    </p>
    <p>
      <b>Pasted text:</b> the title, ingredients and method, copied from anywhere. Nothing goes online.
    </p>
  </aside>

  {#if photosOff}
    <p class="photos">
      Recipe photos: not downloaded.
      <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- Settings → Privacy is built beside this page -->
      <a href="/settings/privacy">Change in Settings → Privacy</a>
    </p>
  {/if}
</form>

<style>
  .start {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 760px;
  }

  .card {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-7);
    border-radius: var(--radius-3xl);
    background: var(--color-surface);
  }

  .big {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
    color: var(--color-text);
  }

  .box {
    min-height: 8.5rem;
    resize: vertical;
    padding: var(--space-6);
    border: 2px solid var(--color-accent);
    border-radius: var(--radius-xl);
    font-size: 1rem;
    line-height: 1.45;
  }

  .kind {
    min-height: 0;
  }

  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-chip);
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .chip.good {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .offline {
    padding: var(--space-5);
    border-radius: var(--radius-lg);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-md);
  }

  .alert {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6);
    border: 1px solid var(--color-warning-border);
    border-radius: var(--radius-xl);
    background: var(--color-warning);
    color: var(--color-warning-text);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .alert .title {
    font-size: var(--text-lg);
    font-weight: var(--weight-extrabold);
  }

  .alert.plain {
    border-color: var(--color-danger);
    background: var(--color-surface);
    color: var(--color-text);
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .button,
  .ghost {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border-radius: var(--radius-lg);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    text-decoration: none;
    cursor: pointer;
  }

  .button {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .ghost {
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .read {
    min-height: 54px;
    border: none;
    border-radius: var(--radius-button);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .read:disabled {
    opacity: 0.55;
    cursor: default;
  }

  .how {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: var(--space-6) var(--space-7);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .photos {
    padding: 0 var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-md);
    line-height: 1.45;
  }

  .photos a {
    color: var(--color-accent);
    font-weight: var(--weight-bold);
  }

  .overline {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }
</style>
