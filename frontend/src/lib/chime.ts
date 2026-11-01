// The sound a Cook mode timer ends with (cabledrawer 31 Oct): one short, gentle chime made for
// Mealwright, played three times. It is made here, in code, from sine waves with the browser's
// own Web Audio: there is no sound file, nothing is fetched and nothing is sent anywhere, so the
// strict content security policy needs no change. There is no choice of sound yet.

/** How many times the chime plays. */
export const CHIME_PLAYS = 3;
/** Seconds from the start of one chime to the start of the next. */
export const CHIME_GAP = 1.1;
/** How long one chime rings. */
export const CHIME_RING = 0.9;

/** The two sine waves of one chime: a soft bell note and a quieter one an octave and a half up. */
const PARTIALS: { hertz: number; level: number }[] = [
  { hertz: 659.25, level: 0.22 },
  { hertz: 1318.5, level: 0.07 }
];

interface Context {
  currentTime: number;
  state?: string;
  destination: unknown;
  resume?: () => Promise<void>;
  createOscillator(): {
    type: string;
    frequency: { value: number };
    connect(to: unknown): unknown;
    start(at: number): void;
    stop(at: number): void;
  };
  createGain(): {
    gain: {
      value: number;
      setValueAtTime(value: number, at: number): unknown;
      linearRampToValueAtTime(value: number, at: number): unknown;
      exponentialRampToValueAtTime(value: number, at: number): unknown;
    };
    connect(to: unknown): unknown;
  };
}

let shared: Context | null = null;

/** The browser's audio, or null where it has none. */
function make(): Context | null {
  if (typeof window === 'undefined') return null;
  const ctor =
    (window as unknown as { AudioContext?: new () => Context }).AudioContext ??
    (window as unknown as { webkitAudioContext?: new () => Context }).webkitAudioContext;
  if (!ctor) return null;
  try {
    return new ctor();
  } catch {
    return null;
  }
}

/**
 * Called from a tap (Start timer), because a browser lets a page make sound only after the
 * person has touched it. The sound then plays later, when the timer ends.
 */
export function primeChime(): void {
  shared ??= make();
  if (shared?.state === 'suspended') void shared.resume?.().catch(() => undefined);
}

/**
 * Play the chime three times. Returns when each one starts, in seconds on the audio clock
 * (empty where the browser can't make sound). `context` is for tests.
 */
export function playChime(context: Context | null = (shared ??= make())): number[] {
  if (!context) return [];
  if (context.state === 'suspended') void context.resume?.().catch(() => undefined);
  const starts: number[] = [];
  const first = context.currentTime + 0.05;
  for (let play = 0; play < CHIME_PLAYS; play++) {
    const at = first + play * CHIME_GAP;
    starts.push(at);
    for (const { hertz, level } of PARTIALS) {
      const tone = context.createOscillator();
      const volume = context.createGain();
      tone.type = 'sine';
      tone.frequency.value = hertz;
      // A soft start, then a long fade: a bell, not a beep.
      volume.gain.setValueAtTime(0.0001, at);
      volume.gain.linearRampToValueAtTime(level, at + 0.03);
      volume.gain.exponentialRampToValueAtTime(0.0001, at + CHIME_RING);
      tone.connect(volume);
      volume.connect(context.destination);
      tone.start(at);
      tone.stop(at + CHIME_RING + 0.05);
    }
  }
  return starts;
}
