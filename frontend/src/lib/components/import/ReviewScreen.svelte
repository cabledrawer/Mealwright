<script lang="ts">
  // "Check before saving" (mockups Import05-Phone and Import05-Desktop, ImportReview05-*, and
  // their dark versions; spec "Import review" and "The labels"): the recipe's name, serves and
  // time, whether its photo came, the counts, every ingredient line as written → how it was
  // read → what's in your kitchen, and Save. "Nothing is saved until you choose." Save & plan
  // it stays hidden until 0.6 (cabledrawer 21 Oct).
  //
  // Leaving without saving (Cancel, the back link, a tab, the browser's Back) asks "Save as a
  // draft?" (mockup Import05-*, the leave sheet; spec "Import drafts"): Save draft · Keep
  // checking · Discard. A draft that was opened and not changed just leaves. Closing or
  // reloading the tab can't be asked about, so that leaves as it always did.
  import { beforeNavigate, goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { changesToast } from '$lib/import.save';
  import { leftOutWords, type ImportFlow } from '$lib/import.svelte';
  import { network } from '$lib/network.svelte';
  import Icon from '$lib/components/Icon.svelte';
  import LeaveSheet from './LeaveSheet.svelte';
  import ReviewLineRow from './ReviewLineRow.svelte';

  import '$lib/styles/fields.css';
  let { flow, phone = false }: { flow: ImportFlow; phone?: boolean } = $props();

  const review = $derived(flow.review!);
  const uid = $props.id();
  const ingredientCount = $derived(review.lines.filter((l) => l.kind === 'ingredient').length);

  async function save() {
    const saved = await flow.save();
    if (!saved) return;
    changesToast(saved);
    await goto(resolve('/(app)/recipes/[id]', { id: String(saved.recipe.id) }));
  }

  function leave() {
    void goto(resolve('/(app)/recipes'));
  }

  // --- Leaving without saving -------------------------------------------------------------
  let asking = $state(false);
  /** Where the person was going when the question came up. */
  let target: URL | null = null;
  /** The question was answered: this leave goes through. */
  let allowed = false;

  beforeNavigate((navigation) => {
    if (allowed || flow.saved || !flow.unkept || !navigation.to) return;
    if (navigation.willUnload) return; // closing the tab: the browser's own, nothing to ask
    navigation.cancel();
    target = navigation.to.url;
    flow.draftProblem = null;
    asking = true;
  });

  async function goOn(url: URL) {
    allowed = true;
    asking = false;
    // eslint-disable-next-line svelte/no-navigation-without-resolve -- the address the person was already going to
    await goto(url);
    allowed = false;
  }

  async function keep() {
    if (!(await flow.keepAsDraft()) || !target) return;
    // Leaving through Cancel or the back link lands on the Drafts list (the mockup's Save draft).
    const toRecipes = target.pathname === resolve('/(app)/recipes') && target.search === '';
    await goOn(toRecipes ? new URL(resolve('/(app)/recipes/drafts'), target) : target);
  }

  function discard() {
    if (target) void goOn(target);
  }
</script>

<div class="review" class:phone>
  <section class="top" aria-label="Recipe details">
    {#if review.photo.state === 'downloaded' && review.photo.photo}
      <img
        class="photo"
        src={review.photo.photo.url}
        width={review.photo.photo.width}
        height={review.photo.photo.height}
        alt="Downloaded from the page"
      />
    {:else if review.photo.state === 'off' || review.photo.state === 'failed'}
      <div class="photo none" role="img" aria-label="No photo">
        <Icon name="photo" size={phone ? 24 : 28} stroke={2} />
      </div>
    {/if}
    <div class="fields">
      <label class="field" for="{uid}-name">
        <span>Name</span>
        <input
          id="{uid}-name"
          class="mw-input title"
          type="text"
          maxlength="200"
          bind:value={flow.name}
        />
      </label>
      <div class="two">
        <label class="field" for="{uid}-serves">
          <span>Serves</span>
          <input
            id="{uid}-serves"
            class="mw-input"
            type="text"
            inputmode="numeric"
            maxlength="2"
            bind:value={flow.serves}
          />
        </label>
        <label class="field" for="{uid}-time">
          <span>Minutes</span>
          <input
            id="{uid}-time"
            class="mw-input"
            type="text"
            inputmode="numeric"
            maxlength="5"
            bind:value={flow.minutes}
          />
        </label>
      </div>
      {#if review.nutrition.kcal !== null}
        <p class="found">Nutrition found · {review.nutrition.kcal} kcal per serving</p>
      {/if}
      {#if review.source.kind === 'link' && review.source.site}
        <p class="muted">
          From {review.source.site}{review.author ? ` · by ${review.author}` : ''}
        </p>
      {/if}
    </div>
  </section>

  {#if review.photo.state === 'off' || review.photo.state === 'failed'}
    <p class="photo-note">
      {#if review.photo.state === 'off'}
        <b>Photo not downloaded.</b> Photo downloads are off in
        <!-- eslint-disable-next-line svelte/no-navigation-without-resolve -- Settings → Privacy is built beside this page -->
        <a href="/settings/privacy">Settings → Privacy</a>. You can add your own photo later.
      {:else}
        <b>Photo not downloaded</b>
        — {review.photo.message} You can add your own photo later.
      {/if}
    </p>
  {/if}

  <div class="counts" aria-label="What was found">
    <span class="count good">{review.counts.matched} matched</span>
    <span class="count warn">{review.counts.to_confirm} to confirm</span>
    <span class="count bad"
      >{review.counts.needs_you} {review.counts.needs_you === 1 ? 'needs' : 'need'} you</span
    >
    <span class="count"
      >{review.counts.staple} {review.counts.staple === 1 ? 'staple' : 'staples'}</span
    >
  </div>

  <section class="lines" aria-labelledby="{uid}-ingredients">
    <h2 id="{uid}-ingredients">Ingredients <span class="muted">· {ingredientCount}</span></h2>
    {#if !phone}
      <p class="columns" aria-hidden="true">
        <span>As written → how Mealwright reads it → in your kitchen</span>
      </p>
    {/if}
    <ul>
      {#each review.lines as line, index (index)}
        <ReviewLineRow
          {flow}
          {index}
          {line}
          problem={flow.saveProblem?.line === index ? flow.saveProblem.message : null}
        />
      {/each}
    </ul>
    {#if review.lines_cut}
      <p class="note">The page had more than 200 ingredient lines. The first 200 are here.</p>
    {/if}
  </section>

  <section class="method" aria-labelledby="{uid}-method">
    <h2 id="{uid}-method">
      Method <span class="muted"
        >· {review.steps.filter((s) => s.kind === 'step').length}
        {review.steps.filter((s) => s.kind === 'step').length === 1 ? 'step' : 'steps'} found</span
      >
    </h2>
    <ol>
      {#each review.steps as step, i (i)}
        <li class:heading={step.kind === 'heading'}>{step.text}</li>
      {/each}
    </ol>
    {#if review.steps_cut}
      <p class="note">The page had more than 100 steps. The first 100 are here.</p>
    {/if}
    {#if review.steps_shortened}
      <p class="note">
        {review.steps_shortened}
        {review.steps_shortened === 1 ? 'step was' : 'steps were'} shortened to 5,000 characters.
      </p>
    {/if}
    {#each review.left_out as left (left.heading)}
      <p class="note">{leftOutWords(left.heading, left.lines)}. You can add them by hand.</p>
    {/each}
  </section>
</div>

<div class="bar">
  <p class="muted">Nothing is saved until you choose.</p>
  {#if flow.unlinked > 0}
    <p class="muted" role="status">
      {flow.unlinked}
      {flow.unlinked === 1 ? 'line' : 'lines'} will be saved without an ingredient. You can link
      {flow.unlinked === 1 ? 'it' : 'them'} in the recipe.
    </p>
  {/if}
  {#if flow.saveProblem && flow.saveProblem.line === null}
    <p class="error" role="alert">{flow.saveProblem.message}</p>
  {:else if flow.saveProblem && flow.saveProblem.line !== null}
    <p class="error" role="alert">Line {flow.saveProblem.line + 1}: {flow.saveProblem.message}</p>
  {/if}
  <div class="buttons">
    <button type="button" class="cancel" onclick={leave}>Cancel</button>
    <button
      type="button"
      class="save"
      disabled={flow.saving || network.offline}
      onclick={() => void save()}
    >
      {flow.saving ? 'Saving…' : 'Save recipe'}
    </button>
  </div>
  {#if network.offline}
    <p class="muted" role="status">You’re offline. Save when you’re back online.</p>
  {/if}
</div>

{#if asking}
  <LeaveSheet
    name={flow.name}
    again={flow.draftId !== null}
    busy={flow.keeping}
    problem={flow.draftProblem}
    onsave={() => void keep()}
    onstay={() => (asking = false)}
    ondiscard={discard}
  />
{/if}

<style>
  .review {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 860px;
  }

  .top {
    display: flex;
    gap: var(--space-6);
    padding: var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .review:not(.phone) .top {
    gap: var(--space-8);
    padding: var(--space-8);
  }

  .photo {
    flex: none;
    width: 72px;
    height: 72px;
    border-radius: var(--radius-lg);
    object-fit: cover;
  }

  .review:not(.phone) .photo {
    width: 150px;
    height: 150px;
  }

  .photo.none {
    display: flex;
    align-items: center;
    justify-content: center;
    box-sizing: border-box;
    border: 2px dashed var(--color-border-strong);
    color: var(--color-text-muted);
  }

  .fields {
    display: flex;
    flex: 1;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
  }

  .field {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .title {
    font: var(--weight-semibold) 1.375rem var(--font-reading);
  }

  /* Boxes are 16 px or more, so a phone doesn't zoom in on them. */
  .two input {
    font-size: 1rem;
  }

  .two {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--space-4);
  }

  .found {
    color: var(--color-accent-on-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .muted {
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    overflow-wrap: anywhere;
  }

  h2 .muted {
    font-weight: var(--weight-semibold);
  }

  .photo-note {
    padding: 0 var(--space-3);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    line-height: 1.4;
  }

  .photo-note b {
    color: var(--color-text);
  }

  .photo-note a {
    color: var(--color-accent);
    font-weight: var(--weight-bold);
  }

  .counts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
  }

  .count {
    padding: var(--space-3) var(--space-5);
    border-radius: var(--radius-full);
    background: var(--color-chip);
    color: var(--color-text-soft);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .count.good {
    background: var(--color-accent-soft);
    color: var(--color-accent-on-soft);
  }

  .count.warn {
    background: var(--color-maybe-chip);
    color: var(--color-maybe-chip-text);
  }

  .count.bad {
    background: var(--color-warning);
    color: var(--color-warning-text);
  }

  .lines,
  .method {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-4) var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  h2 {
    padding-top: var(--space-4);
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .columns {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  ul,
  ol {
    margin: 0;
    padding: 0;
  }

  .method ol {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding: 0 0 var(--space-4) var(--space-8);
    font-size: var(--text-base);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  .method li.heading {
    margin-left: calc(-1 * var(--space-8));
    list-style: none;
    font-weight: var(--weight-extrabold);
  }

  .note {
    padding-bottom: var(--space-4);
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .bar {
    position: sticky;
    bottom: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    max-width: 860px;
    margin-top: var(--space-6);
    padding: var(--space-5) 0 var(--space-6);
    border-top: 1px solid var(--color-border);
    background: var(--color-ground);
  }

  .bar .muted,
  .bar .error {
    text-align: center;
  }

  .error {
    color: var(--color-warning-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .buttons {
    display: flex;
    gap: var(--space-4);
  }

  .save,
  .cancel {
    min-height: 52px;
    border-radius: var(--radius-button);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .save {
    flex: 1;
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
  }

  .save:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .cancel {
    padding: 0 var(--space-7);
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }
</style>
