<script lang="ts">
  // The component gallery (spec "Keeping the UI good", item 3): every shared component in
  // its states, so a new screen can pick what it needs and the checker can look at them
  // all in one place. Development builds only: +page.ts drops this file from the real app.
  // Nothing here is saved or sent: the models behind the pantry rows are stand-ins.
  //
  // Light or dark: use the Theme switch at the top (the colours are page-wide, so there
  // is one theme at a time).
  //
  // Not shown yet (they need the server's answers): the ingredient editor and its sheet,
  // "Add to pantry", the ingredient picker and the Shopping list's rows, pack sheet, list
  // picker, put-away panel and "Did you buy 2?" card. They get a place here when the
  // gallery can fake those answers.
  import AskOnce from '$lib/components/AskOnce.svelte';
  import Button from '$lib/components/Button.svelte';
  import ConnectionNotice from '$lib/components/ConnectionNotice.svelte';
  import ConnectionStatus from '$lib/components/ConnectionStatus.svelte';
  import EmptyState from '$lib/components/EmptyState.svelte';
  import FilterChips from '$lib/components/FilterChips.svelte';
  import Icon, { type Name } from '$lib/components/Icon.svelte';
  import LotMenu from '$lib/components/LotMenu.svelte';
  import Logo from '$lib/components/Logo.svelte';
  import NewIngredient from '$lib/components/NewIngredient.svelte';
  import OfflineNote from '$lib/components/OfflineNote.svelte';
  import PackPicks from '$lib/components/PackPicks.svelte';
  import PageHeader from '$lib/components/PageHeader.svelte';
  import PantryGroup from '$lib/components/PantryGroup.svelte';
  import PlaceTabs from '$lib/components/PlaceTabs.svelte';
  import RecentChanges from '$lib/components/RecentChanges.svelte';
  import RecipeListRow from '$lib/components/RecipeListRow.svelte';
  import RecipesPopout from '$lib/components/RecipesPopout.svelte';
  import Sidebar from '$lib/components/Sidebar.svelte';
  import Switch from '$lib/components/Switch.svelte';
  import TabBar from '$lib/components/TabBar.svelte';
  import TextField from '$lib/components/TextField.svelte';
  import ThemeSwitch from '$lib/components/ThemeSwitch.svelte';
  import Toast from '$lib/components/Toast.svelte';
  import { askOnce } from '$lib/askOnce.svelte';
  import type { RecipeRow } from '$lib/client/recipes';
  import type { Change } from '$lib/client/types';
  import { network } from '$lib/network.svelte';
  import { newIngredient } from '$lib/newIngredient.svelte';
  import type { PantryModel } from '$lib/pantry.svelte';
  import type { PantryList } from '$lib/pantryList.svelte';
  import { samplePantry } from '$lib/testing/fakePantry';
  import { toasts } from '$lib/toast.svelte';

  // Read by the check that the real build has no gallery in it (e2e/tests/gallery.spec.ts).
  const MARKER = 'mealwright-gallery-marker-9c1e47';

  const ICONS: Name[] = [
    'today',
    'plan',
    'shopping',
    'pantry',
    'recipes',
    'auto',
    'light',
    'dark',
    'expand',
    'collapse',
    'back',
    'chevron-down',
    'search',
    'pencil',
    'calendar',
    'check'
  ];

  // --- Switch, fields -----------------------------------------------------------------
  let on = $state(true);
  let off = $state(false);
  let text = $state('Toor dal');
  let longName = $state(
    'துவரம் பருப்பு (toor dal, arhar dal, thuvaram paruppu) — the long name of an ingredient'
  );
  let password = $state('kitchen-secret');
  let empty = $state('');

  // --- Place tabs ---------------------------------------------------------------------
  const places = [
    { id: 'all', label: 'All', pinned: true },
    { id: 'fridge', label: 'Fridge', pinned: true },
    { id: 'freezer', label: 'Freezer' },
    { id: 'cupboard', label: 'Cupboard' },
    { id: 'spice', label: 'Spice rack' }
  ];
  let place = $state('fridge');
  let few = $state('fridge');

  // --- The pantry rows, with stand-in models ----------------------------------------------
  const sample = samplePantry();
  const fridge = sample.pantry.places[0]!;
  const pantryPlaces = sample.pantry.places.map(({ id, name, kind }) => ({ id, name, kind }));
  const saved = () => {
    toasts.show('Gallery: nothing is saved here.');
    return Promise.resolve({ ok: true });
  };
  const model = {
    setLeft: saved,
    setUseBy: saved,
    used: saved,
    binned: saved,
    toFreezer: saved,
    move: saved,
    leftOf: saved,
    usedSome: saved
  } as unknown as PantryModel;
  const shopping = {
    onList: (id: number) => id === 20,
    tap: () => {
      toasts.show('Gallery: nothing is added to the list.');
      return Promise.resolve();
    }
  } as unknown as PantryList;
  const pantryPack = sample.paneer[0]!;
  let menuLot = $state<typeof pantryPack | null>(null);
  let menuAnchor = $state<HTMLElement | null>(null);

  // --- Recipes ------------------------------------------------------------------------------
  const recipe = (id: number, name: string, extra: Partial<RecipeRow> = {}): RecipeRow => ({
    id,
    name,
    description: null,
    time_minutes: null,
    serves: 4,
    tags: [],
    ingredient_count: 5,
    kcal: null,
    stock: null,
    use_soon: null,
    stock_unchecked: false,
    ...extra
  });
  const recipeRows: RecipeRow[] = [
    recipe(1, 'Sambar', {
      time_minutes: 50,
      kcal: 320,
      stock: { counted: 7, missing: 1, can_cook_now: false }
    }),
    recipe(2, 'Palak paneer', {
      stock: { counted: 3, missing: 0, can_cook_now: true },
      use_soon: { foods: [{ id: 9, name: 'Spinach' }], use_by: '2026-10-20', days_left: 0 }
    }),
    recipe(3, 'Rajma', { time_minutes: 60 }),
    recipe(4, 'Chana masala', {
      time_minutes: 45,
      kcal: 380,
      stock: { counted: 6, missing: 0, can_cook_now: true }
    }),
    recipe(5, 'Veg biryani', {
      time_minutes: 75,
      kcal: 410,
      stock: { counted: 12, missing: 4, can_cook_now: false }
    }),
    recipe(
      6,
      'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது with a very long name',
      {
        time_minutes: 1440,
        kcal: 1234,
        use_soon: {
          foods: [
            { id: 1, name: 'Organic stone-ground whole wheat flour from the Saturday market' },
            { id: 2, name: 'Paneer' },
            { id: 3, name: 'Milk' }
          ],
          use_by: '2026-10-21',
          days_left: 1
        },
        stock: { counted: 4, missing: 2, can_cook_now: false }
      }
    )
  ];
  type Filter = 'all' | 'cook' | `tag:${string}`;
  let chosen = $state<Filter>('all');
  let chosenMany = $state<Filter>('tag:Quick');
  const fewFilters: { value: Filter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'cook', label: 'Can cook now' },
    { value: 'tag:Batch-friendly', label: 'Batch-friendly' }
  ];
  const manyFilters: { value: Filter; label: string }[] = [
    ...fewFilters,
    { value: 'tag:Quick', label: 'Quick' },
    { value: 'tag:Kids', label: 'Kids' },
    {
      value: 'tag:Festival and special-occasion cooking',
      label: 'Festival and special-occasion cooking'
    },
    { value: 'tag:Sunday', label: 'Sunday' },
    { value: 'tag:Freezer-friendly', label: 'Freezer-friendly' }
  ];

  // --- Recent changes -----------------------------------------------------------------------
  const who = { login_id: 1, name: 'Tess' };
  const change = (id: number, summary: string, extra: Partial<Change> = {}): Change => ({
    id,
    kind: 'stock_used',
    at: '2026-10-17T18:04:11Z',
    who,
    summary,
    can_undo: true,
    undo_until: '2026-10-24T18:04:11Z',
    undone: null,
    ...extra
  });
  const changes = [
    change(1, 'Used 200 g spinach'),
    change(2, 'Binned 1 pack paneer', { can_undo: false }),
    change(3, 'Undid: Used 200 g spinach', { kind: 'undo', can_undo: false })
  ];

  // --- Toasts and the dialogs that open from a button ------------------------------------------
  function toastUndo() {
    toasts.show('Used 200 g spinach', {
      action: { label: 'Undo', run: () => toasts.show('Undone: Used 200 g spinach') }
    });
  }
  function toastTwo() {
    toasts.show('Added 2 packs of paneer to the fridge', {
      extra: { label: 'Change', run: () => {} },
      action: { label: 'Undo', run: () => {} }
    });
  }
  function toastProblem() {
    toasts.show('Couldn’t save that. Please try again.', {
      tone: 'problem',
      action: { label: 'Try again', run: () => {} }
    });
  }
  function toastPlain() {
    toasts.show('Back online — all saved');
  }
  function toastLong() {
    toasts.show(
      'Added 12 packs of துவரம் பருப்பு (thuvaram paruppu) to the cupboard and the list for Saturday',
      { action: { label: 'Undo', run: () => {} } }
    );
  }

  function ask(kind: 'weight_per_ml' | 'size') {
    void askOnce.ask(
      kind === 'size'
        ? {
            food_id: 7,
            food_name: 'Toor dal',
            kind: 'size',
            question: 'How much is in one packet of toor dal?',
            unit: 'g',
            name: 'packet',
            suggested: 500
          }
        : {
            food_id: 8,
            food_name: 'Jaggery',
            kind: 'weight_per_ml',
            question: 'About how much does 1 cup of jaggery weigh?',
            unit: 'g',
            per: 'cup',
            suggested: null
          }
    );
  }

  // --- Offline bars -------------------------------------------------------------------------
  const wasOffline = network.offline;
  const wasWaiting = network.waiting;
  let pretendOffline = $state(true);
  $effect(() => {
    network.offline = pretendOffline;
    network.waiting = pretendOffline ? 3 : wasWaiting;
    return () => {
      network.offline = wasOffline;
      network.waiting = wasWaiting;
    };
  });
</script>

<div class="gallery" data-gallery={MARKER}>
  <header>
    <Logo size={36} />
    <div>
      <h1>Component gallery</h1>
      <p>
        Development builds only. Every shared component in its states. Use the Theme switch to see
        light and dark.
      </p>
    </div>
    <div class="theme"><ThemeSwitch variant="pill" /></div>
  </header>

  <nav aria-label="Sections">
    <a href="#buttons">Buttons</a>
    <a href="#switch">Switch</a>
    <a href="#fields">Text fields</a>
    <a href="#cards">Cards and notices</a>
    <a href="#toast">Toast</a>
    <a href="#dialogs">Dialogs</a>
    <a href="#tabs">Tabs</a>
    <a href="#pantry">Pantry rows</a>
    <a href="#recipes">Recipes</a>
    <a href="#changes">Recent changes</a>
    <a href="#chrome">Page chrome</a>
    <a href="#icons">Icons</a>
  </nav>

  <section id="buttons">
    <h2>Button</h2>
    <p class="note">The main action on a page; quiet is the other choice beside it.</p>
    <div class="row">
      <div class="cell"><Button>Save</Button></div>
      <div class="cell"><Button quiet>Back</Button></div>
      <div class="cell"><Button disabled>Save</Button></div>
      <div class="cell"><Button quiet disabled>Back</Button></div>
    </div>
  </section>

  <section id="switch">
    <h2>Switch</h2>
    <p class="note">The one on/off control, everywhere.</p>
    <div class="row">
      <label class="inline"><Switch bind:checked={on} label="On" /> On</label>
      <label class="inline"><Switch bind:checked={off} label="Off" /> Off</label>
      <label class="inline"><Switch checked disabled label="On, disabled" /> On, disabled</label>
      <label class="inline"><Switch disabled label="Off, disabled" /> Off, disabled</label>
    </div>
  </section>

  <section id="fields">
    <h2>Text field</h2>
    <div class="grid">
      <TextField id="g-empty" label="Name" bind:value={empty} autocomplete="off" />
      <TextField id="g-text" label="Name" bind:value={text} autocomplete="off" />
      <TextField
        id="g-hint"
        label="Username"
        bind:value={text}
        autocomplete="username"
        hint="Letters and numbers, no spaces."
      />
      <TextField
        id="g-error"
        label="Username"
        bind:value={empty}
        autocomplete="username"
        error="Enter a username."
      />
      <TextField
        id="g-password"
        label="Password"
        type="password"
        bind:value={password}
        autocomplete="current-password"
      />
      <TextField id="g-long" label="Name (long)" bind:value={longName} autocomplete="off" />
      <TextField
        id="g-disabled"
        label="Name (disabled)"
        value="Toor dal"
        autocomplete="off"
        disabled
      />
    </div>
  </section>

  <section id="cards">
    <h2>Empty state, offline note, connection notice</h2>
    <div class="stack">
      <EmptyState title="Nothing in your pantry yet">
        <p>
          Add what is in your cupboards, fridge and freezer, or tick things off your shopping list.
        </p>
      </EmptyState>
      <OfflineNote screen="Pantry" />
      <OfflineNote screen="Ingredients" />
      <OfflineNote screen="Recipes" />
      <OfflineNote screen="Settings" />
      <ConnectionNotice kind="plain-refused" />
      <ConnectionNotice kind="plain-allowed" />
    </div>
  </section>

  <section id="toast">
    <h2>Toast</h2>
    <p class="note">One at a time, bottom of the screen. Press a button to see each.</p>
    <div class="row">
      <button type="button" class="demo" onclick={toastPlain}>Message only</button>
      <button type="button" class="demo" onclick={toastUndo}>With Undo</button>
      <button type="button" class="demo" onclick={toastTwo}>Two buttons</button>
      <button type="button" class="demo" onclick={toastProblem}>Problem</button>
      <button type="button" class="demo" onclick={toastLong}>Long name</button>
    </div>
    <h3>Connection bar</h3>
    <p class="note">Only shows while offline.</p>
    <label class="inline">
      <Switch bind:checked={pretendOffline} label="Pretend to be offline" /> Pretend to be offline
    </label>
    <div class="frame bars">
      <ConnectionStatus layout="phone" />
      <ConnectionStatus layout="desktop" />
      <ConnectionStatus layout="dot" />
    </div>
  </section>

  <section id="dialogs">
    <h2>Dialogs</h2>
    <p class="note">Open from a button; Escape closes.</p>
    <div class="row">
      <button type="button" class="demo" onclick={() => ask('size')}>Ask once: packet size</button>
      <button type="button" class="demo" onclick={() => ask('weight_per_ml')}
        >Ask once: weight of a cup</button
      >
      <button type="button" class="demo" onclick={() => void newIngredient.choose('Curry leaves')}
        >How do you count it?</button
      >
    </div>
  </section>

  <section id="tabs">
    <h2>Place tabs</h2>
    <p class="note">Wide enough for all, and narrow enough that some go under More.</p>
    <div class="stack">
      <div class="narrow wide">
        <PlaceTabs tabs={places} bind:selected={few} panelId="g-panel-1" />
      </div>
      <div class="narrow">
        <PlaceTabs tabs={places} bind:selected={place} panelId="g-panel-2" />
      </div>
      <div class="narrow tight">
        <PlaceTabs tabs={places} bind:selected={place} panelId="g-panel-3" />
      </div>
      <div id="g-panel-1" role="tabpanel" class="note">Selected: {few}, {place}</div>
      <div id="g-panel-2" hidden></div>
      <div id="g-panel-3" hidden></div>
    </div>
  </section>

  <section id="pantry">
    <h2>Pantry rows, packet picks, packet menu</h2>
    <p class="note">Stand-in data; nothing is saved.</p>
    <div class="stack">
      {#each fridge.groups as group (group.food.id)}
        <PantryGroup {group} place={fridge} places={pantryPlaces} {model} {shopping} />
      {/each}
      <PantryGroup
        group={sample.pantry.places[2]!.groups[1]!}
        place={sample.pantry.places[2]!}
        places={pantryPlaces}
        {model}
        {shopping}
        showPlace
        also="chawal"
      />
    </div>
    <h3>Packet picks (¼ · ½ · ¾ · Full)</h3>
    <div class="stack">
      <p id="g-picks-label" class="note">How much is left?</p>
      <PackPicks lot={sample.yoghurt} name="Yoghurt" {model} labelledby="g-picks-label" />
    </div>
    <h3>Packet menu</h3>
    <button
      type="button"
      class="demo"
      onclick={(event) => {
        menuAnchor = event.currentTarget;
        menuLot = pantryPack;
      }}>Open the menu for a packet of paneer</button
    >
    <LotMenu
      lot={menuLot}
      name="Paneer"
      place={pantryPlaces[0]!}
      places={pantryPlaces}
      countedAs="weight"
      anchor={menuAnchor}
      {model}
      onclose={() => (menuLot = null)}
    />
  </section>

  <section id="recipes">
    <h2>Recipe rows, filter row, empty list</h2>
    <p class="note">
      A recipe with no photo has a plain warm square. The line shows only what is known; what is
      about to go off is orange. Rows become links with the recipe page.
    </p>
    <div class="stack">
      <div class="narrow card">
        {#each recipeRows as row (row.id)}
          <div class="divided"><RecipeListRow recipe={row} /></div>
        {/each}
      </div>
      <div class="narrow">
        <FilterChips
          options={fewFilters}
          selected={chosen}
          label="Show (few)"
          onselect={(v) => (chosen = v)}
        />
      </div>
      <div class="narrow">
        <FilterChips
          options={manyFilters}
          selected={chosenMany}
          label="Show (many)"
          onselect={(v) => (chosenMany = v)}
        />
      </div>
      <EmptyState title="No recipes yet">Recipes you add will show here.</EmptyState>
    </div>
  </section>

  <section id="changes">
    <h2>Recent changes</h2>
    <div class="stack">
      <RecentChanges {changes} onundo={() => toasts.show('Undone: Used 200 g spinach')} />
      <RecentChanges changes={[]} onundo={() => {}} />
    </div>
  </section>

  <section id="chrome">
    <h2>Page header, sidebar, bottom tabs</h2>
    <div class="stack">
      <PageHeader title="Pantry" overline="Saturday 17 October" subtitle="6 ingredients" />
      <PageHeader
        title="Ingredients"
        parent={{ href: '/recipes', label: 'Recipes' }}
        subtitle="Everything you can put in a recipe"
      >
        {#snippet actions()}<Button>+ New ingredient</Button>{/snippet}
      </PageHeader>
    </div>
    <h3>Recipes menu (collapsed sidebar)</h3>
    <div class="row">
      <RecipesPopout pathname="/recipes/ingredients" current />
    </div>
    <h3>Sidebar</h3>
    <div class="frame sidebar-frame"><Sidebar /></div>
    <h3>Bottom tabs</h3>
    <div class="frame tabbar-frame"><TabBar /></div>
    <h3>Theme switch</h3>
    <div class="row">
      <div class="cell"><ThemeSwitch variant="pill" /></div>
      <div class="cell"><ThemeSwitch variant="sidebar" /></div>
      <div class="cell"><ThemeSwitch variant="cycle" /></div>
    </div>
  </section>

  <section id="icons">
    <h2>Icons</h2>
    <ul class="icons">
      {#each ICONS as name (name)}
        <li><Icon {name} /> <span>{name}</span></li>
      {/each}
    </ul>
  </section>
</div>

<!-- The dialogs and the toast, as the app has them in its layout. -->
<AskOnce />
<NewIngredient />
<Toast />

<style>
  .gallery {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
    max-width: 960px;
    margin: 0 auto;
    padding: var(--space-8) var(--space-8) 160px;
  }

  header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-6);
  }

  header > div:first-of-type {
    flex: 1 1 260px;
  }

  h1 {
    font-size: var(--text-3xl);
    font-weight: var(--weight-extrabold);
  }

  h2 {
    font-size: var(--text-2xl);
    font-weight: var(--weight-extrabold);
  }

  h3 {
    margin-top: var(--space-6);
    font-size: var(--text-lg);
    font-weight: var(--weight-bold);
  }

  .note,
  header p {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  section {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  nav {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-6);
  }

  nav a {
    display: inline-flex;
    align-items: center;
    min-height: var(--touch-target);
    font-weight: var(--weight-bold);
  }

  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-6);
  }

  .cell {
    flex: 1 1 160px;
    min-width: 0;
  }

  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: var(--space-6);
  }

  .stack {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }

  .inline {
    display: inline-flex;
    align-items: center;
    gap: var(--space-4);
  }

  .demo {
    min-height: var(--touch-target);
    padding: 0 var(--space-6);
    border: none;
    border-radius: var(--radius-md);
    background: var(--color-fill);
    color: var(--color-text);
    font-weight: var(--weight-bold);
    cursor: pointer;
  }

  .narrow {
    max-width: 390px;
  }

  .narrow.wide {
    max-width: 520px;
  }

  .narrow.tight {
    max-width: 260px;
  }

  /* A box that holds fixed or sticky parts (the bars, the sidebar, the bottom tabs), so they
     sit here instead of on the screen. */
  .card {
    padding: var(--space-2) var(--space-6);
    border-radius: var(--radius-2xl);
    background: var(--color-surface);
  }

  .divided {
    border-bottom: 1px solid var(--color-divider);
  }

  .divided:last-child {
    border-bottom: none;
  }

  .frame {
    position: relative;
    overflow: hidden;
    transform: translateZ(0);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
  }

  .bars {
    min-height: 140px;
    padding: var(--space-4);
  }

  .bars :global(.status) {
    position: static;
  }

  .sidebar-frame {
    height: 640px;
  }

  .tabbar-frame {
    height: 96px;
  }

  .icons {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: var(--space-4);
    list-style: none;
  }

  .icons li {
    display: flex;
    align-items: center;
    gap: var(--space-3);
  }
</style>
