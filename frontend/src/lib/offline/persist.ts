// Ask the browser to keep the app's stored data (sync protocol 11.7), once the app is
// installed. The offline copy and queue (PR 6) are then not cleared when the device is short
// of space.
//
// Only where it doesn't show a question to the person: installed (standalone) apps in
// Chromium and Safari decide quietly. Firefox would ask, so it is left out. Tried once per
// device.

export interface PersistEnv {
  standalone: boolean;
  firefox: boolean;
  storage: Pick<StorageManager, 'persist' | 'persisted'> | undefined;
  asked: () => boolean;
  remember: () => void;
}

export async function askToKeepData(env: PersistEnv): Promise<boolean> {
  if (!env.standalone || env.firefox || !env.storage || env.asked()) return false;
  env.remember();
  try {
    if (await env.storage.persisted()) return true;
    return await env.storage.persist();
  } catch {
    return false;
  }
}

const KEY = 'mealwright.keep-data-asked';

/** The real thing, for the app shell. */
export function askToKeepDataHere(): Promise<boolean> {
  return askToKeepData({
    standalone:
      matchMedia('(display-mode: standalone)').matches ||
      (navigator as Navigator & { standalone?: boolean }).standalone === true,
    firefox: navigator.userAgent.includes('Firefox/'),
    storage: navigator.storage,
    asked: () => {
      try {
        return localStorage.getItem(KEY) === '1';
      } catch {
        return false;
      }
    },
    remember: () => {
      try {
        localStorage.setItem(KEY, '1');
      } catch {
        // Storage blocked: it may be asked again next time, which is harmless.
      }
    }
  });
}
