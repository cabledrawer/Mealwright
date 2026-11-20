<script lang="ts">
  // The Plan's parts with made-up meals (0.6 PR 3): the week grid, the phone's day list, the
  // phone's Month, the menu and the "Add" box. Nothing is saved or sent: every change is
  // ignored, because there is no server behind this page.
  import { FOOD_ITEM, type Plan } from '#lib/client/plan.js';
  import MealCell from '#lib/components/plan/MealCell.svelte';
  import PlanDays from '#lib/components/plan/PlanDays.svelte';
  import PlanMonth from '#lib/components/plan/PlanMonth.svelte';
  import PlanMonthPhone from '#lib/components/plan/PlanMonthPhone.svelte';
  import PlanSheet from '#lib/components/plan/PlanSheet.svelte';
  import PlanWeek from '#lib/components/plan/PlanWeek.svelte';
  import type { PlanActions, PlanTarget } from '#lib/planActions.js';
  import { PlanModel } from '#lib/plan.svelte.js';

  const recipe = (id: number, name: string, kcal: number | null, minutes: number | null) => ({
    id,
    position: 0,
    kind: 'recipe' as const,
    recipe: { id, name, removed: false, photo_url: null, time_minutes: minutes, kcal },
    tub_id: null,
    food: null,
    kept_name: null,
    servings: null,
    note: null,
    eating: null,
    cooked: false
  });
  const plain = (id: number, name: string) => ({
    id,
    position: 1,
    kind: FOOD_ITEM,
    recipe: null,
    tub_id: null,
    food: { id, name, removed: false },
    kept_name: null,
    servings: null,
    note: null,
    eating: null,
    cooked: false
  });

  const model = new PlanModel();
  model.today = '2026-10-17';
  model.anchor = '2026-10-17';
  model.startsOn = 1;
  model.slots = [
    { id: 1, name: 'Breakfast', position: 0, enabled: true },
    { id: 2, name: 'Lunch', position: 1, enabled: true },
    { id: 3, name: 'Snack', position: 2, enabled: false },
    { id: 4, name: 'Dinner', position: 3, enabled: true }
  ];
  const plan: Plan = {
    start: '2026-09-28',
    end: '2026-11-01',
    meals: [
      {
        id: 1,
        date: '2026-10-12',
        slot_id: 1,
        status: 'planned',
        eater_member_ids: [],
        kcal: 230,
        items: [recipe(1, 'Idli & podi', 230, 15)]
      },
      {
        id: 2,
        date: '2026-10-12',
        slot_id: 2,
        status: 'planned',
        eater_member_ids: [],
        kcal: 290,
        items: [
          recipe(2, 'Dosa', 230, 20),
          { ...recipe(3, 'Coconut chutney', 60, null), position: 1 }
        ]
      },
      {
        id: 3,
        date: '2026-10-14',
        slot_id: 4,
        status: 'planned',
        eater_member_ids: [],
        kcal: null,
        items: [
          recipe(4, 'A recipe with a very long name that has to wrap inside its card', null, 45)
        ]
      },
      {
        id: 4,
        date: '2026-10-17',
        slot_id: 4,
        status: 'planned',
        eater_member_ids: [],
        kcal: 340,
        items: [recipe(5, 'Vegetable upma', 340, 20), plain(6, 'Fruit')]
      }
    ],
    batch_cooks: [],
    tubs: []
  };
  model.plan = plan;
  model.loaded = true;

  let target = $state<PlanTarget | null>(null);
  let picked = $state('2026-10-17');
  const actions: PlanActions = {
    model,
    readonly: false,
    desktop: true,
    openMeal: (meal) => (target = { kind: 'meal', meal }),
    openItem: (meal, item) => (target = { kind: 'item', meal, item }),
    openCookOnce: () => {},
    openCooked: () => {},
    add: () => {},
    openDay: (day) => (target = { kind: 'day', day }),
    carryMeal: (meal) => ({ label: 'Meal', zones: true, drop: () => void meal }),
    carryItem: (meal) => ({ label: 'Item', zones: true, drop: () => void meal }),
    carryCook: (meal) => ({ label: 'Cook', zones: false, drop: () => void meal })
  };
  const phoneActions: PlanActions = { ...actions, desktop: false };
  const offlineActions: PlanActions = { ...actions, readonly: true };
</script>

<section id="plan">
  <h2>Plan: week grid, day list, month, the menu</h2>
  <p class="note">
    The week on a computer: a column per day, a row per meal that is on, cards that drag by mouse or
    finger and open a menu on click, Enter or a held finger. On a phone the week is a list of days
    and the month a dot grid. Offline, the plan can be read but every button is greyed.
  </p>
  <div class="week-demo"><PlanWeek {actions} /></div>
  <h3>One meal, filled and empty; offline</h3>
  <div class="cells">
    <MealCell {actions} day="2026-10-12" slot={model.slots[1]!} />
    <MealCell {actions} day="2026-10-13" slot={model.slots[1]!} />
    <MealCell actions={offlineActions} day="2026-10-12" slot={model.slots[1]!} />
  </div>
  <h3>Month on a computer</h3>
  <div class="month-demo"><PlanMonth {actions} show="both" /></div>
  <h3>On a phone: the day list and the month</h3>
  <div class="phone-demo">
    <PlanDays actions={phoneActions} days={['2026-10-12', '2026-10-17']} />
    <PlanMonthPhone
      actions={phoneActions}
      show="both"
      selected={picked}
      onselect={(day) => (picked = day)}
      onstart={() => {}}
      onstartahead={() => {}}
      oncook={() => {}}
    />
  </div>
  <p>
    <button type="button" onclick={() => (target = { kind: 'meal', meal: plan.meals[1]! })}
      >Open the menu</button
    >
  </p>
  <PlanSheet {actions} {target} onclose={() => (target = null)} />
</section>

<style>
  .note {
    max-width: 70ch;
    color: var(--color-text-muted);
  }

  .week-demo,
  .month-demo {
    display: flex;
    height: 460px;
    margin-bottom: var(--space-7);
  }

  .cells {
    display: grid;
    grid-template-columns: repeat(3, 160px);
    gap: var(--space-6);
    margin-bottom: var(--space-7);
  }

  .phone-demo {
    display: flex;
    flex-direction: column;
    gap: var(--space-6);
    max-width: 390px;
    margin-bottom: var(--space-7);
  }
</style>
