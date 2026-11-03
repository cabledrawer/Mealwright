// How the Check screen looks on a phone (F141, cabledrawer 3 Nov): "Focus" (the whole list with the
// app's menu hidden; the default) or "One at a time" (each line that needs you, then every step).
// Chosen in Settings → Appearance and remembered on this device only, like the sidebar's
// collapsed state. A computer always shows the whole list, whatever this says.

export type CheckMode = 'focus' | 'one';

export const CHECK_MODE_STORAGE_KEY = 'mealwright.checkMode';

export const CHECK_MODES: readonly CheckMode[] = ['focus', 'one'];

export function isCheckMode(value: unknown): value is CheckMode {
  return value === 'focus' || value === 'one';
}

function readSaved(): CheckMode {
  try {
    const saved = localStorage.getItem(CHECK_MODE_STORAGE_KEY);
    return isCheckMode(saved) ? saved : 'focus';
  } catch {
    return 'focus';
  }
}

class CheckModeChoice {
  choice = $state<CheckMode>(readSaved());

  /** Read this device's saved choice again (a test, or another tab changed it). */
  reload(): void {
    this.choice = readSaved();
  }

  set(choice: CheckMode): void {
    this.choice = choice;
    try {
      if (choice === 'focus') localStorage.removeItem(CHECK_MODE_STORAGE_KEY);
      else localStorage.setItem(CHECK_MODE_STORAGE_KEY, choice);
    } catch {
      // Storage blocked: the choice still applies until the page is closed.
    }
  }
}

export const checkMode = new CheckModeChoice();
