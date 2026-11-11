// "New version ready" (X1): noticing a waiting service worker, without ever making it take over.

import { afterEach, describe, expect, it, vi } from 'vitest';
import { newVersion } from './newVersion.svelte';

class FakeWorker extends EventTarget {
  state: ServiceWorkerState = 'installing';
  postMessage = vi.fn();
  install(registration: FakeRegistration) {
    this.state = 'installed';
    registration.installing = null;
    registration.waiting = this as unknown as ServiceWorker;
    this.dispatchEvent(new Event('statechange'));
  }
}

class FakeRegistration extends EventTarget {
  active: ServiceWorker | null = null;
  waiting: ServiceWorker | null = null;
  installing: ServiceWorker | null = null;
  update = vi.fn();
  unregister = vi.fn();
}

function container(registration: FakeRegistration | undefined): ServiceWorkerContainer {
  return { getRegistration: async () => registration } as unknown as ServiceWorkerContainer;
}

afterEach(() => newVersion.reset());

describe('new version ready', () => {
  it('is ready when an update is already waiting', async () => {
    const registration = new FakeRegistration();
    registration.active = {} as ServiceWorker;
    registration.waiting = {} as ServiceWorker;
    newVersion.watch(container(registration));
    await vi.waitFor(() => expect(newVersion.ready).toBe(true));
  });

  it('becomes ready when an update finishes installing, and never asks it to take over', async () => {
    const registration = new FakeRegistration();
    registration.active = {} as ServiceWorker;
    await newVersion.watch(container(registration));
    expect(newVersion.ready).toBe(false);
    const incoming = new FakeWorker();
    registration.installing = incoming as unknown as ServiceWorker;
    registration.dispatchEvent(new Event('updatefound'));
    incoming.install(registration);
    expect(newVersion.ready).toBe(true);
    expect(incoming.postMessage).not.toHaveBeenCalled(); // no "skip waiting"
    expect(registration.update).not.toHaveBeenCalled();
  });

  it('the very first install is not a new version', async () => {
    const registration = new FakeRegistration();
    await newVersion.watch(container(registration));
    const first = new FakeWorker();
    registration.installing = first as unknown as ServiceWorker;
    registration.dispatchEvent(new Event('updatefound'));
    first.install(registration);
    expect(newVersion.ready).toBe(false);
  });

  it('does nothing without a service worker', async () => {
    await newVersion.watch(undefined);
    await newVersion.watch(container(undefined));
    expect(newVersion.ready).toBe(false);
  });
});
