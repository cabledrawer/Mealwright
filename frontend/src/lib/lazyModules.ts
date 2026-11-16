// The code that is fetched the first time it is used (the size limit), in one place, so a test
// can swap a loader for one that fails once. Use it with `fetchCode(loaders.x)` (lazyCode.svelte.ts):
// a failed fetch gives the toast "Couldn’t open that. Try again.", ends the ask as if
// cancelled with nothing changed, and the next try fetches again.

export const loaders = {
  methodAsk: () => import('./methodAsk.svelte'),
  startAsk: () => import('./startAsk.svelte'),
  startNow: () => import('./startNow'),
  startWords: () => import('./startWords'),
  clientPlan: () => import('./client/plan'),
  optionalQuestion: () => import('./optionalQuestion')
};
