// Makes the app's PNG icons from docs/brand/mealwright-app-icon.svg, once. The PNGs are
// committed in static/icons/; run this again only if the brand icon changes:
//
//   cd frontend && node scripts/make-icons.mjs
//
// It uses the Playwright already in this folder (a local headless Chromium); it opens no
// web pages and sends nothing anywhere.
//
//   icon-192.png, icon-512.png     the icon as designed (rounded square, see-through corners)
//   icon-maskable-512.png          full-bleed green square: phones cut their own shape. The
//                                  artwork already sits inside the middle 80 % (the "safe
//                                  zone"), so it is not shrunk
//   apple-touch-icon.png (180)     full-bleed too: iOS rounds the corners itself and turns
//                                  see-through pixels black
import { mkdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, '../../docs/brand/mealwright-app-icon.svg'), 'utf8');
const out = join(here, '../static/icons');
mkdirSync(out, { recursive: true });

const rounded = source;
const square = source.replace('rx="112"', 'rx="0"');
if (square === source) throw new Error('The icon no longer has rx="112"; update this script.');

const jobs = [
  ['icon-192.png', 192, rounded],
  ['icon-512.png', 512, rounded],
  ['icon-maskable-512.png', 512, square],
  ['apple-touch-icon.png', 180, square]
];

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  for (const [name, size, svg] of jobs) {
    await page.setViewportSize({ width: size, height: size });
    const url = `data:image/svg+xml;base64,${Buffer.from(svg).toString('base64')}`;
    await page.setContent(
      `<body style="margin:0;background:transparent"><img src="${url}" width="${size}" height="${size}" style="display:block"></body>`
    );
    await page.screenshot({ path: join(out, name), omitBackground: true });
    console.log(`${name} ${size}x${size}`);
  }
} finally {
  await browser.close();
}
