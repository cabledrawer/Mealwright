// The Auto · Light · Dark choice (UX principle 13).
//
// static/theme.js applies the saved choice before the page is drawn; this module
// keeps it up to date while the app runs. Both use the same storage key and rules.
// The choice is saved per person (spec: "Choice saved per user"): once signed in,
// the account's choice wins, and changes go back to the account. This device keeps a
// copy, so the right theme shows before the app has started.

import type { ThemeChoice } from './api';

export type { ThemeChoice };

export const THEME_CHOICES: readonly ThemeChoice[] = ['auto', 'light', 'dark'];

export const THEME_LABELS: Record<ThemeChoice, string> = {
  auto: 'Auto',
  light: 'Light',
  dark: 'Dark'
};

export const THEME_HINTS: Record<ThemeChoice, string> = {
  auto: 'Follow device',
  light: 'Light',
  dark: 'Dark'
};

export const THEME_STORAGE_KEY = 'mealwright.theme';

/** The page's ground colour (--color-ground), for the browser's bar. Same as static/theme.js. */
export const THEME_COLOR = { light: '#f5f6f4', dark: '#111614' } as const;

const DARK_QUERY = '(prefers-color-scheme: dark)';

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === 'auto' || value === 'light' || value === 'dark';
}

/** The next choice for the single cycling button (collapsed sidebar). */
export function nextTheme(choice: ThemeChoice): ThemeChoice {
  const i = THEME_CHOICES.indexOf(choice);
  return THEME_CHOICES[(i + 1) % THEME_CHOICES.length] ?? 'auto';
}

function readSaved(): ThemeChoice {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    return isThemeChoice(saved) ? saved : 'auto';
  } catch {
    return 'auto';
  }
}

function save(choice: ThemeChoice): void {
  try {
    if (choice === 'auto') localStorage.removeItem(THEME_STORAGE_KEY);
    else localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Storage blocked: the choice still applies until the page is closed.
  }
}

class Theme {
  choice = $state<ThemeChoice>(readSaved());
  deviceDark = $state(false);
  /** What is actually showing. */
  resolved = $derived<'light' | 'dark'>(
    this.choice === 'auto' ? (this.deviceDark ? 'dark' : 'light') : this.choice
  );

  #media: MediaQueryList | null = null;
  #saveToAccount: ((choice: ThemeChoice) => void) | null = null;

  /** Start following the device setting. Returns a function that stops it. */
  start(): () => void {
    this.choice = readSaved();
    this.#media = window.matchMedia(DARK_QUERY);
    this.deviceDark = this.#media.matches;
    const onChange = (event: MediaQueryListEvent) => {
      this.deviceDark = event.matches;
      this.#apply();
    };
    this.#media.addEventListener('change', onChange);
    this.#apply();
    return () => this.#media?.removeEventListener('change', onChange);
  }

  /** The person picked a theme. */
  set(choice: ThemeChoice): void {
    this.choice = choice;
    save(choice);
    this.#apply();
    this.#saveToAccount?.(choice);
  }

  /** The account's choice, on signing in: it wins over this device's copy. */
  adopt(choice: ThemeChoice): void {
    this.choice = choice;
    save(choice);
    this.#apply();
  }

  /** While someone is signed in, changes are also saved to their account. */
  saveChangesWith(saver: ((choice: ThemeChoice) => void) | null): void {
    this.#saveToAccount = saver;
  }

  cycle(): void {
    this.set(nextTheme(this.choice));
  }

  #apply(): void {
    const root = document.documentElement;
    root.setAttribute('data-theme-choice', this.choice);
    root.setAttribute('data-theme', this.resolved);
    // The browser's bar follows the page (static/theme.js does the same before first paint).
    document
      .querySelector('meta[name="theme-color"]')
      ?.setAttribute('content', this.resolved === 'dark' ? THEME_COLOR.dark : THEME_COLOR.light);
  }
}

export const theme = new Theme();
