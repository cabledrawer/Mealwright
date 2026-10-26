<script lang="ts">
  // The component gallery (spec "Keeping the UI good", item 3): every shared component in
  // its states, so a new screen can pick what it needs and the checker can look at them
  // all in one place. Development builds only: +page.ts drops this file from the real app.
  // Nothing here is saved or sent: the models behind the pantry rows are stand-ins.
  //
  // Light or dark: use the Theme switch at the top (the colours are page-wide, so there
  // is one theme at a time).
  //
  // Not shown yet (they need the server's answers): the ingredient editor and its sheet
  // (but its "Used in N recipes" and "Remove from Ingredients" parts are below), "Add to
  // pantry", the ingredient picker and the Shopping list's rows, pack sheet, list picker,
  // put-away panel and "Did you buy 2?" card. They get a place here when the gallery can
  // fake those answers.
  import PlanGallery from './PlanGallery.svelte';
  import AlreadySheet from '#lib/components/import/AlreadySheet.svelte';
  import ImportStart from '#lib/components/import/ImportStart.svelte';
  import ReviewScreen from '#lib/components/import/ReviewScreen.svelte';
  import { boxFlow, reviewFlow } from '#lib/testing/importSamples.js';
  import AskOnce from '#lib/components/AskOnce.svelte';
  import ChooseRecipe from '#lib/components/ChooseRecipe.svelte';
  import ConflictSheet from '#lib/components/recipe/ConflictSheet.svelte';
  import EditorNote from '#lib/components/recipe/EditorNote.svelte';
  import IngredientPicker from '#lib/components/recipe/IngredientPicker.svelte';
  import LineList from '#lib/components/recipe/LineList.svelte';
  import PhotoField from '#lib/components/recipe/PhotoField.svelte';
  import ServesField from '#lib/components/recipe/ServesField.svelte';
  import StepList from '#lib/components/recipe/StepList.svelte';
  import TagsField from '#lib/components/recipe/TagsField.svelte';
  import Button from '#lib/components/Button.svelte';
  import ConnectionNotice from '#lib/components/ConnectionNotice.svelte';
  import ConnectionStatus from '#lib/components/ConnectionStatus.svelte';
  import EmptyState from '#lib/components/EmptyState.svelte';
  import FilterChips from '#lib/components/FilterChips.svelte';
  import Icon, { type Name } from '#lib/components/Icon.svelte';
  import SwipeRow from '#lib/components/SwipeRow.svelte';
  import UsedSheet from '#lib/components/UsedSheet.svelte';
  import LotMenu from '#lib/components/LotMenu.svelte';
  import Logo from '#lib/components/Logo.svelte';
  import NewIngredient from '#lib/components/NewIngredient.svelte';
  import OfflineNote from '#lib/components/OfflineNote.svelte';
  import PackPicks from '#lib/components/PackPicks.svelte';
  import OutsideConnections from '#lib/components/privacy/OutsideConnections.svelte';
  import OwnNetwork from '#lib/components/privacy/OwnNetwork.svelte';
  import PageHeader from '#lib/components/PageHeader.svelte';
  import PantryGroup from '#lib/components/PantryGroup.svelte';
  import AmountBox from '#lib/components/shopping/AmountBox.svelte';
  import ItemRow from '#lib/components/shopping/ItemRow.svelte';
  import RemoveConfirm from '#lib/components/shopping/RemoveConfirm.svelte';
  import PlaceTabs from '#lib/components/PlaceTabs.svelte';
  import RecentChanges from '#lib/components/RecentChanges.svelte';
  import RemoveIngredient from '#lib/components/RemoveIngredient.svelte';
  import UsedCount from '#lib/components/UsedCount.svelte';
  import UsedInRecipes from '#lib/components/UsedInRecipes.svelte';
  import KeepAwake from '#lib/components/KeepAwake.svelte';
  import MissingBar from '#lib/components/MissingBar.svelte';
  import NutritionStrip from '#lib/components/NutritionStrip.svelte';
  import RecipeIngredient from '#lib/components/RecipeIngredient.svelte';
  import RecipeListRow from '#lib/components/RecipeListRow.svelte';
  import RecipePhoto from '#lib/components/RecipePhoto.svelte';
  import RecipesPopout from '#lib/components/RecipesPopout.svelte';
  import ServingsStepper from '#lib/components/ServingsStepper.svelte';
  import { makesAmount } from '#lib/recipeAmounts.js';
  import Sidebar from '#lib/components/Sidebar.svelte';
  import Switch from '#lib/components/Switch.svelte';
  import TabBar from '#lib/components/TabBar.svelte';
  import TextField from '#lib/components/TextField.svelte';
  import ThemeSwitch from '#lib/components/ThemeSwitch.svelte';
  import Toast from '#lib/components/Toast.svelte';
  import { askOnce } from '#lib/askOnce.svelte.js';
  import type { PhotoOut, RecipeLine, RecipeOut, RecipeRow } from '#lib/client/recipes.js';
  import type { FoodRow } from '#lib/client/types.js';
  import { RecipeDraft, type DraftPhoto } from '#lib/recipes/draft.svelte.js';
  import type { Change } from '#lib/client/types.js';
  import type { OwnNetworkEntry, SwitchName } from '#lib/client/privacy.js';
  import { network } from '#lib/network.svelte.js';
  import { newIngredient } from '#lib/newIngredient.svelte.js';
  import type { PantryModel } from '#lib/pantry.svelte.js';
  import type { PantryList } from '#lib/pantryList.svelte.js';
  import type { Mark } from '#lib/recipeStock.js';
  import type { ScreenAwake } from '#lib/screenAwake.svelte.js';
  import type { PutAway } from '#lib/shopping/putAway.js';
  import type { ShoppingModel } from '#lib/shopping/store.svelte.js';
  import type { ViewItem } from '#lib/shopping/view.js';
  import { samplePantry } from '#lib/testing/fakePantry.js';
  import {
    food as shopFood,
    item as shopItem,
    tess,
    tick as shopTick
  } from '#lib/testing/fakeShopping.js';
  import { toasts } from '#lib/toast.svelte.js';

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
    'check',
    'grip',
    'close',
    'photo',
    'info',
    'alert',
    'cloud-off',
    'link',
    'note',
    'arrow-right'
  ];

  let usedSheet = $state<'weight' | 'count' | null>(null);

  // --- Settings → Privacy -----------------------------------------------------------------
  let importOn = $state(true);
  let photosOn = $state(false);
  const switchValues = (a: boolean, b: boolean): Record<SwitchName, boolean> => ({
    recipe_import: a,
    recipe_photos: b
  });
  const entry = (
    id: number,
    kind: OwnNetworkEntry['kind'],
    value: string,
    addresses: number | null = null,
    added_by = 'Tess'
  ): OwnNetworkEntry => ({ id, kind, value, addresses, added_by, added_on: '2026-10-22' });
  const oneEntry = [entry(1, 'name', 'wiki.home.example')];
  const someEntries = [
    entry(1, 'name', 'wiki.home.example'),
    entry(2, 'address', '192.168.1.20'),
    entry(3, 'range', '192.168.1.0/24', 256),
    entry(4, 'range', 'fd12:3456:789a::/48')
  ];
  const longEntries = [
    entry(
      1,
      'name',
      'a-very-long-name-for-a-wiki-on-the-home-server.in-the-spare-room.home.example.org',
      null,
      'Wilhelmina Featherstonehaugh-Montgomery'
    ),
    entry(2, 'range', '10.0.0.0/8', 16_777_216)
  ];
  const manyEntries = Array.from({ length: 12 }, (_, i) =>
    entry(i + 1, 'name', `server${i + 1}.home.example`)
  );
  let networkText = $state('');
  let networkTextSecond = $state('wiki.home.lan');
  let networkTextThird = $state('localhost');
  let showAlready = $state(false);

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

  // --- Shopping rows, with a stand-in model -------------------------------------------------
  const lineOf = (
    id: string,
    name: string,
    item: Parameters<typeof shopItem>[2] = {},
    food: Parameters<typeof shopFood>[3] = {},
    ticked = false
  ): ViewItem => {
    const ticks = ticked
      ? [
          shopTick(`t-${id}`, {
            by: tess,
            bought: item.amount ? { amount: item.amount, display: item.display ?? '' } : null
          })
        ]
      : [];
    return {
      item: shopItem(id, 1, { ticks, ...item }),
      food: shopFood(1, name, 'dry_goods', { sizes: [], ...food }),
      ticks
    };
  };
  const rows = {
    toorDal: lineOf('g-dal', 'Toor dal', { amount: 500, display: '500 g' }),
    noAmount: lineOf('g-roll', 'Kitchen roll', { amount: null, display: null }),
    long: lineOf(
      'g-long',
      'Dried red Kashmiri chillies, whole, from the Indian grocer on the high street',
      { amount: 2, display: '2 packets' }
    ),
    swiped: lineOf('g-onion', 'Onion', { amount: 4, display: '4' }, { counted_as: 'count' }),
    milk: lineOf(
      'g-milk',
      'Milk',
      { amount: 2000, display: '2 L' },
      { counted_as: 'volume' },
      true
    ),
    bare: lineOf('g-bare', 'Drumsticks', { amount: null, display: null }, {}, true),
    salt: lineOf('g-salt', 'Salt', { amount: 750, display: '750 g' }, { staple: true }, true)
  };
  const putAways: Record<string, PutAway> = {
    'g-milk': { kind: 'amount', place: 'Fridge', amount: '2 L' },
    'g-bare': { kind: 'none' },
    'g-salt': { kind: 'staple' }
  };
  const shopModel = {
    device: 'phone',
    placing: null,
    copy: { places: [] },
    placeName: () => 'Fridge',
    putAwayFor: (item: { id: string }) => putAways[item.id] ?? { kind: 'none' },
    sizesOf: () => Promise.resolve([]),
    tick: saved,
    untick: saved,
    undoTick: saved,
    setAmount: saved,
    remove: saved
  } as unknown as ShoppingModel;
  let asking = $state(false);

  // --- Ingredients and recipes -------------------------------------------------------------
  const usedIn = [
    'Dal tadka',
    'Dosa batter',
    'Lemon rice',
    'Rasam',
    'Sambar',
    'Sambar powder',
    'Tomato rasam'
  ].map((name, i) => ({ id: i + 1, name }));
  const longRecipe =
    'Spiced roasted cauliflower with tahini, pomegranate and a very long name that keeps going';
  const removeDemo = () => toasts.show('Gallery: nothing is removed here.');

  // --- Recipes ------------------------------------------------------------------------------
  const recipe = (id: number, name: string, extra: Partial<RecipeRow> = {}): RecipeRow => ({
    id,
    name,
    description: null,
    makes: null,
    photo: null,
    version: 1,
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
  // Photos for the gallery: little pictures drawn here as data (nothing is fetched). A wide one,
  // a tall one and an ordinary one show the cropping; "gone" is an address that answers nothing.
  const drawn = (width: number, height: number, from: string, to: string) =>
    'data:image/svg+xml,' +
    encodeURIComponent(
      `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">` +
        `<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${from}"/><stop offset="1" stop-color="${to}"/></linearGradient></defs>` +
        `<rect width="${width}" height="${height}" fill="url(#g)"/>` +
        `<circle cx="${width / 2}" cy="${height / 2}" r="${Math.min(width, height) / 3}" fill="#f4efe4"/>` +
        `<circle cx="${width / 2}" cy="${height / 2}" r="${Math.min(width, height) / 6}" fill="#c0522d"/></svg>`
    );
  const photoOf = (width: number, height: number, from: string, to: string): PhotoOut => {
    const picture = drawn(width, height, from, to);
    return {
      id: width * 1000 + height,
      width,
      height,
      url: picture,
      list_width: width >= height ? Math.round((156 * width) / height) : 156,
      list_height: width >= height ? 156 : Math.round((156 * height) / width),
      list_url: picture
    };
  };
  const dish = photoOf(1600, 1200, '#e0a458', '#7a9e4f');
  const tallDish = photoOf(300, 1600, '#d9822b', '#3f6b8c');
  const wideDish = photoOf(1600, 300, '#b5483a', '#e8c170');
  const goneDish: PhotoOut = {
    ...dish,
    id: 9,
    url: '/gallery-no-such-photo-large.jpg',
    list_url: '/gallery-no-such-photo-list.jpg'
  };
  const photoRows: RecipeRow[] = [
    recipe(11, 'Sambar', { photo: dish, time_minutes: 50, kcal: 320 }),
    recipe(12, 'A very tall photo', { photo: tallDish, time_minutes: 30 }),
    recipe(13, 'A very wide photo', { photo: wideDish, time_minutes: 30 }),
    recipe(14, 'A photo that is gone', { photo: goneDish, time_minutes: 20 }),
    recipe(
      15,
      'Spiced roasted cauliflower with tahini, pomegranate and a very long name that keeps going on to a third line',
      { photo: dish, time_minutes: 40, kcal: 290 }
    )
  ];
  type Filter = 'all' | 'cook' | 'soon' | `tag:${string}`;
  let chosen = $state<Filter>('all');
  let chosenMany = $state<Filter>('tag:Quick');
  const fewFilters: { value: Filter; label: string }[] = [
    { value: 'all', label: 'All' },
    { value: 'cook', label: 'Can cook now' },
    { value: 'soon', label: 'Use soon' },
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

  // --- The recipe page's parts ------------------------------------------------------------------
  const ingredient = (id: number, extra: Partial<RecipeLine>): RecipeLine => ({
    id,
    kind: 'ingredient',
    words: 'toor dal',
    amount: null,
    amount_text: null,
    unit: null,
    size: null,
    food: null,
    recipe: null,
    link: 'ingredient',
    note: null,
    ...extra
  });
  const NB = '\u00a0';
  const ingredientRows: { line: RecipeLine; amount: string | null; mark: Mark | null }[] = [
    {
      line: ingredient(1, {
        food: { id: 5, name: 'Toor dal', other_names: [] },
        words: 'Toor dal'
      }),
      amount: `200${NB}g`,
      mark: { kind: 'in', label: 'Cupboard' }
    },
    {
      line: ingredient(2, {
        food: { id: 5, name: 'Toor dal', other_names: [] },
        words: 'thuvaram paruppu',
        note: 'rinsed'
      }),
      amount: `1½${NB}cups`,
      mark: { kind: 'in', label: 'Freezer' }
    },
    {
      line: ingredient(3, { food: { id: 6, name: 'Onions', other_names: [] }, words: 'shallots' }),
      amount: '10',
      mark: { kind: 'list', label: 'On list' }
    },
    {
      line: ingredient(4, {
        food: { id: 7, name: 'Sambar powder', other_names: [] },
        words: 'sambar powder'
      }),
      amount: `2${NB}tbsp`,
      mark: { kind: 'staple', label: 'Staple' }
    },
    {
      line: ingredient(5, { food: { id: 8, name: 'Paneer', other_names: [] }, words: 'paneer' }),
      amount: `400${NB}g`,
      mark: { kind: 'short', label: 'Not enough' }
    },
    {
      line: ingredient(6, { food: { id: 9, name: 'Ghee', other_names: [] }, words: 'ghee' }),
      amount: `1${NB}tbsp`,
      mark: { kind: 'missing', label: null }
    },
    {
      line: ingredient(7, {
        link: 'recipe',
        recipe: { id: 3, name: 'Sambar powder' },
        words: 'masala'
      }),
      amount: `2${NB}tbsp`,
      mark: null
    },
    { line: ingredient(8, { link: 'none', words: 'salt to taste' }), amount: null, mark: null },
    {
      line: ingredient(9, { link: 'recipe_removed', words: 'old homemade paste' }),
      amount: `1${NB}cup`,
      mark: null
    },
    {
      line: ingredient(10, {
        food: {
          id: 10,
          name: 'Organic stone-ground whole wheat flour from the Saturday market',
          other_names: []
        },
        words: 'பச்சைப் பயறு (பாசிப்பயறு) முழுதாக, கரிம விவசாயிகளின் சந்தையில் வாங்கியது',
        note: 'soaked overnight and drained very well'
      }),
      amount: `1½${NB}packets`,
      mark: { kind: 'in', label: 'Spice rack' }
    }
  ];
  let serves = $state(4);
  let servesOne = $state(1);
  let servesMany = $state(99);
  // A recipe with Makes and no Serves: − / + in whole multiples of "Makes 200 g".
  let makesTimes = $state(1);
  let awakeOn = $state(false);
  const awakeAvailable = {
    supported: true,
    get on() {
      return awakeOn;
    },
    refused: false,
    set: (on: boolean) => {
      awakeOn = on;
      return Promise.resolve();
    }
  } as unknown as ScreenAwake;
  const awakeRefused = { supported: true, on: false, refused: true } as unknown as ScreenAwake;

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
    toasts.show('Couldn’t save that. Try again.', {
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

  // --- Recipe editor ------------------------------------------------------------------------
  const photo = {
    id: 1,
    width: 4,
    height: 3,
    url: 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%224%22 height=%223%22%3E%3Crect width=%224%22 height=%223%22 fill=%22%23e7b866%22/%3E%3C/svg%3E',
    list_width: 4,
    list_height: 3,
    list_url: ''
  };
  const photoStates: { label: string; photo: DraftPhoto }[] = [
    {
      label: 'Empty',
      photo: { shown: null, change: 'none', uploading: null, file: null, error: null }
    },
    {
      label: 'Uploading',
      photo: {
        shown: null,
        change: 'none',
        uploading: new File([], 'a.jpg'),
        file: null,
        error: null
      }
    },
    {
      label: 'With a photo',
      photo: { shown: photo, change: 'new', uploading: null, file: null, error: null }
    },
    {
      label: 'Too big (the server’s words)',
      photo: {
        shown: null,
        change: 'none',
        uploading: null,
        file: null,
        error: 'That photo is too big to use (over 50 megapixels). Try a smaller copy.'
      }
    }
  ];
  let editorServes = $state<number | null>(4);
  let servesCleared = $state<number | null>(null);
  let tags = $state(['Batch-friendly', 'South Indian']);
  const suggest = async () => [{ name: 'Quick' }, { name: 'Kids' }];
  const row = (id: number, name: string, matched: string | null = null) =>
    ({ id, name, matched_name: matched, other_names: [] }) as unknown as FoodRow;
  const searchEverything = async () => ({
    foods: [row(7, 'Toor dal', 'thuvaram paruppu'), row(8, 'Sambar onions', 'small onions')],
    recipes: [
      {
        id: 3,
        name: 'Sambar powder',
        description: null,
        version: 1,
        photo: null,
        makes: { amount: 200, amount_text: '200', unit: 'g' }
      },
      { id: 1, name: 'Sambar', description: null, version: 1, photo: null, makes: null },
      { id: 4, name: 'Sambar rice', description: null, version: 1, photo: null, makes: null }
    ]
  });
  const blocked = [
    { id: 1, name: 'Sambar', reason: 'A recipe can’t use itself.', chain: ['Sambar'] },
    {
      id: 4,
      name: 'Sambar rice',
      reason: 'Sambar can’t use Sambar rice, because Sambar rice uses Sambar.',
      chain: ['Sambar', 'Sambar rice']
    }
  ];
  const noLine = {
    amount: null,
    amount_text: null,
    unit: null,
    size: null,
    food: null,
    recipe: null
  };
  const rx = {
    id: 1,
    name: 'Sambar',
    description: 'Lentil & vegetable stew',
    time_minutes: 50,
    serves: 6,
    makes: null,
    made_ahead: false,
    homemade: null,
    tags: ['Quick'],
    nutrition: { kcal: 320, protein: null, carbs: null, fat: null, fibre: null },
    lines: [
      { ...noLine, id: 1, kind: 'heading', words: 'For the dal', link: null, note: null },
      {
        ...noLine,
        id: 2,
        kind: 'ingredient',
        words: 'thuvaram paruppu',
        amount: 200,
        amount_text: '200',
        unit: 'g',
        food: { id: 7, name: 'Toor dal' },
        link: 'ingredient',
        note: 'rinsed'
      },
      {
        ...noLine,
        id: 3,
        kind: 'ingredient',
        words: 'Sambar powder',
        amount: 2,
        amount_text: '2',
        unit: 'tbsp',
        recipe: { id: 3, name: 'Sambar powder' },
        link: 'recipe',
        note: null
      },
      { ...noLine, id: 4, kind: 'ingredient', words: 'karuveppilai', link: 'none', note: null },
      { ...noLine, id: 5, kind: 'ingredient', words: 'salt to taste', link: 'none', note: null }
    ],
    steps: [
      { id: 1, kind: 'heading', text: 'The dal' },
      { id: 2, kind: 'step', text: 'Rinse the dal and pressure-cook with the turmeric until soft.' }
    ],
    source_note: null,
    photo: null,
    used_by: [],
    version: 3,
    updated_at: '2026-10-19T18:04:11+00:00',
    updated_by: { login_id: 1, name: 'Tess' }
  } as RecipeOut;
  const draft = RecipeDraft.from(rx);
  const theirs = {
    ...rx,
    serves: 8,
    version: 4,
    lines: [
      { ...rx.lines[0]! },
      { ...rx.lines[1]!, amount: 300, amount_text: '300' },
      rx.lines[2]!,
      {
        ...noLine,
        id: 9,
        kind: 'ingredient',
        words: 'aubergine',
        amount: 1,
        amount_text: '1',
        link: 'none',
        note: null
      }
    ]
  } as RecipeOut;
  let wrenOpen = $state(false);
  let phoneWide = $state(true);
  const noErrors = {};

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
    <a href="#plan">Plan</a>
    <a href="#recipe-page">Recipe page</a>
    <a href="#recipe-panes">Desktop panes</a>
    <a href="#ingredient-recipes">Ingredients and recipes</a>
    <a href="#import">Import a recipe</a>
    <a href="#changes">Recent changes</a>
    <a href="#chrome">Page chrome</a>
    <a href="#recipe-editor">Recipe editor</a>
    <a href="#privacy">Privacy</a>
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
      <OfflineNote screen="Privacy" />
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

  <section id="shopping-rows">
    <h2>Shopping rows, amount box, "Remove?" question, status line</h2>
    <p class="note">
      Stand-in data; nothing is saved. Only the square ticks; the name and the amount open the
      amount box. A row slid to the left shows a red Remove (a finger does that on a phone).
    </p>
    <h3>Rows: with an amount, with none, a very long name, and swiped</h3>
    <ul class="shop-rows">
      <ItemRow model={shopModel} view={rows.toorDal} />
      <ItemRow model={shopModel} view={rows.noAmount} />
      <ItemRow model={shopModel} view={rows.long} />
      <ItemRow model={shopModel} view={rows.swiped} swiped />
    </ul>
    <h3>Ticked rows: where it went, with no amount, and a staple</h3>
    <ul class="shop-rows">
      <ItemRow model={shopModel} view={rows.milk} trolley />
      <ItemRow model={shopModel} view={rows.bare} trolley />
      <ItemRow model={shopModel} view={rows.salt} trolley />
    </ul>
    <h3>Amount box</h3>
    <div class="shop-rows">
      <AmountBox
        model={shopModel}
        view={rows.toorDal}
        onclose={() => {}}
        onmove={() => {}}
        onremove={() => (asking = true)}
      />
    </div>
    <h3>Remove? (a sheet on a phone, a dialog on a computer)</h3>
    <button type="button" class="demo" onclick={() => (asking = true)}>Ask: Remove Onion?</button>
    {#if asking}
      <RemoveConfirm
        name="Onion"
        onremove={() => {
          asking = false;
          toasts.show('Removed Onion', { action: { label: 'Undo', run: () => {} } });
        }}
        onkeep={() => (asking = false)}
      />
    {/if}
  </section>

  <section id="swipe-row">
    <h2>Swipe row: right action, left action, one side only</h2>
    <p class="note">
      On a phone a finger slides the row; the button it shows does the thing, and a swipe alone does
      nothing. On a computer the row is not swipeable: the same choices are buttons and menus in the
      row. Drafts (PR 5) use this with right = carry on reviewing, left = delete.
    </p>
    <h3>Both sides: right shows Used… (green), left shows Binned (red)</h3>
    <div class="swipes">
      {#each [null, 'right', 'left'] as const as start (start)}
        <SwipeRow
          open={start}
          right={{
            label: 'Used…',
            describe: 'Spinach',
            icon: 'check',
            tone: 'used',
            run: () => {}
          }}
          left={{
            label: 'Binned',
            describe: 'Spinach',
            icon: 'trash',
            tone: 'danger',
            run: () => {}
          }}
        >
          <div class="swipe-demo"><b>Spinach</b><span>Fridge · 200 g</span></div>
        </SwipeRow>
      {/each}
    </div>
    <h3>“How much did you use?”, which Used… opens</h3>
    <p class="inline">
      <Button onclick={() => (usedSheet = 'weight')}>Weight</Button>
      <Button onclick={() => (usedSheet = 'count')}>Count</Button>
    </p>
    <h3>One side: Move… (blue), and a very long name</h3>
    <div class="swipes">
      <SwipeRow
        open="right"
        right={{
          label: 'Move…',
          describe: 'Coriander',
          icon: 'arrow-right',
          tone: 'move',
          run: () => {}
        }}
      >
        <div class="swipe-demo"><b>Coriander</b><span>2 bunches</span></div>
      </SwipeRow>
      <SwipeRow
        left={{
          label: 'Remove',
          describe: 'from the list',
          icon: 'trash',
          tone: 'danger',
          run: () => {}
        }}
      >
        <div class="swipe-demo">
          <b>Extra virgin cold-pressed olive oil from the little shop round the corner</b>
          <span>1 bottle</span>
        </div>
      </SwipeRow>
    </div>
  </section>

  <section id="recipes">
    <h2>Recipe rows, filter row, empty list</h2>
    <p class="note">
      A recipe with no photo has a plain warm square. The line shows only what is known; what is
      about to go off is orange. Each row opens the recipe. "Use soon" in the filter row keeps the
      recipes that use something about to go off; Pantry’s Use soon card links to it ("Recipes for
      these" on a computer, "Recipes that use them →" on a phone).
    </p>
    <div class="stack">
      <div class="narrow card">
        {#each recipeRows as row (row.id)}
          <div class="divided"><RecipeListRow recipe={row} /></div>
        {/each}
      </div>
      <p class="note">
        With a photo it fills the square, cropped and never stretched (an ordinary one, a very tall
        one, a very wide one). A photo that can’t be fetched leaves the plain square, and a name
        that wraps keeps the square at the top.
      </p>
      <div class="narrow card">
        {#each photoRows as row (row.id)}
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

  <section id="recipe-page">
    <h2>Recipe page: ingredient lines, servings, nutrition, missing line, keep awake</h2>
    <p class="note">
      A line’s dot and words say where the ingredient is: green with its place, orange "On list",
      grey ring "Staple", dashed ring "Not enough", or dashed with no words (missing). The
      ingredient’s own name is small text under the words only when it differs. A line that uses
      another recipe opens it; "not linked" and "recipe removed" open nothing.
    </p>
    <div class="stack">
      <ul class="narrow card lines">
        {#each ingredientRows as row (row.line.id)}
          <li class="divided">
            <RecipeIngredient
              line={row.line}
              amount={row.amount}
              mark={row.mark}
              onopen={() => toasts.show('Gallery: the ingredient editor opens here.')}
            />
          </li>
        {/each}
      </ul>
      <div class="narrow stepper-row">
        <ServingsStepper value={serves} onchange={(v) => (serves = v)} />
        <ServingsStepper value={servesOne} onchange={(v) => (servesOne = v)} />
        <ServingsStepper value={servesMany} onchange={(v) => (servesMany = v)} />
        <ServingsStepper
          value={makesTimes}
          makes={makesAmount({ amount: 200, amount_text: '200', unit: 'g' }, makesTimes)}
          onchange={(v) => (makesTimes = v)}
        />
        <ServingsStepper
          value={99}
          makes={makesAmount({ amount: 1.5, amount_text: '1½', unit: 'l' }, 99)}
          onchange={() => {}}
        />
      </div>
      <p class="note">
        The recipe’s photo: a box 170 px tall above the name on a phone, cropped to fill (an
        ordinary one, a very tall one, a very wide one). A recipe with no photo, or a photo that
        can’t be fetched, has no box at all. On a computer it sits beside the nutrition figures and
        wraps above them when there is no room.
      </p>
      <div class="narrow stack">
        <RecipePhoto photo={dish} name="Sambar" />
        <RecipePhoto photo={tallDish} name="A very tall photo" />
        <RecipePhoto photo={wideDish} name="A very wide photo" />
        <RecipePhoto photo={goneDish} name="A photo that is gone" />
        <RecipePhoto photo={null} name="No photo" />
      </div>
      <div class="wide-facts">
        <RecipePhoto photo={dish} name="Sambar" beside />
        <div class="facts-figures">
          <NutritionStrip nutrition={{ kcal: 320, protein: 16, carbs: 48, fat: 7.5, fibre: 11 }} />
        </div>
      </div>
      <div class="narrow stack">
        <NutritionStrip nutrition={{ kcal: 320, protein: 16, carbs: 48, fat: 7.5, fibre: 11 }} />
        <NutritionStrip nutrition={{ kcal: 320, protein: null, carbs: 48, fat: 0, fibre: null }} />
        <NutritionStrip
          nutrition={{ kcal: null, protein: null, carbs: null, fat: null, fibre: null }}
        />
      </div>
      <div class="narrow stack">
        <MissingBar count={1} onadd={() => toasts.show('Gallery: nothing is added to the list.')} />
        <MissingBar
          count={12}
          onadd={() => toasts.show('Gallery: nothing is added to the list.')}
        />
      </div>
      <div class="narrow stack">
        <KeepAwake awake={awakeAvailable} />
        <KeepAwake awake={awakeRefused} />
        <p class="note">(Where the browser can’t keep the screen awake, nothing is drawn.)</p>
      </div>
    </div>
  </section>

  <PlanGallery />

  <section id="recipe-panes">
    <h2>Desktop Recipes: the list pane, the reading pane</h2>
    <p class="note">
      On a computer, Recipes is three panes: the sidebar, All recipes and the recipe being read. In
      the middle pane each row is a card of its own, the open recipe’s row lifted; on the reading
      pane the nutrition, Keep screen awake and servings sit on a quiet fill. With no recipe open
      the reading pane says "Choose a recipe". Below the width where they fit, it is one page at a
      time, as on a phone.
    </p>
    <div class="panes-demo">
      <div class="list-demo">
        {#each recipeRows.slice(0, 4) as row, i (row.id)}
          <RecipeListRow recipe={row} pane current={i === 1} />
        {/each}
      </div>
      <div class="reading-demo">
        <NutritionStrip nutrition={{ kcal: 320, protein: 16, carbs: 48, fat: 7.5, fibre: 11 }} />
        <KeepAwake awake={awakeAvailable} />
        <div class="stepper-row">
          <ServingsStepper value={serves} onchange={(v) => (serves = v)} />
        </div>
      </div>
      <div class="reading-demo"><ChooseRecipe /></div>
    </div>
  </section>

  <section id="ingredient-recipes">
    <h2>Ingredients and the recipes that use them</h2>
    <p class="note">
      In the Ingredients list each row ends with how many recipes use the ingredient ("5 recipes" on
      a phone; the number alone under "Recipes" on a computer; nothing when none do). In the
      ingredient editor, "Used in N recipes" links to each recipe (a long list is folded behind "+ 2
      more"), and "Remove from Ingredients" says how many recipes use it first: they don’t block it,
      their lines keep their words and show "not linked". A recipe’s own made-ahead ingredient says
      why it can’t be removed instead.
    </p>
    <div class="stack">
      <h3>The count at the end of a row</h3>
      <div class="row">
        <UsedCount count={0} />
        <UsedCount count={1} />
        <UsedCount count={5} />
        <UsedCount count={214} />
      </div>
      <h3>Used in recipes (editor)</h3>
      <div class="narrow stack">
        <UsedInRecipes recipes={[]} count={0} />
        <UsedInRecipes recipes={[{ id: 1, name: 'Sambar' }]} count={1} />
        <UsedInRecipes recipes={usedIn.slice(0, 3)} count={3} />
        <UsedInRecipes recipes={usedIn} count={usedIn.length} />
        <UsedInRecipes recipes={[{ id: 9, name: longRecipe }]} count={1} />
      </div>
      <h3>Remove from Ingredients (editor)</h3>
      <div class="narrow stack">
        <RemoveIngredient usedIn={0} madeBy={null} removable onremove={removeDemo} />
        <RemoveIngredient usedIn={1} madeBy={null} removable onremove={removeDemo} />
        <RemoveIngredient usedIn={3} madeBy={null} removable onremove={removeDemo} />
        <RemoveIngredient
          usedIn={1}
          madeBy={{ id: 4, name: 'Dosa batter' }}
          removable
          onremove={removeDemo}
        />
        <p class="note">
          (Some of it in the pantry, or on a shopping list: nothing is drawn, as before.)
        </p>
        <RemoveIngredient usedIn={2} madeBy={null} removable={false} onremove={removeDemo} />
      </div>
    </div>
  </section>

  <section id="import">
    <h2>Import a recipe: the box, the review, "You already have this recipe"</h2>
    <p class="note">
      The one box takes a link or pasted text. Importing from links switched off (an admin sees
      Settings, a member is told an admin can switch it on), another refusal, and the box while
      reading. While "Download recipe photos" is off, a note under "How it works" says photos aren’t
      downloaded and links to Settings → Privacy (the second box; it is left out while the switch is
      on or isn’t known). The review has a line in each state: matched, staple, to confirm, needs
      you, a line that couldn’t be read, a very long name and a heading. "Save & plan it" is not
      there until 0.6.
    </p>
    <div class="stack">
      <div class="narrow"><ImportStart flow={boxFlow('')} /></div>
      <div class="narrow"><ImportStart flow={boxFlow('https://kitchen.example/sambar')} /></div>
      <div class="narrow">
        <ImportStart flow={boxFlow('https://kitchen.example/sambar')} photosOff />
      </div>
      <div class="narrow">
        <ImportStart
          flow={boxFlow('https://kitchen.example/sambar', {
            code: 'import_switched_off',
            message: 'Importing from links is switched off',
            switchedOff: true,
            admin: true
          })}
        />
      </div>
      <div class="narrow">
        <ImportStart
          flow={boxFlow('https://kitchen.example/sambar', {
            code: 'import_switched_off',
            message: 'Importing from links is switched off. An admin can switch it on.',
            switchedOff: true,
            admin: false
          })}
        />
      </div>
      <div class="narrow">
        <ImportStart
          flow={boxFlow('https://kitchen.example/menu.pdf', {
            code: 'not_a_page',
            message: 'This link isn’t a web page.',
            switchedOff: false,
            admin: false
          })}
        />
      </div>
      <div class="narrow">
        <ImportStart flow={boxFlow('Sambar\n1 cup toor dal', null, 'reading')} />
      </div>
      <div class="narrow"><ReviewScreen flow={reviewFlow()} phone /></div>
      <div class="row">
        <button type="button" class="demo" onclick={() => (showAlready = true)}
          >You already have this recipe</button
        >
      </div>
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
        parent={{ href: '/(app)/recipes', label: 'Recipes' }}
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

  <section id="recipe-editor">
    <h2>Recipe editor</h2>
    <p class="note">
      The boxes and parts of New recipe and Edit recipe. Nothing here is saved or sent.
    </p>

    <h3>Photo</h3>
    <div class="grid">
      {#each photoStates as state (state.label)}
        <div class="cell">
          <p class="note">{state.label}</p>
          <PhotoField photo={state.photo} onpick={() => {}} onremove={() => {}} />
        </div>
      {/each}
    </div>

    <h3>Boxes, buttons and notes</h3>
    <div class="grid">
      <div class="mw-field">
        <label class="mw-label" for="g-rx-name">Name</label>
        <textarea id="g-rx-name" class="mw-input" rows="2"
          >Amma’s Sunday drumstick and shallot sambar with freshly roasted sambar powder</textarea
        >
      </div>
      <div class="mw-field">
        <label class="mw-label" for="g-rx-bad"
          >Time <span class="mw-optional">(minutes)</span></label
        >
        <input id="g-rx-bad" class="mw-input" aria-invalid="true" value="1h" />
        <span class="mw-error">Use whole minutes, from 1 to 14,400.</span>
      </div>
      <div class="mw-field">
        <label class="mw-label" for="g-rx-unit">Unit</label>
        <select id="g-rx-unit" class="mw-input"><option>g</option><option>tbsp</option></select>
        <span class="mw-hint">A small hint under a box.</span>
      </div>
      <div class="row">
        <button type="button" class="mw-pill">Change photo</button>
        <button type="button" class="mw-pill" disabled>Disabled</button>
        <button type="button" class="mw-add">+ Add ingredient</button>
        <button type="button" class="mw-icon" aria-label="Take out"
          ><Icon name="close" size={18} /></button
        >
      </div>
    </div>
    <div class="stack narrow">
      <EditorNote tone="offline">You’re offline. Save when you’re back online.</EditorNote>
      <EditorNote tone="trouble">
        <span>Couldn’t save. Try again.</span>
        <button type="button" class="mw-pill">Try again</button>
      </EditorNote>
      <EditorNote tone="conflict">
        <span>Wren changed this recipe after you opened it.</span>
        <span class="row">
          <button type="button" class="mw-pill" onclick={() => (wrenOpen = true)}
            >See Wren’s version</button
          >
          <button type="button" class="demo">Save mine anyway</button>
        </span>
      </EditorNote>
    </div>

    <h3>Serves, tags</h3>
    <div class="grid">
      <ServesField bind:serves={editorServes} />
      <ServesField bind:serves={servesCleared} />
      <TagsField bind:tags {suggest} />
    </div>

    <h3>Pick an ingredient (a recipe that would make a loop is greyed out)</h3>
    <div class="narrow">
      <IngredientPicker
        query="sam"
        search={searchEverything}
        {blocked}
        onpick={() => toasts.show('Gallery: nothing is picked.')}
        oncreate={() => toasts.show('Gallery: this opens “How do you count it?”.')}
      />
    </div>

    <h3>Ingredient lines and method</h3>
    <label class="inline"
      ><Switch bind:checked={phoneWide} label="Pick from a sheet" /> Pick from a sheet (phone) instead
      of under the line</label
    >
    <div class="wide">
      <LineList
        {draft}
        phone={phoneWide}
        errors={noErrors}
        {blocked}
        search={searchEverything}
        announce={() => {}}
      />
      <StepList {draft} errors={noErrors} announce={() => {}} />
    </div>

    <h3>Wren’s version</h3>
    <button type="button" class="demo" onclick={() => (wrenOpen = true)}>Open Wren’s version</button
    >
    {#if wrenOpen}
      <ConflictSheet
        who="Wren"
        opened={rx}
        {theirs}
        phone={phoneWide}
        onclose={() => (wrenOpen = false)}
        onsave={() => (wrenOpen = false)}
      />
    {/if}
  </section>

  <section id="privacy">
    <h2>Settings → Privacy: outside connections, your own network</h2>
    <p class="note">
      An admin changes them. A member sees them and a note saying why. Offline they show as last
      loaded and can’t be changed.
    </p>
    <h3>Outside connections</h3>
    <div class="grid">
      <OutsideConnections
        anchor="g-privacy-admin"
        values={switchValues(importOn, photosOn)}
        onchange={(name, on) => (name === 'recipe_import' ? (importOn = on) : (photosOn = on))}
      />
      <OutsideConnections
        anchor="g-privacy-member"
        values={switchValues(true, false)}
        locked="member"
        onchange={() => {}}
      />
      <OutsideConnections
        anchor="g-privacy-offline"
        values={switchValues(false, true)}
        locked="offline"
        onchange={() => {}}
      />
      <OutsideConnections
        anchor="g-privacy-problem"
        values={switchValues(false, false)}
        problem="Couldn’t reach your Mealwright server. Nothing was changed."
        onchange={() => {}}
      />
    </div>
    <h3>Your own network</h3>
    <div class="grid">
      <OwnNetwork
        anchor="g-network-empty"
        entries={[]}
        bind:value={networkText}
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-one"
        entries={oneEntry}
        bind:value={networkTextSecond}
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-some"
        entries={someEntries}
        value=""
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-long"
        entries={longEntries}
        value=""
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-many"
        entries={manyEntries}
        value=""
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-refused"
        entries={oneEntry}
        bind:value={networkTextThird}
        problem="That can’t be added: this server itself (localhost), link-local and cloud “metadata” addresses are always blocked."
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-adding"
        entries={oneEntry}
        value="nas.home.lan"
        adding
        removeProblem="Couldn’t reach your Mealwright server. Nothing was changed."
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-member"
        entries={someEntries}
        locked="member"
        onadd={() => {}}
        onremove={() => {}}
      />
      <OwnNetwork
        anchor="g-network-offline"
        entries={oneEntry}
        locked="offline"
        onadd={() => {}}
        onremove={() => {}}
      />
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

<UsedSheet
  open={usedSheet !== null}
  name={usedSheet === 'count' ? 'Eggs' : 'Spinach'}
  detail={usedSheet === 'count' ? 'Fridge · 9 left' : 'Fridge · 200 g · use by Today'}
  countedAs={usedSheet === 'count' ? 'count' : 'weight'}
  total={usedSheet === 'count' ? 9 : 200}
  allWords={usedSheet === 'count' ? '9' : '200 g'}
  onall={() => (usedSheet = null)}
  onpart={() => (usedSheet = null)}
  onleft={() => (usedSheet = null)}
  onclose={() => (usedSheet = null)}
/>

{#if showAlready}
  <AlreadySheet
    already={{
      recipe: { id: 1, name: 'Sambar' },
      site: 'kitchen.example',
      importedAt: '2026-10-03T10:00:00Z',
      photo: null
    }}
    oncopy={() => (showAlready = false)}
    onclose={() => (showAlready = false)}
  />
{/if}

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

  .swipes {
    display: flex;
    flex-direction: column;
    max-width: 420px;
    border-radius: var(--radius-xl);
    overflow: hidden;
  }

  .swipe-demo {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-height: 60px;
    padding: var(--space-3) var(--space-8);
    border-bottom: 1px solid var(--color-divider);
  }

  .swipe-demo span {
    color: var(--color-text-muted);
    font-size: var(--text-base);
  }

  .shop-rows {
    max-width: 420px;
    margin: 0;
    padding: var(--space-1) 14px;
    border-radius: var(--radius-xl);
    background: var(--color-surface);
    list-style: none;
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

  .wide {
    display: flex;
    flex-direction: column;
    gap: var(--space-9);
    max-width: 900px;
  }

  .narrow.wide {
    max-width: 520px;
  }

  /* The computer's photo-beside-the-figures row (RecipeScreen's .facts). */
  .wide-facts {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: var(--space-7);
    max-width: 760px;
  }

  .facts-figures {
    display: flex;
    flex: 2 1 360px;
    flex-direction: column;
    justify-content: center;
    gap: var(--space-7);
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

  ul.lines {
    margin: 0;
    padding: var(--space-2) var(--space-6);
    list-style: none;
  }

  .stepper-row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-4);
  }

  .panes-demo {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
    gap: var(--space-7);
  }

  .list-demo {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-ground);
    outline: 1px solid var(--color-border);
  }

  .reading-demo {
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    padding: var(--space-7);
    border-radius: var(--radius-xl);
    background: var(--color-chrome);
    outline: 1px solid var(--color-border);
    --reading-card: var(--color-reading-card);
    --reading-chip: var(--color-reading-chip);
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
