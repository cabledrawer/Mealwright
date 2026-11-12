import type { GroupName } from './sectionOrder.js';

// The little pictures on the phone's Settings list (mockup Dark-Settings08-Phone). Kept here, not in
// the shared Icon, so they load with Settings and nowhere else. Each is a few strokes on a 24 grid.

export type IconKey =
  | 'appearance'
  | 'amounts'
  | 'meal-slots'
  | 'shops-places'
  | 'your-kitchen'
  | 'recent-changes'
  | 'household'
  | 'privacy'
  | 'your-data'
  | 'sign-in'
  | 'about'
  | 'report'
  | 'finish';

export const SECTION_ICONS: Record<
  IconKey,
  { tone: 'you' | 'kitchen' | 'quiet'; paths: string[] }
> = {
  appearance: { tone: 'you', paths: ['M12 3a9 9 0 1 0 0 18z', 'M12 3v18'] },
  amounts: { tone: 'you', paths: ['M12 3v18M5 7h14M5 7l-3 7h6zM19 7l-3 7h6z'] },
  'meal-slots': {
    tone: 'kitchen',
    paths: [
      'M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z',
      'M3 10h18M3 15h18'
    ]
  },
  'shops-places': {
    tone: 'kitchen',
    paths: ['M4 9l1.5-5h13L20 9', 'M4 9h16v11H4z', 'M10 20v-6h4v6']
  },
  'your-kitchen': {
    tone: 'kitchen',
    paths: ['M5 10h14v8a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2z', 'M3 10h18', 'M10 6.5h4M8 3.5h8']
  },
  'recent-changes': {
    tone: 'kitchen',
    paths: ['M3 12a9 9 0 1 0 3-6.7', 'M3 4v5h5', 'M12 8v4l3 2']
  },
  household: {
    tone: 'quiet',
    paths: [
      'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z',
      'M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6',
      'M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14.5c1.8.9 3 2.9 3 5.5'
    ]
  },
  privacy: { tone: 'quiet', paths: ['M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z'] },
  // A database: stacked discs (cabledrawer 12 Nov).
  'your-data': {
    tone: 'quiet',
    paths: [
      'M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z',
      'M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6',
      'M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3'
    ]
  },
  'sign-in': {
    tone: 'quiet',
    paths: ['M12 15a4 4 0 1 1-8 0 4 4 0 0 1 8 0z', 'M11 12l9-9M17 6l3 3M15 8l2 2']
  },
  about: {
    tone: 'quiet',
    paths: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'M12 8h.01M11 12h1v5h1']
  },
  // A flag (proposed, for cabledrawer).
  report: { tone: 'quiet', paths: ['M5 21V4', 'M5 4h12l-2.5 4L17 12H5'] },
  // A tick in a circle (proposed, for cabledrawer).
  finish: { tone: 'kitchen', paths: ['M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z', 'M8 12.5l3 3 5-6'] }
};

/** One row of the list: where it goes (a section of this page, or `href`) and what it shows now. */
export type Row = {
  id: string;
  label: string;
  value?: string;
  icon: IconKey;
  href?: string;
  /** A pill after the label ("Update available"). */
  badge?: string;
  /** A line under the label (the Finish setup row). */
  sub?: string;
};
export type Group = { name: GroupName; label: string; rows: Row[] };
