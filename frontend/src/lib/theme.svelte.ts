// The Auto · Light · Dark choice (UX principle 13).
//
// static/theme.js applies the saved choice before the page is drawn; this module
// keeps it up to date while the app runs. Both use the same storage key and rules.
// The choice is saved per person (spec: "Choice saved per user"): once signed in,
// the account's choice shows, and changes go back to the account. This device keeps a
// copy, so the right theme shows before the app has started.
//
// The person's most recent pick always wins, online or offline (cabledrawer 9 Nov): a pick is
// kept on this device, under the person's id, as "pending" until the server has it, and is
// sent again when the connection is back. While it is pending no older answer from the server
// (on loading, after a reload) replaces it. Once the server has it, the server's value counts
// again. Kept in localStorage beside the choice itself, not in the offline queue: the theme
// isn't part of the sync protocol (it goes to PUT /me/preferences) and one value needs no queue.

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

/** A pick the server hasn't confirmed yet: `{"user": 2, "choice": "dark"}`. */
export const THEME_PENDING_KEY = 'mealwright.theme.pending';

type Pending = { user: number; choice: ThemeChoice };

/** Sends a pick to the account. True: done with (the server has it, or refused it for good).
 * False, or an error: keep it pending and send it again later. */
export type ThemeSaver = (choice: ThemeChoice) => Promise<boolean>;

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

function readPending(): Pending | null {
  try {
    const raw = localStorage.getItem(THEME_PENDING_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== 'object' || value === null) return null;
    const { user, choice } = value as Record<string, unknown>;
    return typeof user === 'number' && isThemeChoice(choice) ? { user, choice } : null;
  } catch {
    return null;
  }
}

function writePending(pending: Pending | null): void {
  try {
    if (pending) localStorage.setItem(THEME_PENDING_KEY, JSON.stringify(pending));
    else localStorage.removeItem(THEME_PENDING_KEY);
  } catch {
    // Storage blocked: the pick is sent now or not at all.
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
  #saveToAccount: ThemeSaver | null = null;
  #userId: number | null = null;
  #sending: Promise<void> | null = null;
  #picks = 0;

  /** How many times the person has picked a theme since the page loaded. */
  get picks(): number {
    return this.#picks;
  }

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
    this.#picks += 1;
    this.choice = choice;
    save(choice);
    this.#apply();
    if (this.#userId !== null) writePending({ user: this.#userId, choice });
    void this.flush();
  }

  /**
   * Send the pending pick, if it is this signed-in person's. At most one send at a time; a
   * newer pick made meanwhile is sent after it. Once the server has it, the pending mark is
   * cleared (only if no newer pick has replaced it), so the server's value counts again.
   */
  flush(): Promise<void> {
    // One already under way carries on with whatever is pending when it finishes a send.
    this.#sending ??= this.#send().finally(() => (this.#sending = null));
    return this.#sending;
  }

  async #send(): Promise<void> {
    for (;;) {
      const saver = this.#saveToAccount;
      const pending = readPending();
      if (!saver || this.#userId === null || !pending || pending.user !== this.#userId) return;
      let done: boolean;
      try {
        done = await saver(pending.choice);
      } catch {
        return;
      }
      if (!done) return;
      const now = readPending();
      if (now && now.user === pending.user && now.choice === pending.choice) {
        writePending(null);
        return;
      }
      if (!now || now.user !== this.#userId) return;
    }
  }

  /**
   * The account's choice, on signing in: it wins over this device's copy. But the person's most
   * recent choice always wins: given `picksAtStart` (picks when the start asked the server), an
   * answer that comes after the person has picked a theme since then changes nothing (cabledrawer 8 Nov).
   */
  adopt(choice: ThemeChoice, picksAtStart?: number, userId?: number): void {
    if (picksAtStart !== undefined && picksAtStart !== this.#picks) return;
    // This person's own pick, which the server hasn't confirmed, is newer than its answer. (A
    // pending pick of someone else on this device never applies.)
    const pending = readPending();
    if (userId !== undefined && pending && pending.user === userId) choice = pending.choice;
    this.choice = choice;
    save(choice);
    this.#apply();
  }

  /** While someone is signed in, changes are also saved to their account. */
  saveChangesWith(saver: ThemeSaver | null, userId: number | null = null): void {
    this.#saveToAccount = saver;
    this.#userId = saver ? userId : null;
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
