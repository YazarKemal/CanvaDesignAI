/** Curated example prompts reflecting the diversity of the 22 style presets.
 * Each entry maps to one or more style categories so users indirectly discover
 * the system's range when cycling through suggestions. */

export const SUGGESTIONS: string[] = [
  "a grand opening flyer for a specialty coffee shop",       // warm-editorial-minimalist, corporate-dynamic-vector
  "a birthday party invitation for a 5 year old",             // memphis-design-pop, y2k-chrome-gloss
  "a streetwear brand lookbook cover with edgy aesthetic",    // neo-grunge-streetwear
  "a tech startup product launch announcement poster",        // holographic-glassmorphism, corporate-dynamic-vector
  "a wedding invitation with elegant botanical details",      // art-nouveau-botanical, formal-ceremonial-turkish
  "a concert poster for an indie rock band",                  // psychedelic-fillmore, riso-print-editorial
  "a weekly planner layout with ornamental grid",             // utility-planner-ornamental
  "a minimalist travel blog Instagram post",                  // warm-editorial-minimalist, kodachrome-americana
  "a retro 80s themed nightclub event flyer",                 // vaporwave-arcade-dusk, memphis-design-pop
  "a luxury fashion brand seasonal sale announcement",        // art-deco-metropolis, swiss-international-grid
];

export function pickRandom(list: string[]): string {
  return list[Math.floor(Math.random() * list.length)];
}
