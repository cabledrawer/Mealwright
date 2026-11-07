// The version this build of the app shows ("Mealwright v0.8.0-alpha.1"): written into the code when
// the app is built (vite.config.ts), so showing it makes no request to anywhere.

declare const __APP_VERSION__: string;

/** The version as Python writes it, e.g. "0.8.0a1" (the server's own form is unchanged). */
export const VERSION: string = __APP_VERSION__;

const PRE = { a: 'alpha', b: 'beta', rc: 'rc' } as const;

/**
 * A version as the tag cabledrawer pushes (7 Nov): "0.8.0a1" is "v0.8.0-alpha.1", "0.8.0b1" is
 * "v0.8.0-beta.1", "0.8.0rc1" is "v0.8.0-rc.1" and "0.8.0" is "v0.8.0". Anything else (a test
 * build's own text) is shown as it is.
 */
export function tagForm(version: string): string {
  const found = /^(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?$/.exec(version);
  if (!found) return version;
  const [, release, kind, number] = found;
  return kind ? `v${release}-${PRE[kind as keyof typeof PRE]}.${number}` : `v${release}`;
}

/** "Mealwright v0.8.0-alpha.1". */
export const VERSION_WORDS = `Mealwright ${tagForm(VERSION)}`;
