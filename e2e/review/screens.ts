// Screenshot review: the app next to its mockup, at phone and desktop sizes, light and
// dark. Run by hand while reviewing a pull request; not part of ./check.
//
//   cd e2e
//   node review/screens.ts --screen Pantry                        # mockups only
//   node review/screens.ts --screen Pantry --path /pantry --serve # app + mockups
//
// Options:
//   --screen NAME   mockups whose canvas title has "· NAME ·" (e.g. Pantry, Ingredients)
//   --mockup FILE   a mockup file by name (repeatable), e.g. --mockup Phone-Pantry
//   --path PATH     the app page to capture (e.g. /pantry)
//   --serve         build and start the app with serve.mjs (port E2E_APP_PORT, default
//                   18080), then stop it afterwards. Without it, the app must already
//                   be running at --base-url.
//   --base-url URL  default http://127.0.0.1:$E2E_APP_PORT
//   --prepare FILE  a module with optional `seed(api)` (run once, signed in) and
//                   `prepare(page, shot)` (run on every shot after the page opens, e.g.
//                   to open the edit sheet the phone mockup shows)
//   --out DIR       default review-shots/<screen or path> (git-ignored)
//   --locale TAG    the browser's language, default en-GB (cabledrawer is in the UK; en-US
//                   would give the household a 240 ml cup)
//
// For each size and theme it writes app-*.png, mockup-*.png and compare-*.png (the two
// side by side on phone, one above the other on desktop).
//
// The mockups are exports from the design canvas: they load the canvas runtime and
// Google Fonts, and use <sc-if> / {{ … }} canvas tags. Here they are rendered offline:
// scripts and the font link are removed, <helmet> and <x-dc> unwrapped, each <sc-if>
// kept or dropped by its preview value, and the bundled fonts from frontend/
// node_modules are inlined; canvas images (/_blob/…, only the logo so far) become
// the logo from docs/brand. Every network request is blocked. Close, not exact.
import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { chromium, request, type APIRequestContext, type Browser, type Page } from '@playwright/test';
import { ADMIN, PORTS, local } from '../tests/servers.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const E2E = resolve(HERE, '..');
const REPO = resolve(E2E, '..');
const MOCKUPS = join(REPO, 'docs', 'mockups');

export type Size = 'phone' | 'desktop';
export type Theme = 'light' | 'dark';
export type Shot = { size: Size; theme: Theme };

export const SIZES: Record<Size, { width: number; height: number }> = {
  phone: { width: 390, height: 844 },
  desktop: { width: 1440, height: 900 },
};
const SHOTS: Shot[] = (['phone', 'desktop'] as const).flatMap((size) =>
  (['light', 'dark'] as const).map((theme) => ({ size, theme })),
);
const label = ({ size, theme }: Shot) => `${size}-${theme}`;

type Board = { title: string; w: number; h: number };

/** The canvas boards for a screen, keyed by size and theme from their titles. */
function findMockups(screen: string | undefined, files: string[]): Map<string, { file: string; board: Board }> {
  const canvas = JSON.parse(readFileSync(join(MOCKUPS, 'canvas.json'), 'utf8')) as {
    boards: Record<string, Board>;
  };
  const found = new Map<string, { file: string; board: Board }>();
  for (const [file, board] of Object.entries(canvas.boards)) {
    const byName = files.some((f) => file === f || file === `${f}.dc.html`);
    const byScreen = screen && board.title.toLowerCase().includes(` · ${screen.toLowerCase()} · `);
    if (!byName && !byScreen) continue;
    const size: Size = / · phone · /.test(board.title) ? 'phone' : 'desktop';
    const theme: Theme = / · dark/.test(board.title) ? 'dark' : 'light';
    const key = label({ size, theme });
    if (found.has(key)) {
      console.warn(`Two mockups for ${key}: ${found.get(key)!.file} and ${file}; using the first.`);
      continue;
    }
    found.set(key, { file, board });
  }
  return found;
}

/** @font-face rules for the bundled fonts, inlined, so mockups render offline. */
function fontFaces(): string {
  const base = join(REPO, 'frontend', 'node_modules', '@fontsource-variable');
  const faces = [
    { family: 'Plus Jakarta Sans', file: 'plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-normal.woff2', weight: '200 800', style: 'normal' },
    { family: 'Plus Jakarta Sans', file: 'plus-jakarta-sans/files/plus-jakarta-sans-latin-wght-italic.woff2', weight: '200 800', style: 'italic' },
    { family: 'Newsreader', file: 'newsreader/files/newsreader-latin-wght-normal.woff2', weight: '200 800', style: 'normal' },
    { family: 'Newsreader', file: 'newsreader/files/newsreader-latin-wght-italic.woff2', weight: '200 800', style: 'italic' },
  ];
  const rules: string[] = [];
  for (const face of faces) {
    const path = join(base, face.file);
    if (!existsSync(path)) {
      console.warn(`Font not found (${path}); run "npm ci" in frontend/. Using a fallback font.`);
      continue;
    }
    const data = readFileSync(path).toString('base64');
    rules.push(
      `@font-face{font-family:'${face.family}';font-style:${face.style};font-weight:${face.weight};font-display:block;src:url(data:font/woff2;base64,${data}) format('woff2')}`,
    );
  }
  return rules.join('\n');
}

/** The logo, standing in for canvas images that weren't exported (/_blob/…). */
function logo(dark: boolean): string {
  const file = join(REPO, 'docs', 'brand', dark ? 'mealwright-mark-dark.svg' : 'mealwright-mark.svg');
  return existsSync(file) ? `data:image/svg+xml;base64,${readFileSync(file).toString('base64')}` : '';
}

/** A mockup's markup with the canvas runtime and outside links taken out. */
function cleanMockup(html: string, fonts: string, dark: boolean): string {
  return html
    .replace(/src="\/_blob\/[^"]*"/g, `src="${logo(dark)}"`)
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<link\b[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>/gi, '')
    .replace(/<\/?(helmet|x-dc)\b[^>]*>/gi, '')
    .replace('</head>', `<style>${fonts}</style></head>`);
}

async function renderMockup(browser: Browser, file: string, board: Board, out: string, fonts: string) {
  const context = await browser.newContext({ viewport: { width: board.w, height: board.h } });
  const page = await context.newPage();
  const blocked: string[] = [];
  await page.route('**/*', (route) => {
    blocked.push(route.request().url());
    return route.abort();
  });
  await page.setContent(cleanMockup(readFileSync(join(MOCKUPS, file), 'utf8'), fonts, / · dark/.test(board.title)));
  await page.evaluate(() => {
    // Innermost first, so nested ones are settled before their parents.
    for (const el of [...document.querySelectorAll('sc-if')].reverse()) {
      const show = /\btrue\b/.test(el.getAttribute('hint-placeholder-val') ?? '');
      if (show) el.replaceWith(...el.childNodes);
      else el.remove();
    }
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      if (node.nodeValue?.includes('{{')) node.nodeValue = node.nodeValue.replace(/\{\{[^}]*\}\}/g, '…');
    }
  });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: out });
  await context.close();
  if (blocked.length) console.log(`  (blocked ${blocked.length} request(s) from ${file}: ${blocked[0]}${blocked.length > 1 ? ', …' : ''})`);
}

/** Signed in as the test admin: sets Mealwright up if it's fresh, else signs in. */
async function signIn(baseURL: string): Promise<APIRequestContext> {
  const api = await request.newContext({ baseURL });
  const setup = await api.post('/api/v1/setup', { data: ADMIN });
  if (setup.status() === 201) return api;
  const session = await api.post('/api/v1/session', {
    data: { username: ADMIN.username, password: ADMIN.password },
  });
  if (!session.ok()) {
    throw new Error(`Couldn't sign in as ${ADMIN.username}: ${session.status()} ${await session.text()}`);
  }
  return api;
}

type Prepare = {
  seed?: (api: APIRequestContext) => Promise<void>;
  prepare?: (page: Page, shot: Shot) => Promise<void>;
};

async function captureApp(
  browser: Browser,
  baseURL: string,
  path: string,
  shot: Shot,
  storageState: Awaited<ReturnType<APIRequestContext['storageState']>>,
  prep: Prepare,
  out: string,
  locale: string,
) {
  const context = await browser.newContext({
    baseURL,
    viewport: SIZES[shot.size],
    colorScheme: shot.theme,
    storageState,
    locale,
    ...(shot.size === 'phone' ? { isMobile: true, hasTouch: true, deviceScaleFactor: 1 } : {}),
  });
  const page = await context.newPage();
  const outside: string[] = [];
  await page.route(
    (url) => url.origin !== new URL(baseURL).origin,
    (route) => {
      outside.push(route.request().url());
      return route.abort();
    },
  );
  await page.goto(path);
  await page.locator(`html[data-theme="${shot.theme}"]`).waitFor();
  await page.evaluate(() => document.fonts.ready);
  await prep.prepare?.(page, shot);
  await page.waitForLoadState('networkidle');
  await page.screenshot({ path: out });
  const sideways = await page.evaluate(() => {
    const root = document.scrollingElement ?? document.documentElement;
    return root.scrollWidth > root.clientWidth ? `${root.scrollWidth} > ${root.clientWidth}` : '';
  });
  if (sideways) console.log(`  ! ${label(shot)}: the page scrolls sideways (${sideways} px)`);
  if (outside.length) console.log(`  ! ${label(shot)}: requests to outside addresses: ${outside.join(', ')}`);
  await context.close();
}

async function compose(browser: Browser, shot: Shot, app: string | null, mockup: string | null, out: string) {
  const img = (file: string | null, caption: string) =>
    file
      ? `<figure><figcaption>${caption}</figcaption><img src="data:image/png;base64,${readFileSync(file).toString('base64')}"></figure>`
      : `<figure><figcaption>${caption}: none</figcaption></figure>`;
  const direction = shot.size === 'phone' ? 'row' : 'column';
  const html = `<!doctype html><style>
    body{margin:0;padding:16px;background:#888;font:600 16px system-ui;display:flex;flex-direction:${direction};gap:24px;align-items:flex-start}
    figure{margin:0}figcaption{margin-bottom:6px;color:#fff}img{display:block;box-shadow:0 0 0 1px #000}
  </style>${img(app, `App · ${label(shot)}`)}${img(mockup, `Mockup · ${label(shot)}`)}`;
  const page = await browser.newPage({ viewport: { width: 400, height: 400 } });
  await page.setContent(html);
  await page.screenshot({ path: out, fullPage: true });
  await page.close();
}

async function startApp(port: number): Promise<ChildProcess> {
  console.log(`Building and starting the app (port ${port})…`);
  const child = spawn('node', ['serve.mjs'], {
    cwd: E2E,
    stdio: ['ignore', 'ignore', 'inherit'],
    env: { ...process.env, E2E_APP_PORT: String(port) },
    detached: true,
  });
  for (let i = 0; i < 1800; i++) {
    if (child.exitCode !== null) throw new Error('serve.mjs stopped before the app was up');
    try {
      if ((await fetch(`${local(port)}/api/v1/version`)).ok) return child;
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 100));
  }
  throw new Error('the app did not start within 3 minutes');
}

async function main() {
  const { values } = parseArgs({
    options: {
      screen: { type: 'string' },
      mockup: { type: 'string', multiple: true, default: [] },
      path: { type: 'string' },
      serve: { type: 'boolean', default: false },
      'base-url': { type: 'string' },
      locale: { type: 'string', default: 'en-GB' },
      prepare: { type: 'string' },
      out: { type: 'string' },
    },
  });
  if (!values.screen && !values.mockup.length && !values.path) {
    console.error('Give --screen, --mockup or --path. See the top of review/screens.ts.');
    process.exit(2);
  }
  const slug = (values.screen ?? values.path ?? values.mockup[0]).replace(/^\/+/, '').replace(/[^\w-]+/g, '-') || 'today';
  const out = resolve(values.out ?? join(E2E, 'review-shots', slug));
  mkdirSync(out, { recursive: true });

  const mockups = findMockups(values.screen, values.mockup);
  if ((values.screen || values.mockup.length) && mockups.size === 0) console.warn('No matching mockups found.');

  const browser = await chromium.launch();
  let server: ChildProcess | undefined;
  try {
    const fonts = fontFaces();
    for (const [key, { file, board }] of mockups) {
      console.log(`Mockup ${key}: ${file}`);
      await renderMockup(browser, file, board, join(out, `mockup-${key}.png`), fonts);
    }

    if (values.path) {
      const port = PORTS.main;
      if (values.serve) server = await startApp(port);
      const baseURL = values['base-url'] ?? local(port);
      const api = await signIn(baseURL);
      const prep: Prepare = values.prepare ? await import(pathToFileURL(resolve(values.prepare)).href) : {};
      await prep.seed?.(api);
      // The theme comes from the device setting; put the account on Auto.
      await api.put('/api/v1/me/preferences', { data: { theme: 'auto' } });
      const state = await api.storageState();
      await api.dispose();
      for (const shot of SHOTS) {
        console.log(`App ${label(shot)}: ${values.path}`);
        await captureApp(browser, baseURL, values.path, shot, state, prep, join(out, `app-${label(shot)}.png`), values.locale);
      }
    }

    for (const shot of SHOTS) {
      const app = join(out, `app-${label(shot)}.png`);
      const mock = join(out, `mockup-${label(shot)}.png`);
      const haveApp = values.path ? app : null;
      const haveMock = mockups.has(label(shot)) ? mock : null;
      if (haveApp && haveMock) await compose(browser, shot, haveApp, haveMock, join(out, `compare-${label(shot)}.png`));
    }
    writeFileSync(join(out, 'README.txt'), `Made by e2e/review/screens.ts on ${new Date().toISOString()}\n`);
    console.log(`Done: ${out}`);
  } finally {
    await browser.close();
    if (server?.pid) process.kill(-server.pid, 'SIGTERM');
  }
}

await main();
