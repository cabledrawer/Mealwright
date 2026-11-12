import { describe, expect, it } from 'vitest';
import { starterPacks } from './starterPacks.svelte';

// The dialog's code is fetched the first time it's opened, and then kept (size limit): the
// app layout shows it once `wanted` is true, which closing never undoes.
describe('the starter pack dialog', () => {
  it('isn’t wanted until it’s first opened, and stays wanted once closed', () => {
    expect(starterPacks.wanted).toBe(false);
    expect(starterPacks.open).toBe(false);
    starterPacks.show();
    expect(starterPacks.open).toBe(true);
    expect(starterPacks.wanted).toBe(true);
    starterPacks.close();
    expect(starterPacks.open).toBe(false);
    expect(starterPacks.wanted).toBe(true);
  });
});
