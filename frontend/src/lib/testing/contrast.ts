// For component tests: the contrast ratio of an element's text against what it sits on, as the
// browser really drew it (WCAG 2: 4.5 for small text). Used for the dark theme's red words (L6).

const channels = (css: string) => (css.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
const luminance = (css: string) => {
  const [r, g, b] = channels(css).map((c) => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
};
/** The first background that isn't see-through, from the element outwards. */
const backdrop = (el: Element | null): string => {
  for (; el; el = el.parentElement) {
    const background = getComputedStyle(el).backgroundColor;
    if (!/rgba\(.*, 0\)|transparent/.test(background)) return background;
  }
  return getComputedStyle(document.documentElement).backgroundColor;
};
const ratio = (a: string, b: string) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
};

/** The contrast of the element's text colour against the first solid background around it. */
export const contrastOf = (el: Element): number => ratio(getComputedStyle(el).color, backdrop(el));
