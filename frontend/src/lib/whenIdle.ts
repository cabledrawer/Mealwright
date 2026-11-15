// Run `work` a moment after the page has loaded (0.9.5 speed work; proposed, for cabledrawer). Used to
// fetch a dialog's code after the first page, so the first page stays small but the dialog still
// opens where the network layer blocks a first-use fetch (offline, in Playwright's WebKit).
// A plain timer, not requestIdleCallback, which Safari does not have. `work` runs at most once;
// the returned function cancels it.
export interface IdleHost {
  readyState: string;
  addEventListener(type: 'load', fn: () => void, options?: { once: boolean }): void;
  removeEventListener(type: 'load', fn: () => void): void;
  setTimeout(fn: () => void, ms: number): number;
  clearTimeout(id: number): void;
}

/** How long after the page has loaded `work` runs. */
export const AFTER_LOAD_MS = 1000;

/** The page: `readyState` is the document's, the rest is the window's. */
const pageHost = (): IdleHost => ({
  get readyState() {
    return document.readyState;
  },
  addEventListener: (type, fn, options) => window.addEventListener(type, fn, options),
  removeEventListener: (type, fn) => window.removeEventListener(type, fn),
  setTimeout: (fn, ms) => window.setTimeout(fn, ms),
  clearTimeout: (id) => window.clearTimeout(id)
});

export function whenIdle(work: () => void, host: IdleHost = pageHost()): () => void {
  let cancel: () => void = () => {};
  const go = () => {
    const id = host.setTimeout(work, AFTER_LOAD_MS);
    cancel = () => host.clearTimeout(id);
  };
  if (host.readyState === 'complete') go();
  else {
    host.addEventListener('load', go, { once: true });
    cancel = () => host.removeEventListener('load', go);
  }
  return () => cancel();
}
