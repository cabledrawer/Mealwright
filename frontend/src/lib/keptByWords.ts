// The words for the choice "weight, volume or one by one" (F119, cabledrawer 31 Oct): it used to
// read "How it’s counted", "Counted" and "How do you count it?". Every place the choice is asked
// uses these two lines, so they cannot drift apart.
export const KEPT_BY = 'Pantry keeps it by';
export const KEPT_BY_HINT =
  'The way you buy it: a 500 g jar → by weight. Recipes can still use spoons or cups; Mealwright converts.';

// The same choice said back in a summary (Check's settled line, the Save sheet's card; cabledrawer
// 1 Nov: "the same words everywhere"): "Pantry keeps it by weight", "… by volume", "… one by one".
const KEPT_BY_SAID = { weight: 'by weight', volume: 'by volume', count: 'one by one' } as const;
export const keptBySaid = (countedAs: keyof typeof KEPT_BY_SAID): string =>
  `Pantry keeps it ${KEPT_BY_SAID[countedAs]}`;
