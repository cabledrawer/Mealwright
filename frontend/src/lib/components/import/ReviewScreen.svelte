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
  import { downLine } from '#lib/downWords.js';
  import { tick } from 'svelte';
  import { beforeNavigate, goto } from '$app/navigation';
  import { resolve } from '$app/paths';
  import { changesToast } from '#lib/import.save.js';
  import { leftOutWords, type ImportFlow } from '#lib/import.svelte.js';
  import { sentenceCount, stepRuns } from '#lib/importSteps.js';
  import { network } from '#lib/network.svelte.js';
  import { PhotoFallback } from '#lib/photoFallback.svelte.js';
  import { placesAndShops } from '#lib/placesAndShops.svelte.js';
  import { OUTSIDE_CONNECTIONS_ANCHOR } from '#lib/privacyWords.js';
  import Icon from '#lib/components/Icon.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import ZoomPhoto from '#lib/components/ZoomPhoto.svelte';
  import CheckFrame from './CheckFrame.svelte';
  import LeaveSheet from './LeaveSheet.svelte';
  import ReviewLineRow from './ReviewLineRow.svelte';

  import '#lib/styles/fields.css';
  let {
    flow,
    phone = false,
    layout = 'full'
  }: {
    flow: ImportFlow;
    phone?: boolean;
    /** full: the whole screen (a computer, and what this always was). focus and one are the
     *  phone's own pages (F141): the whole list with the app's menu hidden, and one line or step
     *  at a time. Only ReviewPage chooses them, and only on a phone. */
    layout?: 'full' | 'focus' | 'one';
  } = $props();

  /** "See all" on One at a time shows Focus for the rest of this visit. */
  let seeAll = $state(false);
  const mode = $derived(layout === 'one' && seeAll ? 'focus' : layout);

  const review = $derived(flow.review!);
  // The large copy, or the list copy if only that fails; neither means the "No photo" box.
  const copy = new PhotoFallback(() =>
    review.photo.state === 'downloaded' ? review.photo.photo : null
  );
  const shown = $derived(copy.shown);
  const counts = $derived(flow.counts);
  const uid = $props.id();
  // Fetched again as Check opens: a place made on another phone has no live event.
  $effect(() => {
    placesAndShops.load(true).catch(() => {});
  });
  const usPints = $derived(flow.pints === 'us');
  const other = $derived(flow.otherPints);
  const ingredientCount = $derived(review.lines.filter((l) => l.kind === 'ingredient').length);

  async function finish(saved: Awaited<ReturnType<typeof flow.save>>) {
    if (!saved) return;
    changesToast(saved);
    await goto(resolve('/(app)/recipes/[id]', { id: String(saved.recipe.id) }));
  }

  /** Save; with lines that have no ingredient, the sheet that goes through them comes first. */
  async function save() {
    await finish(await flow.trySave());
  }

  function leave() {
    void goto(resolve('/(app)/recipes'));
  }

  /** Close (Focus and One at a time, F141): the recipe stays in Drafts with the choices made so
   *  far (the same draft save as "Save draft"), and Recipes → Drafts opens. A draft that was
   *  opened and not changed just leaves. When the draft can't be kept (offline, or 50 drafts) the
   *  reason shows and nothing is left behind. */
  async function close() {
    if (flow.keeping) return;
    if (flow.unkept && !(await flow.keepAsDraft())) return;
    await goto(resolve('/(app)/recipes/drafts'));
  }

  // --- Leaving without saving -------------------------------------------------------------
  let asking = $state(false);
  /** Where the person was going when the question came up. */
  let target: URL | null = null;
  /** The question was answered: this leave goes through. */
  let allowed = false;

  beforeNavigate((navigation) => {
    // A step's box is open (F143): typed words would be lost, and the leave sheet's Save draft
    // keeps only what is already in the steps. Stay, with the cursor back in the box, until Done
    // or Cancel. Closing the tab is the browser's own. Only the box of the screen showing counts:
    // after a turn of the phone (One at a time <-> the whole list) the other screen's box is gone.
    if (mode === 'one' ? oneBox : editing !== null) {
      if (navigation.willUnload) return;
      navigation.cancel();
      document.querySelector<HTMLElement>('.edit textarea')?.focus();
      return;
    }
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
    void flow.dropPhoto(); // its waiting photo goes at once (F92)
    if (target) void goOn(target);
  }

  /** Close couldn't keep the draft, so the leave sheet's Discard is offered there: the same two
   *  things, then Recipes. */
  function discardAndLeave() {
    void flow.dropPhoto();
    void goOn(new URL(resolve('/(app)/recipes'), window.location.href));
  }

  // --- Changing or removing a step or heading (F111) ------------------------------------------
  // The step being changed, held as the step itself and not its place: the list can move under an
  // open box (Undo, Put the steps back), and the words must land on the step the box was opened
  // for. The box and the code that changes the steps load the first time one is asked for, so the
  // page stays as small as before.
  type Step = (typeof review.steps)[number];
  let editing = $state<Step | null>(null);
  /** One at a time keeps its own box; it tells this screen whether one is open. */
  let oneBox = $state(false);

  // The step went from the list (taken out, split, or put back as it was): the box goes with it.
  $effect(() => {
    if (editing && !review.steps.includes(editing)) editing = null;
  });

  function startEdit(step: Step) {
    flow.previewStep = null;
    editing = step;
    // The box loads on first use. If it can't load, nothing is left open and waiting (Save,
    // Close and Discard wait while a box is open).
    import('./StepEdit.svelte').catch(() => {
      if (editing === step) editing = null;
    });
  }

  /** Close the box; the cursor goes back to the step it was opened from. */
  async function closeEdit() {
    const step = editing;
    editing = null;
    await tick();
    const at = step ? review.steps.indexOf(step) : -1;
    document.querySelector<HTMLElement>(`[data-step-at="${at}"]`)?.focus();
  }

  /** Take a step or heading out, with Undo. The cursor stays in the method, on the step that took
   *  its place. A box open for another step stays open with what was typed. */
  async function removeStep(at: number) {
    const { removeStep: remove } = await import('#lib/importStepEdits.js');
    remove(flow, at);
    await tick();
    const buttons = Array.from(document.querySelectorAll<HTMLElement>('[data-step-remove]'));
    const same = buttons.find((b) => Number(b.dataset.stepRemove) >= at);
    (same ?? buttons.at(-1))?.focus();
  }

  // A removed line's Undo has nowhere to go once this screen is gone.
  $effect(() => () => flow.forgetTakenOut());

  // The bar floats over the foot of the list (and, on a phone, rests on the bottom tabs). A
  // control that is scrolled to, by a tap, Tab or a find, must stop above them, not hide behind.
  let barHeight = $state(0);
  $effect(() => {
    if (mode !== 'full') return;
    const root = document.documentElement;
    root.style.scrollPaddingBottom = `calc(${barHeight}px + ${phone ? 'var(--tabbar-height) + env(safe-area-inset-bottom) + var(--offline-offset)' : '0px'} + var(--space-4))`;
    return () => root.style.removeProperty('scroll-padding-bottom');
  });

  const privacy = `/settings/privacy#${OUTSIDE_CONNECTIONS_ANCHOR}`;
</script>

{#snippet left()}
  <div class="col">
    <section class="top" aria-label="Recipe details">
      {#if review.photo.state === 'downloaded' && shown}
        <div class="photo">
          <ZoomPhoto
            src={shown.url}
            width={shown.width}
            height={shown.height}
            alt="Downloaded from the page"
            name={flow.name.trim() || 'this recipe'}
            onerror={(event) => {
              // Fail the address this picture tried, not whatever is shown by the time the error
              // arrives (a late error from a photo already gone, or from one since replaced).
              const tried = (event.currentTarget as HTMLImageElement).getAttribute('src');
              if (tried) copy.fail(tried);
            }}
          />
        </div>
      {:else if review.photo.state !== 'none'}
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
          <a href={privacy}>Settings → Privacy</a>. You can add your own photo later.
        {:else}
          <b>Photo not downloaded</b>
          — {review.photo.message} You can add your own photo later.
        {/if}
      </p>
    {/if}

    {#if flow.offersPints}
      <!-- A US page: its pints are read as US pints, for this recipe only (mockup ImportPints-*;
         words proposed, for cabledrawer). -->
      <section class="pints" aria-labelledby="{uid}-pints">
        <div class="pints-row">
          <p class="pints-words">
            <span class="pints-title">This looks like a US recipe</span>
            <span id="{uid}-pints">Read its pints as US pints (473 ml)</span>
          </p>
          <Switch
            checked={usPints}
            labelledby="{uid}-pints"
            onchange={(on) => (flow.pints = on ? 'us' : 'uk')}
          />
        </div>
        <p class="pints-foot">For this recipe only. Your setting stays UK pints.</p>
      </section>
    {/if}
  </div>
{/snippet}

{#snippet middle()}
  <div class="col middle">
    <section class="lines" aria-labelledby="{uid}-ingredients">
      <!-- The counts sit in the heading row, as the mockup (ImportCheck07-Desktop). -->
      <div class="lines-head">
        <h2 id="{uid}-ingredients">Ingredients <span class="muted">· {ingredientCount}</span></h2>
        {#if mode !== 'focus'}
          <div class="counts" aria-label="What was found">
            <span class="count good">{counts.matched} matched</span>
            <span class="count warn">{counts.to_confirm} to confirm</span>
            <span class="count bad"
              >{counts.needs_you}
              {counts.needs_you === 1 ? 'needs' : 'need'} you</span
            >
            <span class="count">{counts.staple} {counts.staple === 1 ? 'staple' : 'staples'}</span>
          </div>
        {/if}
      </div>
      {#if !phone}
        <p class="columns" aria-hidden="true">
          <span>As written → how Mealwright reads it → in your kitchen</span>
        </p>
      {/if}
      <ul>
        {#each review.lines as line, index (line)}
          <ReviewLineRow
            {flow}
            {index}
            line={flow.withPints(line)}
            problem={flow.saveProblem?.line === index ? flow.saveProblem.message : null}
          />
        {/each}
      </ul>
      {#if flow.offersPints && other}
        <p class="pints-hint">
          Switch it {usPints ? 'off' : 'on'} and the {other.words} reads {other.reads}
          ({other.kind === 'us' ? 'US' : 'UK'} pints).
        </p>
      {/if}
      {#if review.lines_cut}
        <p class="note">The page had more than 200 ingredient lines. The first 200 are here.</p>
      {/if}
    </section>
  </div>
{/snippet}

{#snippet right()}
  <div class="col">
    <section class="method" aria-labelledby="{uid}-method">
      <h2 id="{uid}-method">
        Method <span class="muted"
          >· {review.steps.filter((s) => s.kind === 'step').length}
          {review.steps.filter((s) => s.kind === 'step').length === 1 ? 'step' : 'steps'} found</span
        >
      </h2>
      <!-- Keyed by the step itself, so a box open on one stays (with what was typed) when others move. -->
      {#each stepRuns(review.steps) as run (run.heading ? review.steps[run.heading.at] : 'start')}
        {#if run.heading}
          {@const at = run.heading.at}
          {#if editing === review.steps[at]}
            {#await import('./StepEdit.svelte') then { default: StepEdit }}
              <StepEdit
                {flow}
                step={review.steps[at]!}
                name="heading"
                onclose={() => void closeEdit()}
                onremove={() => void removeStep(at)}
              />
            {:catch}
              <!-- Cleared in startEdit. -->
            {/await}
          {:else}
            <div class="step-row">
              <h3 class="step-heading">
                <button
                  type="button"
                  class="step-text"
                  data-step-at={at}
                  title="Change heading"
                  onclick={() => startEdit(review.steps[at]!)}>{run.heading.text}</button
                >
              </h3>
              <button
                type="button"
                class="step-remove"
                data-step-remove={at}
                aria-label="Remove heading: {run.heading.text}"
                onclick={() => void removeStep(at)}>Remove</button
              >
            </div>
          {/if}
        {/if}
        {#if run.steps.length}
          <!-- A heading is not in the numbered list, so it takes no number (F112). -->
          <ol start={run.start}>
            {#each run.steps as step, n (review.steps[step.at])}
              {@const pieces = flow.splitOf(step.at)}
              {@const number = run.start + n}
              <li>
                {#if editing === review.steps[step.at]}
                  {#await import('./StepEdit.svelte') then { default: StepEdit }}
                    <StepEdit
                      {flow}
                      step={review.steps[step.at]!}
                      name="step {number}"
                      onclose={() => void closeEdit()}
                      onremove={() => void removeStep(step.at)}
                    />
                  {:catch}
                    <!-- Cleared in startEdit. -->
                  {/await}
                {:else}
                  <div class="step-row">
                    <button
                      type="button"
                      class="step-text"
                      data-step-at={step.at}
                      aria-label="Change step {number}: {step.text}"
                      onclick={() => startEdit(review.steps[step.at]!)}>{step.text}</button
                    >
                    <button
                      type="button"
                      class="step-remove"
                      data-step-remove={step.at}
                      aria-label="Remove step {number}"
                      onclick={() => void removeStep(step.at)}>Remove</button
                    >
                  </div>
                {/if}
                {#if pieces && flow.previewStep !== step.at}
                  <span class="long">
                    <span class="long-note">A long step ({sentenceCount(step.text)} sentences)</span
                    >
                    <button
                      type="button"
                      class="chip"
                      onclick={() => {
                        flow.previewStep = step.at;
                      }}>Split into shorter steps</button
                    >
                  </span>
                {/if}
                {#if pieces && flow.previewStep === step.at}
                  <span class="preview" role="group" aria-label="Preview of the split">
                    <span class="preview-title">Preview: this step as {pieces.length} steps</span>
                    {#each pieces as piece, n (n)}
                      <span class="piece"><b>{n + 1}.</b> {piece}</span>
                    {/each}
                    <span class="preview-buttons">
                      <button
                        type="button"
                        class="keep"
                        onclick={() => {
                          flow.keepSplit(step.at);
                        }}>Keep the split</button
                      >
                      <button type="button" class="quiet" onclick={() => (flow.previewStep = null)}
                        >Keep as one</button
                      >
                    </span>
                  </span>
                {/if}
              </li>
            {/each}
          </ol>
        {/if}
      {/each}
      {#if flow.stepsBefore}
        <p class="note">
          Some long steps were split into shorter ones.
          <button type="button" class="quiet" onclick={() => flow.putStepsBack()}
            >Put the steps back as they were</button
          >
        </p>
      {/if}
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
{/snippet}

{#snippet reviewBody()}
  <div class="wrap">
    <div class="review" class:phone class:focus={mode === 'focus'}>
      {#if mode === 'focus'}
        <!-- Focus puts the ingredients first, so they get the screen (cabledrawer 5 Nov, F141). -->
        {@render middle()}
        {@render left()}
        {@render right()}
      {:else}
        {@render left()}
        {@render middle()}
        {@render right()}
      {/if}
    </div>
  </div>
{/snippet}

{#if mode === 'one'}
  <!-- One at a time loads the first time it is asked for, so the import page stays small. -->
  {#await import('./OneAtATime.svelte') then { default: OneAtATime }}
    <OneAtATime
      {flow}
      bind:boxOpen={oneBox}
      closing={flow.keeping}
      onclose={() => void close()}
      onsave={() => void save()}
      onseeall={() => (seeAll = true)}
      onleave={discardAndLeave}
    />
  {/await}
{:else if mode === 'focus'}
  <CheckFrame>
    {#snippet header()}
      <div class="fhead">
        <!-- "Check before saving" as the Focus h1: cabledrawer 5 Nov (F141). -->
        <h1>Check before saving</h1>
        <span class="muted">Step 2 of 3 · nothing saved yet</span>
      </div>
      <div class="counts" aria-label="What was found">
        <span class="count good">{counts.matched} ok</span>
        <span class="count warn">{counts.to_confirm} to confirm</span>
        <span class="count bad"
          >{counts.needs_you} {counts.needs_you === 1 ? 'needs' : 'need'} you</span
        >
        <span class="count">{counts.staple} {counts.staple === 1 ? 'staple' : 'staples'}</span>
      </div>
    {/snippet}
    {@render reviewBody()}
    {#snippet footer()}
      <div class="fbar">
        {#if flow.saveProblem && flow.saveProblem.line === null}
          <p class="error" role="alert">{flow.saveProblem.message}</p>
        {:else if flow.saveProblem && flow.saveProblem.line !== null}
          <p class="error" role="alert">
            Line {flow.saveProblem.line + 1}: {flow.saveProblem.message}
          </p>
        {/if}
        {#if flow.draftProblem}
          <p class="error" role="alert">{flow.draftProblem}</p>
          <!-- The leave sheet's own words and action: the draft can't be kept, so this is the way out. -->
          <button
            type="button"
            class="leave"
            disabled={flow.saving || editing !== null}
            onclick={discardAndLeave}
            >{flow.draftId !== null ? 'Discard changes' : 'Discard'}</button
          >
        {/if}
        <div class="buttons">
          <button
            type="button"
            class="close"
            disabled={flow.keeping || flow.saving || editing !== null}
            onclick={() => void close()}
          >
            Close <span class="sub">Kept in Drafts</span>
          </button>
          <button
            type="button"
            class="save"
            disabled={flow.saving || flow.keeping || editing !== null || network.offline}
            onclick={() => void save()}
          >
            {flow.saving ? 'Saving…' : 'Save recipe'}
          </button>
        </div>
        {#if network.offline}
          <p class="muted" role="status">
            {downLine(network.deviceOffline, (b) => `Save ${b.when}.`)}
          </p>
        {/if}
      </div>
    {/snippet}
  </CheckFrame>
{:else}
  {@render reviewBody()}
  <div class="bar" class:phone bind:offsetHeight={barHeight}>
    <p class="muted">Nothing is saved until you choose.</p>
    {#if flow.saveProblem && flow.saveProblem.line === null}
      <p class="error" role="alert">{flow.saveProblem.message}</p>
    {:else if flow.saveProblem && flow.saveProblem.line !== null}
      <p class="error" role="alert">Line {flow.saveProblem.line + 1}: {flow.saveProblem.message}</p>
    {/if}
    <div class="buttons">
      <button type="button" class="cancel" disabled={editing !== null} onclick={leave}
        >Cancel</button
      >
      <button
        type="button"
        class="save"
        disabled={flow.saving || editing !== null || network.offline}
        onclick={() => void save()}
      >
        {flow.saving ? 'Saving…' : 'Save recipe'}
      </button>
    </div>
    {#if network.offline}
      <p class="muted" role="status">{downLine(network.deviceOffline, (b) => `Save ${b.when}.`)}</p>
    {/if}
  </div>
{/if}

{#if flow.walk}
  <!-- Loaded when first needed, so the page stays small (F111). -->
  {#await import('./WalkSheet.svelte') then { default: WalkSheet }}
    <WalkSheet {flow} onsave={async () => finish(await flow.saveAnyway())} />
  {/await}
{/if}

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
  .wrap {
    container-type: inline-size;
  }

  .review {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 860px;
  }

  .col {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    min-width: 0;
  }

  /* A computer with room: three columns (details, ingredients, method; mockup
     Dark-ImportCheck07-Desktop: 300px, the rest, 340px). In rem, so larger text stacks them again before they squeeze. */
  @container (min-width: 64rem) {
    .review:not(.phone) {
      display: grid;
      grid-template-columns: 18.75rem minmax(0, 1fr) 21.25rem;
      gap: var(--space-6);
      align-items: start;
      max-width: none;
    }

    .wrap .review:not(.phone) .top {
      flex-direction: column;
      padding: var(--space-6);
    }

    .wrap .review:not(.phone) .photo {
      width: 100%;
      height: 150px;
    }

    .wrap .review:not(.phone) .photo.none {
      height: 150px;
    }
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
    position: relative;
    flex: none;
    width: 72px;
    height: 72px;
    border-radius: var(--radius-lg);
    background: var(--color-recipe-square);
    overflow: hidden;
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

  .pints {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-5) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-info);
    color: var(--color-info-text);
  }

  .pints-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-5);
  }

  .pints-words {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
    font-size: var(--text-sm);
  }

  .pints-title {
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
  }

  .pints-foot {
    color: var(--color-info-muted);
    font-size: var(--text-sm);
  }

  .pints-hint {
    padding: 0 var(--space-1);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
  }

  .lines-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
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
  }

  .method {
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

  .lines ul {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .long,
  .preview {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    margin-top: var(--space-3);
    padding: var(--space-4);
    border: 1px solid var(--color-border-strong);
    border-radius: 14px;
  }

  .preview {
    border: 2px solid var(--color-accent);
    font-size: var(--text-md);
  }

  .long-note {
    color: var(--color-maybe-text);
    font-size: var(--text-sm);
    font-weight: var(--weight-bold);
  }

  .preview-title {
    color: var(--color-accent-on-soft);
    font-size: var(--text-xs);
    font-weight: var(--weight-extrabold);
    letter-spacing: 0.04em;
    text-transform: uppercase;
  }

  .preview-buttons {
    display: flex;
    gap: var(--space-4);
    align-items: center;
  }

  .chip,
  .keep,
  .quiet {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border-radius: var(--radius-full);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .chip {
    align-self: flex-start;
    border: 1px solid var(--color-border-strong);
    background: transparent;
    color: var(--color-text);
  }

  .keep {
    border: none;
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font-weight: var(--weight-extrabold);
  }

  .quiet {
    border: none;
    background: transparent;
    color: var(--color-text-muted);
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

  .method .step-heading {
    flex: 1;
    min-width: 0;
    font-size: var(--text-base);
    font-weight: var(--weight-extrabold);
    line-height: 1.5;
    overflow-wrap: anywhere;
  }

  /* A step or heading: its words are a button (tap to change), with Remove beside it (F111). */
  .step-row {
    display: flex;
    gap: var(--space-3);
    align-items: flex-start;
  }

  .step-text {
    flex: 1;
    min-width: 0;
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    overflow-wrap: anywhere;
    cursor: pointer;
  }

  .step-remove {
    flex: none;
    min-height: var(--touch-target);
    padding: 0 var(--space-3);
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-md);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .note {
    padding-bottom: var(--space-4);
    color: var(--color-text-muted);
    font-size: var(--text-md);
  }

  .bar:not(.phone) {
    max-width: none;
  }

  /* Focus (F141, mockup Dark-ImportCheckFocus07-Phone): the counts are in the header. */
  .review.focus {
    max-width: none;
  }

  .fhead {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-4);
    margin-bottom: var(--space-4);
  }

  .fhead h1 {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
  }

  .fhead .muted {
    text-align: right;
  }

  .fbar {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }

  .fbar .muted,
  .fbar .error {
    text-align: center;
  }

  .leave {
    min-height: var(--touch-target);
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-size: var(--text-base);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .close {
    display: flex;
    flex: 1;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 52px;
    border: 1px solid var(--color-border-strong);
    border-radius: var(--radius-full);
    background: transparent;
    color: var(--color-text);
    font-size: 1rem;
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .close:disabled {
    opacity: 0.6;
    cursor: default;
  }

  .close .sub {
    color: var(--color-text-muted);
    font-size: var(--text-xs);
    font-weight: var(--weight-semibold);
  }

  .fbar .save {
    flex: 1.4;
    border-radius: var(--radius-full);
  }

  /* On a phone the bottom tabs are fixed over the foot of the screen: the bar rests on top of
     them (and the offline bar), so Cancel and Save are never hidden behind the tabs while the
     list scrolls. */
  .bar.phone {
    bottom: calc(var(--tabbar-height) + env(safe-area-inset-bottom) + var(--offline-offset));
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

  /* A blocked button looks blocked, the same as Save recipe (F154). */
  .cancel:disabled,
  .leave:disabled {
    opacity: 0.6;
    cursor: default;
  }
</style>
