// Run `work` once the page has loaded and the browser has nothing better to do (0.9.5 speed
// work; proposed, for cabledrawer). Used to fetch a dialog's code after the first page, so the first
// page stays small but the dialog still opens where the network layer blocks a first-use fetch
// (offline, in Playwright's WebKit). `work` runs at most once; the returned function cancels it.
export interface IdleHost {
  readyState: string;
  addEventListener(type: 'load', fn: () => void, options?: { once: boolean }): void;
  removeEventListener(type: 'load', fn: () => void): void;
  requestIdleCallback?: (fn: () => void, options?: { timeout: number }) => number;
  cancelIdleCallback?: (id: number) => void;
  setTimeout(fn: () => void, ms: number): number;
  clearTimeout(id: number): void;
}

/** After the browser has waited at most this long for an idle moment, `work` runs anyway. */
export const IDLE_TIMEOUT_MS = 4000;

export function whenIdle(
  work: () => void,
  host: IdleHost = window as unknown as IdleHost
): () => void {
  let cancelled = false;
  let handle: (() => void) | null = null;
  const go = () => {
    if (cancelled) return;
    if (host.requestIdleCallback) {
      const id = host.requestIdleCallback(work, { timeout: IDLE_TIMEOUT_MS });
      handle = () => host.cancelIdleCallback?.(id);
    } else {
      const id = host.setTimeout(work, 200);
      handle = () => host.clearTimeout(id);
    }
  };
  if (host.readyState === 'complete') go();
  else {
    host.addEventListener('load', go, { once: true });
    handle = () => host.removeEventListener('load', go);
  }
  return () => {
    cancelled = true;
    handle?.();
  };
}
