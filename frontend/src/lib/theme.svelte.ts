// The Auto · Light · Dark choice (UX principle 13).
//
// static/theme.js applies the saved choice before the page is drawn; this module
// keeps it up to date while the app runs. Both use the same storage key and rules.
// For now the choice is saved on this device. Once sign-in is in, it is also saved
// to the person's account (PUT /api/v1/me/preferences), as the spec asks.

export type ThemeChoice = 'auto' | 'light' | 'dark';

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

  set(choice: ThemeChoice): void {
    this.choice = choice;
    save(choice);
    this.#apply();
  }

  cycle(): void {
    this.set(nextTheme(this.choice));
  }

  #apply(): void {
    const root = document.documentElement;
    root.setAttribute('data-theme-choice', this.choice);
    root.setAttribute('data-theme', this.resolved);
  }
}

export const theme = new Theme();
