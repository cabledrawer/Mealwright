<script lang="ts">
  // New recipe and Edit recipe (mockups RecipeEditor-*, NewRecipe-*, EditorState-*; cabledrawer 19
  // Oct, editor brief). Nothing changes until Save; Cancel with changes closes at once with
  // "Changes not saved" and Undo. Recipes are online only in 0.4: offline, the editor keeps
  // what was typed and Save waits.
  import '$lib/styles/fields.css';
  import { onMount, tick } from 'svelte';
  import { beforeNavigate } from '$app/navigation';
  import { resolve } from '$app/paths';
  import Switch from '../Switch.svelte';
  import ConflictSheet from './ConflictSheet.svelte';
  import EditorNote from './EditorNote.svelte';
  import LineList from './LineList.svelte';
  import PhotoField from './PhotoField.svelte';
  import ServesField from './ServesField.svelte';
  import StepList from './StepList.svelte';
  import TagsField from './TagsField.svelte';
  import { ApiError, worthRetrying } from '$lib/api';
  import { newChangeId } from '$lib/changeId';
  import { serverUndo } from '$lib/client/changes';
  import { listFoods } from '$lib/client/foods';
  import {
    cannotUse,
    createRecipe,
    deleteRecipe,
    getRecipe,
    saveRecipe,
    suggestTags,
    type Blocked,
    type RecipeOut
  } from '$lib/client/recipes';
  import { kitchen } from '$lib/freshness.svelte';
  import { network } from '$lib/network.svelte';
  import { autosize } from '$lib/recipes/autosize';
  import { COUNT, NUTRIENTS, RecipeDraft, type Errors } from '$lib/recipes/draft.svelte';
  import { go, NEW_RECIPE, RECIPES, editPage, recipePage } from '$lib/recipes/paths';
  import { fold, recipeSearch } from '$lib/recipes/search';
  import { takeKept, editorKey, keep, reopen } from '$lib/recipes/stash';
  import { toasts } from '$lib/toast.svelte';
  import { undoHistory } from '$lib/undo.svelte';

  let { recipeId = null }: { recipeId?: number | null } = $props();

  const uid = $props.id();
  // The page makes a new editor for each recipe ({#key}), so these are fixed for its life.
  // svelte-ignore state_referenced_locally
  const key = editorKey(recipeId);
  // svelte-ignore state_referenced_locally
  const editing = recipeId !== null;
  const title = editing ? 'Edit recipe' : 'New recipe';

  let draft = $state<RecipeDraft | null>(null);
  let loading = $state<'loading' | 'ready' | 'failed' | 'missing'>('loading');
  let errors = $state<Errors>({});
  let saving = $state(false);
  let cantSave = $state(false);
  let problem = $state<string | null>(null);
  let conflict = $state<{ who: string; detail: string; version: number } | null>(null);
  let wrens = $state<RecipeOut | null>(null);
  let seeing = $state(false);
  let blocked = $state<Blocked[]>([]);
  let existing = $state<string | null>(null);
  let live = $state('');
  let phone = $state(matchMedia('(max-width: 767px)').matches);
  /** Set when the editor is being left on purpose (saved, cancelled, deleted). */
  let leaving = false;
  let attempt = { snapshot: '', key: '' };

  // Save and "Save mine anyway" both wait for the network and for a photo still going up.
  const canOverwrite = $derived(!!draft && !saving && !draft.photo.uploading && !network.offline);
  const canSave = $derived(canOverwrite && !!draft && draft.name.trim() !== '');
  const effectiveHomemade = $derived((draft?.homemadeName.trim() || draft?.name.trim()) ?? '');

  // The phone layout has no bottom tabs in the editor: it is a full page of its own.
  onMount(() => {
    document.documentElement.setAttribute('data-full-page', '');
    const media = matchMedia('(max-width: 767px)');
    const onchange = () => (phone = media.matches);
    media.addEventListener('change', onchange);
    return () => {
      document.documentElement.removeAttribute('data-full-page');
      media.removeEventListener('change', onchange);
    };
  });

  // --- Opening ---------------------------------------------------------------------------------

  async function open() {
    loading = 'loading';
    const kept = takeKept(key);
    if (kept) {
      draft = kept;
      loading = 'ready';
      const file = kept.photo.change === 'new' ? kept.photo.file : null;
      if (file) {
        // The cancelled editor gave its upload's place back; upload the picture again.
        kept.photo = {
          shown: kept.opened?.photo ?? null,
          change: 'none',
          uploading: null,
          file: null,
          error: null
        };
        void kept.pickPhoto(file);
      }
    } else if (recipeId === null) {
      draft = new RecipeDraft();
      draft.markSaved();
      loading = 'ready';
    } else {
      try {
        draft = RecipeDraft.from(await getRecipe(recipeId));
        loading = 'ready';
      } catch (error) {
        loading = error instanceof ApiError && error.status === 404 ? 'missing' : 'failed';
        return;
      }
    }
    if (recipeId !== null) {
      cannotUse(recipeId)
        .then((list) => (blocked = list))
        .catch(() => {});
    }
  }

  onMount(() => void open());

  // --- Made ahead: is there already an ingredient with that name? --------------------------------

  $effect(() => {
    const d = draft;
    const name = effectiveHomemade;
    if (!d || !d.madeAhead || d.homemade || !name) {
      existing = null;
      return;
    }
    const timer = setTimeout(() => {
      listFoods({ q: name, limit: 8 })
        .then((list) => {
          existing = list.foods.find((f) => fold(f.name) === fold(name))?.name ?? null;
        })
        .catch(() => (existing = null));
    }, 300);
    return () => clearTimeout(timer);
  });

  // --- The picker's searches -------------------------------------------------------------------

  const findRecipes = recipeSearch();
  const search = async (q: string) => {
    const [foods, recipes] = await Promise.all([
      listFoods({ q, limit: 8 }).then((list) => list.foods),
      findRecipes(q).catch(() => [])
    ]);
    return { foods, recipes };
  };

  // --- Leaving -----------------------------------------------------------------------------------

  /** Leave with unsaved changes: nothing is asked; Undo opens the editor again as it was. */
  function keepForUndo() {
    const d = draft;
    // Even with nothing else changed, a photo still going up must not be left behind.
    d?.discardUpload();
    if (!d?.dirty) return;
    keep(key, d);
    undoHistory.record({
      label: 'Changes not saved',
      undo: () => {
        const path = editing ? editPage(recipeId!) : NEW_RECIPE;
        // Already on that editor (Ctrl+Z from another recipe): nothing to open again.
        if (location.pathname === path) return 'That editor is already open.';
        if (!reopen(key)) return 'Those changes can’t be brought back any more.';
        void go(path);
        return false;
      }
    });
  }

  function cancel() {
    leaving = true;
    keepForUndo();
    void go(editing ? recipePage(recipeId!) : RECIPES);
  }

  // Leaving some other way (a tab, a link, the back button) counts as Cancel.
  beforeNavigate(({ type }) => {
    if (leaving || type === 'leave') return;
    leaving = true;
    keepForUndo();
  });

  // --- Saving ------------------------------------------------------------------------------------

  function showFirstProblem() {
    void tick().then(() => {
      const first = document.querySelector<HTMLElement>('[aria-invalid="true"], .mw-error');
      first?.scrollIntoView({ block: 'center' });
      if (first?.matches('input, textarea, select, button')) first.focus({ preventScroll: true });
    });
  }

  async function save(overwrite = false) {
    const d = draft;
    if (!d || !(overwrite ? canOverwrite : canSave)) return;
    const built = d.build();
    errors = built.errors;
    cantSave = false;
    problem = null;
    if (Object.keys(errors).length) {
      showFirstProblem();
      return;
    }
    const version = overwrite && conflict ? conflict.version : (d.opened?.version ?? 0);
    // The same change keeps its ID when it is sent again, so a retry never saves twice.
    const snapshot = `${d.snapshot()}|${version}|${overwrite}`;
    if (attempt.snapshot !== snapshot) attempt = { snapshot, key: newChangeId() };
    saving = true;
    try {
      const saved =
        recipeId === null
          ? await createRecipe(built.body, attempt.key)
          : await saveRecipe(recipeId, built.body, version, overwrite, attempt.key);
      leaving = true;
      kitchen.changed();
      toasts.show('Saved');
      void go(recipePage(saved.id));
    } catch (error) {
      seeing = false;
      if (!(error instanceof ApiError)) throw error;
      if (error.code === 'recipe_changed') {
        const data = error.body as { version: number; changed_by?: { name: string } };
        conflict = {
          who: data.changed_by?.name ?? 'Someone',
          detail: error.detail,
          version: data.version
        };
        return;
      }
      conflict = null;
      if (worthRetrying(error)) {
        cantSave = true;
        return;
      }
      errors = d.explain(error, built);
      if (!Object.keys(errors).length) problem = error.detail;
      showFirstProblem();
    } finally {
      saving = false;
    }
  }

  async function seeTheirs() {
    if (!recipeId) return;
    try {
      wrens = await getRecipe(recipeId);
      seeing = true;
    } catch {
      toasts.show('Couldn’t open their version. Try again.', { tone: 'problem' });
    }
  }

  function saveKey(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && !event.altKey && event.key.toLowerCase() === 's') {
      event.preventDefault();
      if (conflict) return;
      void save();
    }
  }

  // --- Deleting ----------------------------------------------------------------------------------

  async function remove() {
    const name = draft?.opened?.name ?? '';
    if (!recipeId) return;
    leaving = true;
    try {
      const { change } = await deleteRecipe(recipeId, newChangeId());
      kitchen.changed();
      undoHistory.record({ label: `Deleted ${name}`, undo: serverUndo(change.id) });
      void go(RECIPES);
    } catch (error) {
      leaving = false;
      toasts.show(error instanceof ApiError ? error.detail : 'Couldn’t delete. Try again.', {
        tone: 'problem'
      });
    }
  }

  function oneLine(event: Event) {
    const box = event.currentTarget as HTMLTextAreaElement;
    if (/[\r\n\t]/.test(box.value) && draft) draft.name = box.value.replace(/[\r\n\t]+/g, ' ');
  }
</script>

<svelte:head>
  <title>{title} · Mealwright</title>
</svelte:head>

<svelte:window onkeydown={saveKey} />

{#if loading !== 'ready' || !draft}
  <section class="state" aria-live="polite">
    <h1>{title}</h1>
    {#if loading === 'loading'}
      <p>Opening the recipe…</p>
    {:else if loading === 'missing'}
      <p>That recipe isn’t here any more.</p>
      <a class="mw-pill" href={resolve('/recipes')}>All recipes</a>
    {:else}
      <p>Couldn’t load this recipe. Check your connection and try again.</p>
      <span class="choices">
        <button type="button" class="mw-pill" onclick={() => void open()}>Try again</button>
        <a class="mw-pill" href={resolve('/recipes')}>All recipes</a>
      </span>
    {/if}
  </section>
{:else}
  <form class="editor" onsubmit={(e) => e.preventDefault()} novalidate>
    <header class="bar">
      <button type="button" class="cancel" onclick={cancel}>Cancel</button>
      <div class="heading">
        <h1>{title}</h1>
        <p class="lead">Nothing changes until you save. Only the name is needed.</p>
      </div>
      <button type="button" class="save" disabled={!canSave} onclick={() => void save()}>
        {saving ? 'Saving…' : 'Save'}
        {#if !phone && !saving}<kbd>Ctrl+S</kbd>{/if}
      </button>
    </header>

    {#if network.offline}
      <EditorNote tone="offline">You’re offline. Save when you’re back online.</EditorNote>
    {/if}
    {#if cantSave}
      <EditorNote tone="trouble">
        <span>Couldn’t save. Try again.</span>
        <button type="button" class="mw-pill" onclick={() => void save()}>Try again</button>
      </EditorNote>
    {/if}
    {#if problem}
      <EditorNote tone="trouble"><span>{problem}</span></EditorNote>
    {/if}
    {#if conflict}
      <EditorNote tone="conflict">
        <span>{conflict.detail}</span>
        <span class="choices">
          <button type="button" class="mw-pill" onclick={() => void seeTheirs()}>
            See {conflict.who}’s version
          </button>
          <button
            type="button"
            class="mine"
            disabled={!canOverwrite}
            onclick={() => void save(true)}
          >
            Save mine anyway
          </button>
        </span>
      </EditorNote>
    {/if}

    <div class="grid">
      <div class="basics">
        <PhotoField
          photo={draft.photo}
          onpick={(file) => void draft?.pickPhoto(file)}
          onremove={() => draft?.removePhoto()}
        />
        {#if errors.photo}<p class="mw-error" role="alert">{errors.photo}</p>{/if}

        <div class="mw-field">
          <label class="mw-label" for="{uid}-name">Name</label>
          <textarea
            id="{uid}-name"
            class="mw-input name"
            rows="1"
            maxlength="200"
            placeholder="e.g. Sambar"
            aria-invalid={errors.name ? true : undefined}
            aria-describedby="{uid}-name-note"
            bind:value={draft.name}
            use:autosize={draft.name}
            oninput={oneLine}
            onkeydown={(e) => e.key === 'Enter' && e.preventDefault()}></textarea>
          {#if errors.name}<span id="{uid}-name-note" class="mw-error">{errors.name}</span>
          {:else if !draft.name.trim()}<span id="{uid}-name-note" class="mw-hint"
              >A name is all you need to save.</span
            >{/if}
        </div>

        <div class="mw-field">
          <label class="mw-label" for="{uid}-description">
            Short description <span class="mw-optional">(optional)</span>
          </label>
          <input
            id="{uid}-description"
            class="mw-input"
            type="text"
            maxlength="200"
            placeholder="One line, e.g. Lentil & vegetable stew"
            aria-invalid={errors.description ? true : undefined}
            aria-describedby={errors.description ? `${uid}-description-note` : undefined}
            bind:value={draft.description}
          />
          {#if errors.description}<span id="{uid}-description-note" class="mw-error"
              >{errors.description}</span
            >{/if}
        </div>

        <div class="pair">
          <div class="mw-field">
            <label class="mw-label" for="{uid}-time">
              Time <span class="mw-optional">(minutes)</span>
            </label>
            <input
              id="{uid}-time"
              class="mw-input"
              type="text"
              inputmode="numeric"
              maxlength="5"
              placeholder="e.g. 50"
              aria-invalid={errors.time ? true : undefined}
              aria-describedby={errors.time ? `${uid}-time-note` : undefined}
              bind:value={draft.time}
            />
            {#if errors.time}<span id="{uid}-time-note" class="mw-error">{errors.time}</span>{/if}
          </div>
          <ServesField bind:serves={draft.serves} error={errors.serves} />
        </div>

        <div class="mw-field" role="group" aria-labelledby="{uid}-makes">
          <span id="{uid}-makes" class="mw-label">
            Makes <span class="mw-optional">(optional)</span>
          </span>
          <span class="makes-row">
            <input
              class="mw-input"
              type="text"
              inputmode="decimal"
              maxlength="20"
              aria-label="Makes amount"
              placeholder="e.g. 1.5"
              aria-invalid={errors.makes ? true : undefined}
              bind:value={draft.makesAmount}
            />
            <select class="mw-input" aria-label="Makes unit" bind:value={draft.makesUnit}>
              <option value="l">litres</option>
              <option value="ml">ml</option>
              <option value="g">g</option>
              <option value="kg">kg</option>
              <option value={COUNT}>count</option>
            </select>
          </span>
          {#if draft.makesUnit === COUNT}
            <input
              class="mw-input"
              type="text"
              maxlength="30"
              aria-label="What it makes"
              placeholder="What it makes, e.g. dosas"
              bind:value={draft.makesWord}
            />
          {/if}
          {#if errors.makes}<span class="mw-error">{errors.makes}</span>
          {:else}<span class="mw-hint"
              >For a batter, a podi or anything made ahead: “Makes 200 g”.</span
            >{/if}
        </div>

        <div class="made">
          <div class="made-head">
            <span class="made-words">
              <span id="{uid}-made" class="made-title">Made ahead (keeps in the pantry)</span>
              <span class="mw-hint">For things you make once and use over days</span>
            </span>
            <Switch bind:checked={draft.madeAhead} labelledby="{uid}-made" />
          </div>
          {#if draft.madeAhead}
            <div class="made-body">
              {#if draft.homemade}
                <p>Kept in Ingredients as <b>{draft.homemade.name}</b>.</p>
              {:else}
                {#if existing}
                  <p class="exists" role="status">
                    {existing} is already in Ingredients. It will be linked to this recipe, and its pantry
                    stock stays.
                  </p>
                {:else}
                  <p>
                    Adds <b>{effectiveHomemade || 'this recipe'}</b> to Ingredients as homemade, so the
                    pantry can keep it.
                  </p>
                {/if}
                <div class="mw-field">
                  <label class="mw-label" for="{uid}-homemade">Ingredient name</label>
                  <input
                    id="{uid}-homemade"
                    class="mw-input"
                    type="text"
                    maxlength="100"
                    aria-invalid={errors.homemade ? true : undefined}
                    value={draft.homemadeName || draft.name}
                    oninput={(e) => (draft!.homemadeName = e.currentTarget.value)}
                  />
                </div>
              {/if}
              {#if errors.homemade}<p class="mw-error" role="alert">{errors.homemade}</p>{/if}
              {#if !draft.makesAmount.trim()}
                <p class="warm">Add how much it makes, so the pantry can count it.</p>
              {/if}
            </div>
          {:else if draft.opened?.made_ahead && draft.homemade}
            <p class="made-body mw-hint">
              {draft.homemade.name} stays in Ingredients, no longer linked to this recipe.
            </p>
          {/if}
        </div>

        <TagsField bind:tags={draft.tags} suggest={suggestTags} error={errors.tags} />

        <fieldset class="nutrition">
          <legend>Nutrition per serving <span>(optional)</span></legend>
          <div class="nutrients">
            {#each NUTRIENTS as nutrient (nutrient)}
              <label class="mw-field mw-label">
                {nutrient === 'kcal' ? 'kcal' : `${nutrient} g`}
                <input
                  class="mw-input"
                  type="text"
                  inputmode="decimal"
                  maxlength="9"
                  placeholder="?"
                  aria-invalid={errors[`nutrition.${nutrient}`] ? true : undefined}
                  bind:value={draft.nutrition[nutrient]}
                />
              </label>
            {/each}
          </div>
          {#each NUTRIENTS as nutrient (nutrient)}
            {#if errors[`nutrition.${nutrient}`]}
              <p class="mw-error">{errors[`nutrition.${nutrient}`]}</p>
            {/if}
          {/each}
          <p class="mw-hint">Leave a box empty if you don’t know: it shows as unknown, never 0.</p>
        </fieldset>
      </div>

      <div class="body">
        <LineList {draft} {phone} {errors} {blocked} {search} announce={(m) => (live = m)} />
        <StepList {draft} {errors} announce={(m) => (live = m)} />
      </div>

      <div class="rest">
        <div class="mw-field">
          <label class="mw-label" for="{uid}-source">
            Source <span class="mw-optional">(optional)</span>
          </label>
          <input
            id="{uid}-source"
            class="mw-input"
            type="text"
            maxlength="500"
            placeholder="Amma’s, a book, or a web address"
            aria-invalid={errors.source ? true : undefined}
            bind:value={draft.source}
          />
          {#if errors.source}<span class="mw-error">{errors.source}</span>{/if}
          <span class="mw-hint"
            >A web address shows as a link you can open yourself. Mealwright never visits it.</span
          >
        </div>

        {#if editing}
          <div class="delete">
            <button type="button" onclick={() => void remove()}>Delete recipe</button>
            <span class="mw-hint">No “Are you sure?”: you can undo it for 7 days.</span>
          </div>
        {/if}
      </div>
    </div>

    <p class="visually-hidden" role="status" aria-live="polite">{live}</p>
  </form>

  {#if seeing && wrens && conflict && draft.opened}
    <ConflictSheet
      who={conflict.who}
      opened={draft.opened}
      theirs={wrens}
      {phone}
      busy={!canOverwrite}
      offline={network.offline}
      onclose={() => (seeing = false)}
      onsave={() => void save(true)}
    />
  {/if}
{/if}

<style>
  .state {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-5);
    max-width: 860px;
    padding: var(--space-8);
    border-radius: var(--radius-3xl);
    background: var(--color-surface);
  }

  .state h1 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  .state p {
    color: var(--color-text-muted);
  }

  .editor {
    display: flex;
    flex-direction: column;
    gap: var(--space-7);
    max-width: 1100px;
  }

  /* The bar with Cancel and Save stays in reach the whole time (phone: a top bar). */
  .bar {
    position: sticky;
    top: 0;
    z-index: 5;
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: var(--space-3);
    margin: 0 calc(-1 * var(--space-8));
    padding: max(var(--space-4), env(safe-area-inset-top)) var(--space-4) var(--space-4);
    border-bottom: 1px solid var(--color-border);
    background: var(--color-chrome);
  }

  h1 {
    font-size: var(--text-xl);
    font-weight: var(--weight-extrabold);
    text-align: center;
  }

  .lead {
    display: none;
  }

  .cancel {
    justify-self: start;
    min-height: var(--touch-target);
    padding: 0 var(--space-4);
    border: none;
    background: transparent;
    color: var(--color-accent);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .save {
    justify-self: end;
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
    min-height: var(--touch-target);
    padding: 0 var(--space-8);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-accent);
    color: var(--color-surface);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .save:disabled {
    background: var(--color-fill-strong);
    color: var(--color-text-muted);
    cursor: not-allowed;
  }

  kbd {
    padding: 1px 5px;
    border: 1px solid currentColor;
    border-radius: 6px;
    font: var(--weight-bold) var(--text-xs) var(--font-ui);
  }

  .choices {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .mine {
    min-height: var(--touch-target);
    padding: 0 var(--space-7);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-inverse);
    color: var(--color-inverse-text);
    font: var(--weight-bold) var(--text-base) var(--font-ui);
    cursor: pointer;
  }

  .mine:disabled {
    cursor: progress;
    opacity: 0.7;
  }

  .grid {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
  }

  .basics,
  .body,
  .rest {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
    min-width: 0;
  }

  .body {
    gap: var(--space-10);
  }

  .name {
    font-size: var(--text-xl);
    font-weight: var(--weight-bold);
    line-height: 1.35;
    overflow-wrap: anywhere;
  }

  .pair {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: var(--space-6);
    align-items: start;
  }

  .makes-row {
    display: flex;
    gap: var(--space-4);
  }

  .makes-row > * {
    flex: 1 1 0;
  }

  .made {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-6) var(--space-7);
    border: 1px solid var(--color-divider);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .made-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-6);
  }

  .made-words {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }

  .made-title {
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .made-body {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    padding-top: var(--space-5);
    border-top: 1px solid var(--color-divider);
    font-size: var(--text-base);
  }

  .exists {
    padding: var(--space-4) var(--space-5);
    border-radius: var(--radius-md);
    background: var(--color-note);
    color: var(--color-note-text);
    font-weight: var(--weight-semibold);
  }

  .warm {
    color: var(--color-tub-chip-text);
    font-size: var(--text-md);
    font-weight: var(--weight-semibold);
  }

  .nutrition {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
    min-width: 0;
    margin: 0;
    padding: 0;
    border: none;
  }

  legend {
    padding: 0 0 var(--space-4);
    color: var(--color-text-muted);
    font-size: var(--text-sm);
    font-weight: var(--weight-extrabold);
    letter-spacing: var(--tracking-overline);
    text-transform: uppercase;
  }

  legend span {
    font-weight: var(--weight-semibold);
    letter-spacing: 0;
    text-transform: none;
  }

  .nutrients {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(3.4rem, 1fr));
    gap: var(--space-3);
  }

  .nutrients .mw-label {
    font-size: var(--text-sm);
  }

  .nutrients .mw-input {
    padding: 0 var(--space-3);
    text-align: center;
  }

  .delete {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-2);
    padding-top: var(--space-7);
    border-top: 1px solid var(--color-divider);
  }

  .delete button {
    min-height: var(--touch-target);
    padding: 0;
    border: none;
    background: transparent;
    color: var(--color-warning-text);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  @media (min-width: 768px) {
    .editor {
      gap: var(--space-8);
    }

    .bar {
      margin: calc(-1 * var(--space-10)) calc(-1 * var(--space-11)) 0;
      padding: var(--space-9) var(--space-11) var(--space-7);
      grid-template-columns: 1fr auto auto;
      grid-template-areas: 'heading cancel save';
      gap: var(--space-4);
    }

    .heading {
      grid-area: heading;
    }

    .cancel {
      grid-area: cancel;
      justify-self: end;
      padding: 0 var(--space-8);
      border: 1px solid var(--color-border-strong);
      border-radius: var(--radius-full);
      background: var(--color-surface);
      color: var(--color-text);
      font-size: var(--text-base);
    }

    .save {
      grid-area: save;
    }

    h1 {
      font-size: 1.75rem;
      letter-spacing: var(--tracking-tight);
      text-align: left;
    }

    .lead {
      display: block;
      color: var(--color-text-muted);
      font-size: var(--text-md);
    }
  }

  @media (min-width: 1000px) {
    .grid {
      display: grid;
      grid-template-columns: minmax(18rem, 26rem) minmax(0, 1fr);
      grid-template-areas:
        'basics body'
        'rest body';
      align-items: start;
      column-gap: var(--space-11);
    }

    .basics {
      grid-area: basics;
    }

    .body {
      grid-area: body;
    }

    .rest {
      grid-area: rest;
    }
  }
</style>
