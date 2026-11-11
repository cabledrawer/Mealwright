// The little pictures on the phone's Settings list (mockup Dark-Settings08-Phone). Kept here, not in
// the shared Icon, so they load with Settings and nowhere else. Each is a few strokes on a 24 grid.

export type IconKey =
  | 'appearance'
  | 'amounts'
  | 'meal-slots'
  | 'shops-places'
  | 'your-kitchen'
  | 'recent-changes'
  | 'privacy'
  | 'sign-in';

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
  privacy: { tone: 'quiet', paths: ['M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6z'] },
  'sign-in': {
    tone: 'quiet',
    paths: ['M12 15a4 4 0 1 1-8 0 4 4 0 0 1 8 0z', 'M11 12l9-9M17 6l3 3M15 8l2 2']
  }
};

/** One row of the list: where it goes (a section of this page, or `href`) and what it shows now. */
export type Row = { id: string; label: string; value?: string; icon: IconKey; href?: string };
export type Group = { name: string; label: string; rows: Row[] };
