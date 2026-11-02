// The version this build of the app shows ("Mealwright 0.7.0"): written into the code when the
// app is built (vite.config.ts), so showing it makes no request to anywhere.

declare const __APP_VERSION__: string;

export const VERSION: string = __APP_VERSION__;

/** "Mealwright 0.7.0". */
export const VERSION_WORDS = `Mealwright ${VERSION}`;
