import { flushSync, mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import '#lib/styles/tokens.css';
import StepperFixture from '#lib/testing/StepperFixture.svelte';

let component: ReturnType<typeof mount> | null = null;

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
});

function render(props: Record<string, unknown> = {}) {
  component = mount(StepperFixture, { target: document.body, props });
  flushSync();
}

const shown = () => document.querySelector('.now')?.textContent?.trim();

describe('Stepper', () => {
  it('is a labelled group with Fewer and More buttons named for what is counted', async () => {
    render();
    const group = page.getByRole('group', { name: 'Portions cooked' });
    await expect.element(group).toBeVisible();
    await expect.element(group.getByRole('button', { name: 'Fewer portions' })).toBeVisible();
    await expect.element(group.getByRole('button', { name: 'More portions' })).toBeVisible();
  });

  it('steps and stops at its ends', async () => {
    render({ start: 2, min: 1, max: 3 });
    const group = page.getByRole('group', { name: 'Portions cooked' });
    await group.getByRole('button', { name: 'More portions' }).click();
    await expect.poll(() => shown()).toBe('3');
    await expect.element(group.getByRole('button', { name: 'More portions' })).toBeDisabled();
    await group.getByRole('button', { name: 'Fewer portions' }).click();
    await expect.poll(() => shown()).toBe('2');
    await group.getByRole('button', { name: 'Fewer portions' }).click();
    await expect.poll(() => shown()).toBe('1');
    await expect.element(group.getByRole('button', { name: 'Fewer portions' })).toBeDisabled();
  });
});
