// A screen's memory that most pages never use (Privacy's switches, for now) is not loaded with
// every page: it is code only the screens that show it need (the browser code limit, spec
// "Keeping the UI good", item 5). This is how the app's shell still forgets it when a sign-in
// ends or the device is wiped: the memory adds its forget here when it is loaded, and the shell
// calls `forgetLoaded`, which does nothing for what was never loaded (nothing is held then).
const loaded = new Map<string, () => void>();

/** Called by the memory itself, once, when its code is loaded. */
export function rememberToForget(name: string, forget: () => void): void {
  loaded.set(name, forget);
}

/** Forget it if it was ever loaded. */
export function forgetLoaded(name: string): void {
  loaded.get(name)?.();
}
