import { describe, expect, it } from 'vitest';
import { CACHE_PREFIX, SHELL, VERSION_FILE, appFiles, cacheName, handling, isApi } from './rules';

const own = 'https://home.example';
const assets = new Set(['/_app/immutable/entry/start.js', '/icons/icon-192.png', '/theme.js']);
const get = { method: 'GET', mode: 'no-cors' };
const url = (pathname: string, origin = own) => ({ origin, pathname });

describe('what the service worker handles', () => {
  it('answers pages and the app’s own files from its cache', () => {
    expect(handling({ method: 'GET', mode: 'navigate' }, url('/shopping'), own, assets)).toBe(
      'shell'
    );
    expect(handling(get, url('/icons/icon-192.png'), own, assets)).toBe('asset');
    expect(handling(get, url('/_app/immutable/entry/start.js'), own, assets)).toBe('asset');
  });

  it('never touches /api, the live stream included', () => {
    for (const path of ['/api', '/api/v1/events', '/api/v1/shopping/changes', '/api/anything']) {
      expect(handling(get, url(path), own, assets)).toBe('network');
      expect(handling({ method: 'GET', mode: 'navigate' }, url(path), own, assets)).toBe('network');
    }
    // Even if an /api address were ever (wrongly) in the list of app files.
    expect(handling(get, url('/api/v1/events'), own, new Set(['/api/v1/events']))).toBe('network');
    expect(isApi('/apiary')).toBe(false);
  });

  it('never touches another address', () => {
    expect(handling(get, url('/theme.js', 'https://elsewhere.example'), own, assets)).toBe(
      'network'
    );
  });

  it('leaves writes and unknown files to the network', () => {
    expect(handling({ method: 'POST', mode: 'cors' }, url('/theme.js'), own, assets)).toBe(
      'network'
    );
    expect(handling(get, url('/photos/1.jpg'), own, assets)).toBe('network');
  });

  it('names its cache for the build, and starts from the shell', () => {
    expect(cacheName('abc')).toBe(`${CACHE_PREFIX}abc`);
    expect(SHELL).toBe('/index.html');
  });
});

describe('SvelteKit’s own version check', () => {
  it('is answered by the worker itself, on this address only, for a plain GET', () => {
    expect(VERSION_FILE).toBe('/_app/version.json');
    expect(handling(get, url(VERSION_FILE), own, assets)).toBe('version');
    expect(handling({ method: 'GET', mode: 'cors' }, url(VERSION_FILE), own, assets)).toBe(
      'version'
    );
    expect(handling({ method: 'POST', mode: 'cors' }, url(VERSION_FILE), own, assets)).toBe(
      'network'
    );
    expect(handling(get, url(VERSION_FILE, 'https://elsewhere.example'), own, assets)).toBe(
      'network'
    );
    expect(handling(get, url('/_app/version.json.map'), own, assets)).toBe('network');
  });

  it('is never one of the files the worker keeps', () => {
    const kept = appFiles([{ path: '_app/immutable/entry/start.js' }], [{ path: 'theme.js' }]);
    expect(kept).not.toContain(VERSION_FILE);
  });
});

describe('the app’s own files, from SvelteKit’s manifest', () => {
  it('become absolute addresses, in order, with no repeats', () => {
    expect(
      appFiles(
        [{ path: '_app/immutable/entry/start.js' }, { path: '/_app/immutable/assets/a.css' }],
        [{ path: 'theme.js' }, { path: '/theme.js' }, { path: 'icons/icon-192.png' }]
      )
    ).toEqual([
      '/_app/immutable/entry/start.js',
      '/_app/immutable/assets/a.css',
      '/theme.js',
      '/icons/icon-192.png'
    ]);
  });

  it('are nothing when the manifest is empty (a development run)', () => {
    expect(appFiles([], [])).toEqual([]);
  });
});
