import { expect, test, type Page } from '@playwright/test';

// Calm motion (spec "Keeping the UI good", item 7): animations are small, and turn off
// when the device asks for reduced motion. Runs on the sign-in page (no saved session),
// which has a real switch whose knob slides.

/** The computed motion settings of the switch's knob and of a test element that asks for
 *  a slow transition, a long delay and an endless animation. */
async function motion(page: Page) {
  await page.goto('/sign-in');
  const knob = page.getByRole('switch').first().locator('span');
  await expect(knob).toBeVisible();
  return page.evaluate(() => {
    const knobEl = document.querySelector('[role="switch"] span') as HTMLElement;
    const probe = document.createElement('div');
    probe.style.cssText =
      'transition: opacity 5s 2s; animation: probe 5s 2s infinite; scroll-behavior: smooth';
    document.body.append(probe);
    const style = getComputedStyle(probe);
    const result = {
      knobTransition: getComputedStyle(knobEl).transitionDuration,
      transition: style.transitionDuration,
      transitionDelay: style.transitionDelay,
      animation: style.animationDuration,
      animationDelay: style.animationDelay,
      iterations: style.animationIterationCount,
      scroll: style.scrollBehavior
    };
    probe.remove();
    return result;
  });
}

test('with reduced motion, nothing slides, fades or loops', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  const result = await motion(await context.newPage());
  await context.close();
  // 0.01 ms: over at once, but "transitionend" and "animationend" still fire.
  expect(result).toEqual({
    knobTransition: '1e-05s',
    transition: '1e-05s',
    transitionDelay: '0s',
    animation: '1e-05s',
    animationDelay: '0s',
    iterations: '1',
    scroll: 'auto'
  });
});

test('without that request, the small animations are there', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'no-preference' });
  const result = await motion(await context.newPage());
  await context.close();
  expect(result.knobTransition).toBe('0.15s');
  expect(result.transition).toBe('5s');
  expect(result.iterations).toBe('infinite');
});
