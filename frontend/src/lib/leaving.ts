// Is this page being left? (T1, cabledrawer 11 Nov.) From the moment the browser starts to leave a
// page (a reload, a typed address, closing the tab: `beforeunload`) until the next page arrives,
// the old one is still running, and a request it makes then is not a real one:
//  - WebKit (Safari) refuses a request started then, and logs "Fetch API cannot load … due to
//    access control checks." as a script error;
//  - the requests still on their way are cut off ("Load failed"), which is not the server being
//    out of reach, so the page being left must not say "Can’t reach your Mealwright server".
// So while the page is being left nothing new is sent, and a request cut off by the leave is
// neither shown nor logged as a failure: it waits (api.ts). If the page goes, it never answers,
// which is nothing to anyone. If the page stays after all (the leave was called off, or the
// browser brings the page back from its back-forward cache), the waiting requests go on.
//
// A leave the page itself has asked the browser to confirm (Cook mode with a timer running) is
// not counted until the browser hides the page (`pagehide`). Any key or tap on the page means
// it is staying.

let leaving = false;
let stay: (() => void) | null = null;
let stayed: Promise<void> = Promise.resolve();

/** The page is being left: hold requests rather than send them or report them as failures. */
export function isLeaving(): boolean {
  return leaving;
}

/** Resolves once the page turns out to be staying; at once if it isn't being left. Never
 *  resolves if the page goes. */
export function whenStaying(): Promise<void> {
  return stayed;
}

function startLeaving(): void {
  if (leaving) return;
  leaving = true;
  stayed = new Promise<void>((resolve) => (stay = resolve));
}

function staying(): void {
  if (!leaving) return;
  leaving = false;
  const resolve = stay;
  stay = null;
  stayed = Promise.resolve();
  resolve?.();
}

/**
 * Watch for the page being left (the root layout calls it once). Also keeps a page's code or
 * styles cut off by the leave from being reported as a script error. Returns a function that
 * stops watching.
 */
export function watchLeaving(target: Window = window): () => void {
  const onBeforeUnload = (event: BeforeUnloadEvent) => {
    // Asked to confirm (the browser's "Leave page?"): the person may stay.
    if (event.defaultPrevented) return;
    startLeaving();
  };
  // A page's code or styles cut off by the leave (Vite's "Unable to preload CSS"): Vite throws
  // the error on, and nothing is waiting for it any more. Not prevented here, which would make
  // the import answer `undefined` instead; its unhandled rejection is let go below.
  const cut = new WeakSet<object>();
  const onPreloadError = (event: Event) => {
    const error = (event as Event & { payload?: unknown }).payload;
    if (leaving && error && typeof error === 'object') cut.add(error);
  };
  const onUnhandled = (event: PromiseRejectionEvent) => {
    const error: unknown = event.reason;
    if (leaving && error && typeof error === 'object' && cut.has(error)) event.preventDefault();
  };
  const listeners: [string, EventListener, AddEventListenerOptions?][] = [
    ['beforeunload', onBeforeUnload as EventListener],
    ['pagehide', startLeaving],
    ['pageshow', staying],
    ['pointerdown', staying, { capture: true, passive: true }],
    ['keydown', staying, { capture: true, passive: true }],
    ['vite:preloadError', onPreloadError],
    ['unhandledrejection', onUnhandled as EventListener]
  ];
  for (const [type, listener, options] of listeners)
    target.addEventListener(type, listener, options);
  return () => {
    for (const [type, listener, options] of listeners)
      target.removeEventListener(type, listener, options);
    staying();
  };
}
