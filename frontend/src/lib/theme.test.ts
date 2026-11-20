import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { page } from 'vitest/browser';
import ThemeSwitch from './components/ThemeSwitch.svelte';
import { THEME_PENDING_KEY, THEME_STORAGE_KEY, nextTheme, theme } from './theme.svelte';

const root = document.documentElement;

// static/theme.js, fetched the way the browser loads it.
const startupScript = await (await fetch('/theme.js')).text();

/** Run static/theme.js as the browser would at start-up. */
function runStartupScript() {
  new Function(startupScript)();
}

beforeEach(() => {
  localStorage.clear();
  root.removeAttribute('data-theme');
  root.removeAttribute('data-theme-choice');
});

describe('nextTheme', () => {
  it('steps Auto → Light → Dark → Auto', () => {
    expect(nextTheme('auto')).toBe('light');
    expect(nextTheme('light')).toBe('dark');
    expect(nextTheme('dark')).toBe('auto');
  });
});

describe('start-up script (static/theme.js)', () => {
  const deviceDark = matchMedia('(prefers-color-scheme: dark)').matches;

  it('uses Auto when nothing is saved', () => {
    runStartupScript();
    expect(root.dataset.themeChoice).toBe('auto');
    expect(root.dataset.theme).toBe(deviceDark ? 'dark' : 'light');
  });

  it('applies a saved choice', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    runStartupScript();
    expect(root.dataset.theme).toBe('dark');
    localStorage.setItem(THEME_STORAGE_KEY, 'light');
    runStartupScript();
    expect(root.dataset.theme).toBe('light');
  });

  it('ignores anything else saved', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'purple');
    runStartupScript();
    expect(root.dataset.themeChoice).toBe('auto');
  });

  it('agrees with the app about what was saved', () => {
    theme.set('dark');
    root.removeAttribute('data-theme');
    runStartupScript();
    expect(root.dataset.theme).toBe('dark');
    theme.set('auto');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });
});

describe('theme', () => {
  it('saves the choice and applies it to the page', () => {
    theme.set('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(root.dataset.theme).toBe('dark');
    expect(root.dataset.themeChoice).toBe('dark');
    theme.set('light');
    expect(root.dataset.theme).toBe('light');
  });

  it('colours the browser bar like the page, light or dark, even when picked by hand', () => {
    const meta = document.createElement('meta');
    meta.name = 'theme-color';
    document.head.append(meta);
    try {
      theme.set('dark');
      expect(meta.content).toBe('#111614');
      theme.set('light');
      expect(meta.content).toBe('#f5f6f4');
    } finally {
      meta.remove();
    }
  });

  it('colours it at start-up too (static/theme.js)', () => {
    const meta = document.createElement('meta');
    meta.name = 'theme-color';
    document.head.append(meta);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, 'dark');
      runStartupScript();
      expect(meta.content).toBe('#111614');
      localStorage.setItem(THEME_STORAGE_KEY, 'light');
      runStartupScript();
      expect(meta.content).toBe('#f5f6f4');
    } finally {
      meta.remove();
    }
  });

  it('cycles', () => {
    theme.set('auto');
    theme.cycle();
    expect(theme.choice).toBe('light');
    theme.cycle();
    expect(theme.choice).toBe('dark');
    theme.cycle();
    expect(theme.choice).toBe('auto');
  });
});

describe('ThemeSwitch', () => {
  let component: ReturnType<typeof mount> | null = null;

  afterEach(() => {
    if (component) unmount(component);
    component = null;
  });

  it('shows Auto · Light · Dark with the current one pressed', async () => {
    theme.set('auto');
    component = mount(ThemeSwitch, { target: document.body, props: { variant: 'pill' } });
    flushSync();
    const group = page.getByRole('group', { name: 'Theme' });
    await expect
      .element(group.getByRole('button', { name: 'Auto' }))
      .toHaveAttribute('aria-pressed', 'true');
    await group.getByRole('button', { name: 'Dark' }).click();
    await expect
      .element(group.getByRole('button', { name: 'Dark' }))
      .toHaveAttribute('aria-pressed', 'true');
    await expect
      .element(group.getByRole('button', { name: 'Auto' }))
      .toHaveAttribute('aria-pressed', 'false');
    expect(root.dataset.theme).toBe('dark');
  });

  it('as one button, steps through the three and says what is next', async () => {
    theme.set('auto');
    component = mount(ThemeSwitch, { target: document.body, props: { variant: 'cycle' } });
    flushSync();
    const button = page.getByRole('button', { name: /^Theme:/ });
    await expect.element(button).toHaveAccessibleName('Theme: Auto. Switch to Light');
    await button.click();
    await expect.element(button).toHaveAccessibleName('Theme: Light. Switch to Dark');
    expect(root.dataset.theme).toBe('light');
  });
});

describe('a pick is the most recent choice until the server has it (cabledrawer 9 Nov)', () => {
  const pending = () => localStorage.getItem(THEME_PENDING_KEY);
  /** A saver that can't reach the server until `online` is set. */
  function server() {
    const sent: string[] = [];
    const state = { online: false };
    const saver = async (choice: string) => {
      if (!state.online) return false;
      sent.push(choice);
      return true;
    };
    return { sent, state, saver };
  }

  afterEach(() => {
    theme.saveChangesWith(null);
    theme.adopt('auto');
  });

  it('an offline pick stays pending, and after a reload is still the pick, over an older server answer', async () => {
    const s = server();
    theme.saveChangesWith(s.saver, 2);
    theme.set('dark');
    await theme.flush();
    expect(pending()).toBe('{"user":2,"choice":"dark"}');
    // A reload: the app starts again from this device's copy, and the server still says Light.
    theme.saveChangesWith(null);
    theme.start();
    expect(theme.choice).toBe('dark');
    theme.adopt('light', undefined, 2);
    expect(theme.choice).toBe('dark');
    expect(root.dataset.theme).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('back online it is sent once, then the pending mark is cleared', async () => {
    const s = server();
    theme.saveChangesWith(s.saver, 2);
    theme.adopt('auto', undefined, 2); // the server has said who is signed in
    theme.set('dark');
    await theme.flush();
    expect(s.sent).toEqual([]);
    s.state.online = true;
    await Promise.all([theme.flush(), theme.flush()]);
    await theme.flush();
    expect(s.sent).toEqual(['dark']);
    expect(pending()).toBeNull();
  });

  it('once confirmed, the server’s value counts again (a pick from another device arrives)', async () => {
    const s = server();
    s.state.online = true;
    theme.saveChangesWith(s.saver, 2);
    theme.adopt('auto', undefined, 2);
    theme.set('dark');
    await theme.flush();
    expect(pending()).toBeNull();
    theme.adopt('light', undefined, 2);
    expect(theme.choice).toBe('light');
  });

  it('a newer pick made while one is being sent is sent after it, and is what stays', async () => {
    const sent: string[] = [];
    let release!: () => void;
    const gate = new Promise<void>((done) => (release = done));
    let asked = 0;
    theme.saveChangesWith(async (choice) => {
      asked += 1;
      if (sent.length === 0) await gate;
      sent.push(choice);
      return true;
    }, 2);
    theme.adopt('auto', undefined, 2);
    theme.set('dark');
    await expect.poll(() => asked).toBe(1); // Dark is on its way
    theme.set('light');
    release();
    await expect.poll(() => sent).toEqual(['dark', 'light']);
    await expect.poll(pending).toBeNull();
    expect(theme.choice).toBe('light');
  });

  it('a stored pick waits until the server has said this person is signed in (FR1 review 1)', async () => {
    const s = server();
    s.state.online = true;
    // Opened from this device as person 2; the browser's session may already be someone else's.
    localStorage.setItem(THEME_PENDING_KEY, '{"user":2,"choice":"dark"}');
    theme.saveChangesWith(s.saver, 2);
    await theme.flush();
    expect(s.sent).toEqual([]);
    // The server names someone else: still not sent.
    theme.adopt('light', undefined, 9);
    await theme.flush();
    expect(s.sent).toEqual([]);
    // The server names person 2: sent now.
    theme.adopt('light', undefined, 2);
    await expect.poll(() => s.sent).toEqual(['dark']);
    await expect.poll(pending).toBeNull();
  });

  it('someone else’s pending pick never applies, and is not sent as this person', async () => {
    const s = server();
    s.state.online = true;
    localStorage.setItem(THEME_PENDING_KEY, '{"user":9,"choice":"dark"}');
    theme.saveChangesWith(s.saver, 2);
    theme.adopt('light', undefined, 2);
    expect(theme.choice).toBe('light');
    await theme.flush();
    expect(s.sent).toEqual([]);
    expect(pending()).toBe('{"user":9,"choice":"dark"}');
  });
});
