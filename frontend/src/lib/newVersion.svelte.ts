// "New version ready" (spec "App updates"; plan row X1): a new version of the app has been
// downloaded and its service worker is waiting. Our worker never calls skipWaiting() (and claims
// only on the very first install), so an update takes over only once every tab and window of
// the app is closed. This only notices that it's waiting,
// so About can say so; it never reloads a page or asks the worker to take over.

class NewVersion {
  /** A new service worker is installed and waiting for every tab to close. */
  ready = $state(false);
  #watching = false;

  /** Start watching (once). Safe where there is no service worker (a test, http://). The
   *  promise is for tests: it settles once the watching has started. */
  watch(container: ServiceWorkerContainer | undefined = navigator.serviceWorker): Promise<void> {
    if (this.#watching || !container) return Promise.resolve();
    this.#watching = true;
    return container.getRegistration().then(
      (registration) => {
        if (registration) this.#follow(registration);
      },
      () => {}
    );
  }

  #follow(registration: ServiceWorkerRegistration): void {
    // Only an update counts: the very first worker, with no page controlled yet, is not "new".
    const isUpdate = () => registration.active !== null;
    if (registration.waiting && isUpdate()) this.ready = true;
    registration.addEventListener('updatefound', () => {
      const incoming = registration.installing;
      if (!incoming) return;
      incoming.addEventListener('statechange', () => {
        if (incoming.state === 'installed' && registration.waiting === incoming && isUpdate()) {
          this.ready = true;
        }
      });
    });
  }

  /** For tests. */
  reset(): void {
    this.ready = false;
    this.#watching = false;
  }
}

export const newVersion = new NewVersion();
