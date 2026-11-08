import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { Recipe, RecipeLine, RecipeStep } from '#lib/client/recipes.js';
import { CookTimers, TICK_MS } from '#lib/cookTimers.svelte.js';
import { ScreenAwake } from '#lib/screenAwake.svelte.js';
import CookMode from './CookMode.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

vi.mock('#lib/chime.js', () => ({ primeChime: vi.fn(), playChime: vi.fn(() => []) }));

/** A part of the text: the matcher alone wants all of it. */
const has = (part: string) => new RegExp(part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));

/** The text of an element holds this (the matcher on its own wants all of it). */
const shows = (where: { element(): Element }, part: RegExp) =>
  vi.waitFor(() => expect(where.element().textContent ?? '').toMatch(part));

const step = (id: number, text: string): RecipeStep => ({ id, kind: 'step', text });
const heading = (id: number, text: string): RecipeStep => ({ id, kind: 'heading', text });
const line = (
  id: number,
  name: string,
  amount: string | null,
  extra: Partial<RecipeLine> = {}
): RecipeLine => ({
  id,
  kind: 'ingredient',
  words: name.toLowerCase(),
  amount: amount ? Number(amount) : null,
  amount_text: amount,
  unit: null,
  size: null,
  food: { id: id + 100, name, other_names: [] },
  recipe: null,
  link: 'ingredient',
  note: null,
  ...extra
});

const LINES: RecipeLine[] = [
  { ...line(1, 'x', null), kind: 'heading', words: 'For the dal', food: null, link: null },
  line(2, 'Tamarind', null, { unit: 'g', amount: 30, amount_text: '30' }),
  line(3, 'Onions', '3'),
  line(4, 'Shallots', '15')
];

const recipe = (steps: RecipeStep[], lines: RecipeLine[] = LINES): Recipe => ({
  id: 1,
  name: 'Sambar',
  description: null,
  time_minutes: null,
  serves: 4,
  makes: null,
  made_ahead: false,
  tags: [],
  nutrition: { kcal: null, protein: null, carbs: null, fat: null, fibre: null },
  lines,
  steps,
  source_note: null,
  photo: null,
  version: 1
});

const FOUR = [
  step(1, 'Boil the dal.'),
  step(2, 'Soak the tamarind for 10 minutes, then chop the onions.'),
  step(3, 'Fry the shallots.'),
  step(4, 'Serve.')
];

describe('Cook mode', () => {
  const mounted: ReturnType<typeof mount>[] = [];
  let timers: CookTimers;
  let awake: ScreenAwake;
  const onexit = vi.fn();
  const oncooked = vi.fn();
  const onperstep = vi.fn();

  function open(
    r: Recipe,
    extra: { perStep?: boolean; cooked?: boolean; settling?: boolean } = {}
  ): { leaveOr: (go: () => void) => void } {
    const target = document.body.appendChild(document.createElement('div'));
    const component = mount(CookMode, {
      target,
      props: {
        recipe: r,
        timers,
        awake,
        perStep: extra.perStep ?? false,
        onperstep,
        onexit,
        oncooked: extra.cooked === false ? null : oncooked,
        settling: extra.settling ?? false
      }
    });
    mounted.push(component);
    flushSync();
    return component as unknown as { leaveOr: (go: () => void) => void };
  }

  const count = () => page.getByTestId('step-count');
  const text = () => page.getByTestId('step-text');
  const next = () => page.getByRole('button', { name: 'Next →' });
  const back = () => page.getByRole('button', { name: '← Back' });

  beforeEach(async () => {
    await page.viewport(390, 844);
    timers = new CookTimers();
    awake = new ScreenAwake();
    onexit.mockClear();
    oncooked.mockClear();
    onperstep.mockClear();
  });

  afterEach(() => {
    for (const component of mounted.splice(0)) unmount(component);
    document.body.innerHTML = '';
    timers.stopAll();
    vi.useRealTimers();
    delete (navigator as unknown as Record<string, unknown>).wakeLock;
  });

  describe('the steps', () => {
    it('shows one big step at a time, with Back and Next', async () => {
      open(recipe(FOUR));
      await shows(count(), has('Step 1 of 4'));
      await shows(text(), has('Boil the dal.'));
      await expect.element(back()).toBeDisabled();
      await next().click();
      await shows(count(), has('Step 2 of 4'));
      await shows(text(), has('Soak the tamarind'));
      await back().click();
      await shows(count(), has('Step 1 of 4'));
      // Big: well over the size of the page's body text.
      expect(parseFloat(getComputedStyle(text().element()).fontSize)).toBeGreaterThanOrEqual(28);
    });

    it('moves with the arrow keys', async () => {
      open(recipe(FOUR));
      await userEvent.keyboard('{ArrowRight}');
      await shows(count(), has('Step 2 of 4'));
      await userEvent.keyboard('{ArrowRight}{ArrowRight}');
      await shows(count(), has('Step 4 of 4'));
      await userEvent.keyboard('{ArrowRight}');
      await shows(count(), has('Step 4 of 4'));
      await userEvent.keyboard('{ArrowLeft}');
      await shows(count(), has('Step 3 of 4'));
    });

    /** A finger on the step: down, then each move, then up (no moves: a flick). */
    const finger = (body: Element, moves: [number, number][], end?: [number, number]) => {
      const event = (type: string, [dx, dy]: [number, number]) =>
        body.dispatchEvent(
          new PointerEvent(type, {
            clientX: 200 + dx,
            clientY: 300 + dy,
            pointerId: 1,
            bubbles: true
          })
        );
      event('pointerdown', [0, 0]);
      for (const move of moves) event('pointermove', move);
      if (end) event('pointerup', end);
      flushSync();
    };
    const slide = () => document.querySelector<HTMLElement>('[data-testid="slide"]')!;
    const stillMoving = () => slide().dataset.moving === 'true';
    const rest = () => vi.waitFor(() => expect(stillMoving()).toBe(false));
    const shift = () => new DOMMatrix(getComputedStyle(slide()).transform).m41;

    it('moves with a swipe, and a short or mostly downward drag does nothing', async () => {
      open(recipe(FOUR));
      const body = document.querySelector('.body')!;
      finger(body, [], [-120, 0]);
      await shows(count(), has('Step 2 of 4'));
      await rest();
      finger(body, [], [20, 0]);
      finger(body, [], [-100, 200]);
      await shows(count(), has('Step 2 of 4'));
      finger(body, [], [120, 0]);
      await shows(count(), has('Step 1 of 4'));
    });

    it('follows the finger, then slides to the next step (F145)', async () => {
      open(recipe(FOUR));
      const body = document.querySelector('.body')!;
      finger(body, [
        [-30, 0],
        [-70, 2]
      ]);
      expect(shift()).toBe(-70);
      await shows(count(), has('Step 1 of 4')); // not changed until the finger lifts
      body.dispatchEvent(
        new PointerEvent('pointerup', { clientX: 130, clientY: 302, pointerId: 1, bubbles: true })
      );
      flushSync();
      await shows(count(), has('Step 2 of 4'));
      await rest();
      expect(shift()).toBe(0);
    });

    it('springs back when the swipe does not go far enough, or there is no step that way (F145)', async () => {
      open(recipe(FOUR));
      const body = document.querySelector('.body')!;
      finger(body, [[-30, 0]], [-30, 0]);
      await rest();
      expect(shift()).toBe(0);
      await shows(count(), has('Step 1 of 4'));
      // Right at the first step: the step gives a little, goes nowhere, and comes back.
      finger(body, [[100, 0]]);
      expect(shift()).toBe(25);
      body.dispatchEvent(
        new PointerEvent('pointerup', { clientX: 300, clientY: 300, pointerId: 1, bubbles: true })
      );
      flushSync();
      await rest();
      expect(shift()).toBe(0);
      await shows(count(), has('Step 1 of 4'));
    });

    it('a sideways drag holds the pointer, and a cancelled one springs back', async () => {
      open(recipe(FOUR));
      const body = document.querySelector('.body') as HTMLElement;
      const hold = vi.spyOn(body, 'setPointerCapture').mockImplementation(() => {});
      finger(body, [[-40, 0]]);
      expect(hold).toHaveBeenCalledWith(1);
      expect(shift()).toBe(-40);
      // Held by the step, the lift outside it still arrives here; so does a cancel.
      body.dispatchEvent(new PointerEvent('pointercancel', { pointerId: 1, bubbles: true }));
      flushSync();
      await rest();
      expect(shift()).toBe(0);
      await shows(count(), has('Step 1 of 4'));
    });

    it('Next pressed while a swipe is still sliding is ignored, not overridden (L4)', async () => {
      open(recipe(FOUR));
      const body = document.querySelector('.body')!;
      finger(body, [], [-120, 0]); // slides to step 2
      expect(stillMoving()).toBe(true);
      (next().element() as HTMLElement).click();
      flushSync();
      // The press did nothing of its own: the step is still the one the swipe left.
      expect(count().element().textContent).toContain('Step 1 of 4');
      await rest();
      await shows(count(), has('Step 2 of 4'));
      await next().click();
      await shows(count(), has('Step 3 of 4'));
    });

    it('a mostly downward drag does not move the step (it is a scroll)', async () => {
      open(recipe(FOUR));
      const body = document.querySelector('.body')!;
      finger(
        body,
        [
          [-20, 60],
          [-30, 120]
        ],
        [-30, 120]
      );
      expect(shift()).toBe(0);
      await shows(count(), has('Step 1 of 4'));
    });

    it('shows a heading as the title of its section and never counts it', async () => {
      open(
        recipe([heading(1, 'The dal'), step(2, 'Boil.'), heading(3, 'The tadka'), step(4, 'Fry.')])
      );
      await shows(count(), has('Step 1 of 2'));
      await expect.element(page.getByRole('heading', { name: 'The dal' })).toBeVisible();
      await next().click();
      await shows(count(), has('Step 2 of 2'));
      await expect.element(page.getByRole('heading', { name: 'The tadka' })).toBeVisible();
      expect(page.getByRole('heading', { name: 'The dal' }).elements()).toHaveLength(0);
    });

    it('does not break on a recipe with two method sections: every step, in order, with its heading', async () => {
      open(
        recipe([
          heading(1, 'Method 1: stove'),
          step(2, 'Simmer.'),
          step(3, 'Serve hot.'),
          heading(4, 'Method 2: pressure cooker'),
          step(5, 'Cook for 3 whistles.'),
          step(6, 'Serve warm.')
        ])
      );
      const seen: string[] = [];
      for (let i = 0; i < 4; i++) {
        const section = document.querySelector('h2.section')?.textContent;
        seen.push(`${section}: ${text().element().textContent}`);
        if (i < 3) await next().click();
      }
      expect(seen).toEqual([
        'Method 1: stove: Simmer.',
        'Method 1: stove: Serve hot.',
        'Method 2: pressure cooker: Cook for 3 whistles.',
        'Method 2: pressure cooker: Serve warm.'
      ]);
      await shows(count(), has('Step 4 of 4'));
    });

    it('says so for a recipe with no steps, and still lets you leave and open the ingredients', async () => {
      open(recipe([heading(1, 'Only a heading')]));
      await shows(count(), has('No steps'));
      await shows(text(), has('This recipe has no steps yet.'));
      await expect.element(page.getByRole('button', { name: 'Show ingredients' })).toBeVisible();
      expect(
        page.getByRole('button', { name: /Not cooked yet|Close|Not now/ }).elements()
      ).toHaveLength(0);
      await expect.element(page.getByRole('button', { name: 'Cooked it' })).toBeVisible();
      expect(next().elements()).toHaveLength(0);
    });

    it('shows the last-step buttons at once for a one-step recipe', async () => {
      open(recipe([step(1, 'Just stir.')]));
      await shows(count(), has('Step 1 of 1'));
      await expect.element(page.getByRole('button', { name: 'Cooked it' })).toBeVisible();
      expect(next().elements()).toHaveLength(0);
    });

    it('keeps a very long step whole, inside the screen, and scrolls it', async () => {
      const long = 'Stir the pot slowly and keep stirring. '.repeat(120).trim();
      open(recipe([step(1, long), step(2, 'Done.')]));
      await expect.element(text()).toHaveTextContent(long);
      const body = document.querySelector('.body') as HTMLElement;
      expect(body.scrollHeight).toBeGreaterThan(body.clientHeight);
      expect(body.scrollWidth).toBeLessThanOrEqual(body.clientWidth);
      // Next and Back are still on the screen.
      const rect = next().element().getBoundingClientRect();
      expect(rect.bottom).toBeLessThanOrEqual(window.innerHeight);
    });
  });

  describe('the last step', () => {
    it('ends with Back and Cooked it (into the review) and nothing else (F155, F156)', async () => {
      open(recipe(FOUR));
      await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}');
      expect(next().elements()).toHaveLength(0);
      await page.getByRole('button', { name: 'Cooked it' }).click();
      expect(oncooked).toHaveBeenCalledTimes(1);
      expect(onexit).not.toHaveBeenCalled();
      expect(page.getByRole('button', { name: 'Not now' }).elements()).toHaveLength(0);
      expect(page.getByRole('button', { name: /Not cooked yet|Close/ }).elements()).toHaveLength(0);
      expect(document.querySelectorAll('footer button')).toHaveLength(2);
      await page.getByRole('button', { name: 'Leave Cook mode' }).click();
      expect(onexit).toHaveBeenCalledTimes(1);
    });

    it('keeps the place of Cooked it, but shows nothing, until the plan has loaded (F158)', async () => {
      open(recipe(FOUR), { settling: true, cooked: false });
      await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}');
      expect(page.getByRole('button', { name: 'Cooked it' }).elements()).toHaveLength(0);
      const waiting = document.querySelector('footer .waiting') as HTMLElement;
      expect(getComputedStyle(waiting).visibility).toBe('hidden');
      expect(waiting.getAttribute('aria-hidden')).toBe('true');
      expect(back().elements()).toHaveLength(1);
    });

    it('has ← Back on the last step too (F138)', async () => {
      open(recipe(FOUR));
      await userEvent.keyboard('{ArrowRight}{ArrowRight}{ArrowRight}');
      expect(back().elements()).toHaveLength(1);
      await expect.element(back()).toBeEnabled();
      await back().click();
      await expect.element(count()).toHaveTextContent('Step 3 of 4');
    });

    it('Back is there but off on a one-step recipe (F138)', async () => {
      open(recipe([step(1, 'Stir.')]), { cooked: false });
      await expect.element(back()).toBeDisabled();
    });

    it('the finished part of the progress bar is 5 px tall (F126)', async () => {
      open(recipe(FOUR));
      await userEvent.keyboard('{ArrowRight}');
      const spans = document.querySelectorAll<HTMLElement>('.progress span');
      for (const span of spans) {
        expect(span.getBoundingClientRect().height).toBe(5);
      }
    });

    it('has Back alone where nothing has been planned to cook (F155, F156)', async () => {
      open(recipe([step(1, 'Stir.')]), { cooked: false });
      expect(document.querySelectorAll('footer button')).toHaveLength(1);
      await expect.element(back()).toBeVisible();
      await expect.element(back()).toBeDisabled(); // a one-step recipe: nowhere to go back to
      expect(
        page.getByRole('button', { name: /Close|Not now|Not cooked yet|Cooked it/ }).elements()
      ).toHaveLength(0);
    });
  });

  describe('Show ingredients', () => {
    it('slides up the whole list on every step, headings and all, and closes with Done', async () => {
      open(recipe(FOUR));
      await next().click();
      await page.getByRole('button', { name: 'Show ingredients' }).click();
      const sheet = page.getByRole('dialog', { name: 'All ingredients' });
      await expect.element(sheet).toBeVisible();
      await shows(sheet, has('For the dal'));
      await shows(sheet, /30\sg/);
      await shows(sheet, has('tamarind'));
      await shows(sheet, has('15'));
      // The arrow keys do not turn the page behind the sheet.
      await userEvent.keyboard('{ArrowRight}');
      await shows(count(), has('Step 2 of 4'));
      await page.getByRole('button', { name: 'Done' }).click();
      await vi.waitFor(() => expect(document.querySelector('dialog[open]')).toBeNull());
    });
  });

  describe('timers', () => {
    it('starts one from the step’s words on a tap, counts down on screen, and ends with the chime', async () => {
      vi.useFakeTimers({ toFake: ['Date', 'setInterval', 'clearInterval'] });
      const { playChime } = await import('#lib/chime.js');
      open(recipe(FOUR));
      await next().click();
      const card = page.getByTestId('timer');
      const said = () => card.element().textContent ?? '';
      expect(said()).toContain('10 minutes');
      expect(said()).toContain('10:00');
      await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
      await vi.advanceTimersByTimeAsync(65_000);
      flushSync();
      expect(said()).toContain('08:55');
      expect(playChime).not.toHaveBeenCalled();
      // The rest of the ten minutes passes as it does on a phone that slept: the clock jumps and
      // the next look at it (one tick) finds the timer over. Stepping 2,160 more ticks one by
      // one took about ten real seconds, and over fifteen on a busy machine.
      vi.setSystemTime(Date.now() + 540_000);
      await vi.advanceTimersByTimeAsync(TICK_MS);
      flushSync();
      expect(said()).toContain('Time’s up');
      expect(playChime).toHaveBeenCalledTimes(1);
      const spoken = [...document.querySelectorAll('[role="status"]')].map((el) => el.textContent);
      expect(spoken.join(' ')).toContain('Timer finished: 10 minutes');
      await page.getByRole('button', { name: 'Done with the timer for 10 minutes' }).click();
      flushSync();
      expect(said()).toContain('10:00');
    });

    it('says there is no alarm when the phone is locked or the app is in the background', async () => {
      open(recipe(FOUR));
      expect(document.body.textContent).not.toContain('No alarm');
      await next().click();
      await expect
        .element(
          page.getByText('No alarm if the phone is locked or Mealwright is in the background.')
        )
        .toBeVisible();
    });

    it('keeps a running timer in view on the other steps', async () => {
      open(recipe(FOUR));
      await next().click();
      await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
      await next().click();
      await shows(count(), has('Step 3 of 4'));
      const link = page.getByRole('button', { name: /Step 2 ·/ });
      await expect.element(link).toBeVisible();
      await link.click();
      await shows(count(), has('Step 2 of 4'));
    });
  });

  describe('leaving', () => {
    it('leaves at once with no timer running', async () => {
      open(recipe(FOUR));
      await page.getByRole('button', { name: 'Leave Cook mode' }).click();
      expect(onexit).toHaveBeenCalledTimes(1);
    });

    it('asks "Stop the timer and leave?" with a timer running: Stay keeps it, Leave stops it', async () => {
      open(recipe(FOUR));
      await next().click();
      await page.getByRole('button', { name: 'Start timer for 10 minutes' }).click();
      await page.getByRole('button', { name: 'Leave Cook mode' }).click();
      const ask = page.getByRole('dialog', { name: 'Stop the timer and leave?' });
      await expect.element(ask).toBeVisible();
      expect(onexit).not.toHaveBeenCalled();
      await page.getByRole('button', { name: 'Stay' }).click();
      expect(onexit).not.toHaveBeenCalled();
      expect(timers.running).toBe(true);
      await page.getByRole('button', { name: 'Leave Cook mode' }).click();
      await page.getByRole('button', { name: 'Leave', exact: true }).click();
      expect(onexit).toHaveBeenCalledTimes(1);
      expect(timers.running).toBe(false);
    });

    it('asks the same before the cross on the last step, and when the page leaves by another way', async () => {
      const cook = open(recipe([step(1, 'Simmer for 5 minutes.')]));
      await page.getByRole('button', { name: 'Start timer for 5 minutes' }).click();
      await page.getByRole('button', { name: 'Leave Cook mode' }).click();
      await expect
        .element(page.getByRole('dialog', { name: 'Stop the timer and leave?' }))
        .toBeVisible();
      await page.getByRole('button', { name: 'Stay' }).click();
      const go = vi.fn();
      cook.leaveOr(go);
      flushSync();
      await page.getByRole('button', { name: 'Leave', exact: true }).click();
      expect(go).toHaveBeenCalledTimes(1);
      expect(onexit).not.toHaveBeenCalled();
    });

    it('leaves with Escape, asking first when a timer runs', async () => {
      open(recipe([step(1, 'Simmer for 5 minutes.')]));
      await userEvent.keyboard('{Escape}');
      expect(onexit).toHaveBeenCalledTimes(1);
    });
  });

  describe('ingredients for each step (Experimental)', () => {
    it('is off by default: nothing is shown under the step, and the switch says Experimental', async () => {
      open(recipe(FOUR));
      await next().click();
      expect(page.getByTestId('per-step').elements()).toHaveLength(0);
      const sw = page.getByRole('switch', { name: /Ingredients for each step/ });
      await expect.element(sw).toHaveAttribute('aria-checked', 'false');
      await expect.element(page.getByText('Experimental', { exact: true })).toBeVisible();
      await sw.click();
      expect(onperstep).toHaveBeenCalledWith(true);
    });

    it('shows the guessed ingredients in the box, under a divider, once on', async () => {
      open(recipe(FOUR), { perStep: true });
      await next().click();
      const box = page.getByTestId('per-step');
      await shows(box, has('tamarind'));
      await shows(box, /3\sonions/);
      await shows(
        box,
        has('Guessed from the step, so it may be wrong. Fix it when you edit the recipe.')
      );
      // The pink flask is on the badge: its colour is the Experimental one.
      const badge = document.querySelector('.perstep .badge')!;
      const probe = document.body.appendChild(document.createElement('span'));
      probe.style.color = 'var(--color-experimental-text)';
      expect(getComputedStyle(badge).color).toBe(getComputedStyle(probe).color);
      // Another step guesses other ingredients; none found says so.
      await next().click();
      await shows(box, has('shallots'));
      expect(box.element().textContent).not.toContain('tamarind');
      await next().click();
      await shows(box, has('No ingredient guessed for this step.'));
    });

    it('lays the box out as the 0.8 mockup does (F148)', async () => {
      open(recipe(FOUR), { perStep: true });
      const rect = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
      const style = getComputedStyle(document.querySelector('.perstep')!);
      // The mockup's sizes: label 15 px, 12 px between the head and the guesses and in the head.
      expect(getComputedStyle(document.querySelector('.perstep .label')!).fontSize).toBe('15px');
      expect(style.rowGap).toBe('12px');
      expect(getComputedStyle(document.querySelector('.perstep .head')!).columnGap).toBe('12px');
      // 16 px padding and a thin border.
      expect(style.paddingTop).toBe('16px');
      expect(style.paddingLeft).toBe('16px');
      expect(style.borderTopWidth).toBe('1px');
      // The label on its own line, the badge under it with 8 px between, both on the left.
      const label = rect('.perstep .label');
      const badge = rect('.perstep .badge');
      expect(badge.top - label.bottom).toBe(8);
      expect(badge.left).toBe(label.left);
      // The switch 52 × 32, centred against the two lines.
      const sw = rect('.perstep [role="switch"]');
      expect([sw.width, sw.height]).toEqual([52, 32]);
      const middle = (label.top + badge.bottom) / 2;
      expect(Math.abs(sw.top + sw.height / 2 - middle)).toBeLessThanOrEqual(1);
      // The guesses sit under a thin divider; the note has line height 1.45.
      expect(getComputedStyle(document.querySelector('.perstep .guess')!).borderTopWidth).toBe(
        '1px'
      );
      const note = getComputedStyle(document.querySelector('.perstep .guess .note:last-child')!);
      expect(parseFloat(note.lineHeight) / parseFloat(note.fontSize)).toBeCloseTo(1.45, 2);
      // The label does not touch the top of its box.
      expect(label.top - rect('.perstep').top).toBeGreaterThanOrEqual(16);
    });

    it('uses the links the recipe holds for a step instead of guessing', async () => {
      const held = recipe([
        { ...step(1, 'Fry everything.'), lines: [{ line_id: 4, line: 3, kind: 'by_hand' }] }
      ]);
      open(held, { perStep: true });
      await shows(page.getByTestId('per-step'), has('shallots'));
    });
  });

  describe('Keep screen awake', () => {
    function fakeLock() {
      const released: number[] = [];
      let n = 0;
      Object.defineProperty(navigator, 'wakeLock', {
        configurable: true,
        value: {
          request: async () => {
            const id = ++n;
            return { release: async () => void released.push(id), addEventListener: () => {} };
          }
        }
      });
      return released;
    }

    it('turns on with Cook mode, can be switched off, and lets go on leaving', async () => {
      const released = fakeLock();
      awake = new ScreenAwake();
      open(recipe(FOUR));
      const sw = page.getByRole('switch', { name: 'Keep screen awake' });
      await expect.element(sw).toHaveAttribute('aria-checked', 'true');
      await expect.element(page.getByText('Awake', { exact: true })).toBeVisible();
      await sw.click();
      await expect.element(sw).toHaveAttribute('aria-checked', 'false');
      expect(released).toEqual([1]);
      await sw.click();
      await expect.element(sw).toHaveAttribute('aria-checked', 'true');
      for (const component of mounted.splice(0)) unmount(component);
      await vi.waitFor(() => expect(released).toEqual([1, 2]));
    });

    it('says “Couldn’t keep the screen awake.” on its own amber line under the progress bar, not in the box (F148)', async () => {
      Object.defineProperty(navigator, 'wakeLock', {
        configurable: true,
        value: { request: async () => Promise.reject(new Error('no')) }
      });
      awake = new ScreenAwake();
      open(recipe(FOUR), { perStep: true });
      const line = page.getByTestId('cook-asleep');
      await expect.element(line).toBeVisible();
      await expect.element(line).toHaveTextContent('Couldn’t keep the screen awake.');
      expect(line.element().closest('.perstep')).toBeNull();
      expect(line.element().querySelector('svg')).not.toBeNull(); // the moon
      const progress = document.querySelector('.progress')!.getBoundingClientRect();
      const amber = line.element().getBoundingClientRect();
      expect(amber.top).toBeGreaterThanOrEqual(progress.bottom);
      const style = getComputedStyle(line.element());
      expect([style.paddingTop, style.paddingLeft]).toEqual(['10px', '12px']);
      expect(style.fontSize).toBe('14px');
      // Nothing in the Awake pill while it is refused.
      expect(document.querySelector('.awake:not(.spacer)')).toBeNull();
    });

    it('is greyed with the words when the browser can’t keep the screen on', async () => {
      Object.defineProperty(navigator, 'wakeLock', { configurable: true, value: undefined });
      awake = new ScreenAwake();
      open(recipe(FOUR));
      const sw = page.getByRole('switch', { name: 'Keep screen awake' });
      await expect.element(sw).toBeDisabled();
      await expect.element(sw).toHaveAttribute('aria-checked', 'false');
      await expect.element(page.getByText('This browser can’t keep the screen on')).toBeVisible();
      expect(sw.element().getAttribute('aria-describedby')).toBeTruthy();
    });
  });

  it('has no button under 44 px, the sheet’s Done included', async () => {
    open(recipe(FOUR));
    await page.getByRole('button', { name: 'Show ingredients' }).click();
    for (const el of document.querySelectorAll('button:not([role="switch"])')) {
      const box = el.getBoundingClientRect();
      if (box.width === 0) continue;
      expect(
        box.height,
        `${el.textContent?.trim() || el.getAttribute('aria-label')}`
      ).toBeGreaterThanOrEqual(44);
    }
  });

  it('sets the page title and has the recipe’s name as its one heading 1', async () => {
    open(recipe(FOUR));
    await expect.element(page.getByRole('heading', { name: 'Sambar', level: 1 })).toBeVisible();
    expect(page.getByRole('heading', { level: 1 }).elements()).toHaveLength(1);
  });
});
