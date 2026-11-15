import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Component } from 'svelte';
import { newIngredient } from './newIngredient.svelte';
import { toasts } from './toast.svelte';

// The dialog's code is fetched when asked or warmed (size limit). A failed fetch is forgotten:
// the next ask fetches again, and an ask waiting at the moment of failure is answered, not left
// hanging.
const fake = {} as Component;

describe('the new-ingredient dialog’s code', () => {
  beforeEach(() => {
    newIngredient.code = null;
    toasts.dismiss();
  });

  it('a failed warm-up is forgotten quietly, and the next ask fetches again and opens', async () => {
    const loader = vi
      .fn<() => Promise<{ default: Component }>>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ default: fake });
    newIngredient.loader = loader;
    newIngredient.warm();
    expect(newIngredient.wanted).toBe(true);
    await vi.waitFor(() => expect(newIngredient.wanted).toBe(false));
    expect(toasts.current).toBeNull(); // nobody asked: no toast

    const asked = newIngredient.ask('Ghee');
    expect(loader).toHaveBeenCalledTimes(2);
    expect(newIngredient.current?.name).toBe('Ghee');
    expect(await newIngredient.code).toBe(fake);
    newIngredient.cancel();
    expect(await asked).toBeNull();
  });

  it('an ask waiting when the fetch fails is answered with null and a toast, and the next ask tries again', async () => {
    const loader = vi
      .fn<() => Promise<{ default: Component }>>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({ default: fake });
    newIngredient.loader = loader;
    const first = newIngredient.choose('Hing');
    expect(await first).toBeNull(); // not left hanging
    expect(newIngredient.current).toBeNull();
    expect(newIngredient.wanted).toBe(false);
    expect(toasts.current?.message).toBe('Couldn’t open that. Try again.');

    const second = newIngredient.choose('Hing');
    expect(loader).toHaveBeenCalledTimes(2);
    expect(await newIngredient.code).toBe(fake);
    newIngredient.cancel();
    expect(await second).toBeNull();
  });
});
