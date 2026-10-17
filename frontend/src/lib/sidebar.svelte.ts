// Whether the desktop sidebar is collapsed to icons. Remembered on this device
// (spec: "Toggle on every page, remembered per device").

export const SIDEBAR_STORAGE_KEY = 'mealwright.sidebar';

function readSaved(): boolean {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'collapsed';
  } catch {
    return false;
  }
}

class Sidebar {
  collapsed = $state(readSaved());

  toggle(): void {
    this.set(!this.collapsed);
  }

  set(collapsed: boolean): void {
    this.collapsed = collapsed;
    try {
      if (collapsed) localStorage.setItem(SIDEBAR_STORAGE_KEY, 'collapsed');
      else localStorage.removeItem(SIDEBAR_STORAGE_KEY);
    } catch {
      // Storage blocked: it still applies until the page is closed.
    }
  }
}

export const sidebar = new Sidebar();
