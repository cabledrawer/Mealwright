// A Copy button's feedback (F237, hand test 15 Nov; cabledrawer's "every Copy button says Copied"):
// the button's label turns to "Copied" for about two seconds after the text is on the clipboard.
// One of these per button. The screen keeps its own toast for a copy that failed.

export const COPIED_FOR_MS = 2000;
export const COPIED = 'Copied';

export class CopyFeedback {
  copied = $state(false);
  #timer: ReturnType<typeof setTimeout> | undefined;

  /** Puts `text` on the clipboard; true when that worked. */
  async copy(text: string): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      this.#clear();
      return false;
    }
    this.copied = true;
    clearTimeout(this.#timer);
    this.#timer = setTimeout(() => this.#clear(), COPIED_FOR_MS);
    return true;
  }

  /** The label for the button: "Copied" for a moment, then `normal`. */
  label(normal: string): string {
    return this.copied ? COPIED : normal;
  }

  #clear() {
    clearTimeout(this.#timer);
    this.#timer = undefined;
    this.copied = false;
  }
}
