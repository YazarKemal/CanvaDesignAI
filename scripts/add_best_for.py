#!/usr/bin/env python3
"""Add `best_for` field to all style presets in config/styles/."""
import json
from pathlib import Path

BEST_FOR = {
    "corporate-dynamic-vector": "tech launches, SaaS products, and professional agency presentations needing a clean, modern corporate gradient look",
    "holographic-glassmorphism": "futurist app UIs, Web3/crypto branding, and sci-fi event promos with iridescent depth",
    "neo-grunge-streetwear": "streetwear drops, underground music gigs, and youth-culture campaigns needing gritty monochrome with a neon punch",
    "bauhaus-modernist-poster": "art-school exhibitions, architecture firm branding, and modernist festival posters with primary-color geometry",
    "kodachrome-americana": "travel editorials, nostalgic brand campaigns, and lifestyle carousels with warm 1970s film-still warmth",
    "riso-print-editorial": "zine covers, indie magazine spreads, and campus event flyers with tactile soy-ink texture",
    "art-deco-metropolis": "luxury gala invitations, hotel branding, and Great Gatsby-era glamour with gold geometric ornament",
    "art-nouveau-botanical": "organic skincare, floral boutique branding, and garden-event promos with flowing vine-inspired line work",
    "brutalist-concrete": "architecture portfolios, industrial-design showcases, and raw urban streetwear with monolithic concrete severity",
    "constructivist-agitprop": "political campaign graphics, protest-art posters, and bold activist branding with diagonal red/black urgency",
    "dutch-golden-age-still-life": "premium food photography, luxury tabletop product shots, and museum-grade fine-art still lives with dramatic chiaroscuro",
    "memphis-design-pop": "1980s-retro parties, kids-brand launches, and playful startup branding with squiggles and clashing neons",
    "mid-century-modern-print": "furniture showroom promos, minimalist homeware branding, and retro cocktail-bar posters with clean atomic-age geometry",
    "psychedelic-fillmore": "music-festival lineups, vinyl-album art, and counterculture event posters with liquid-light typography",
    "swiss-international-grid": "corporate annual reports, editorial magazine layouts, and minimalist fashion branding with Helvetica precision",
    "ukiyo-e-woodblock": "Japanese cuisine menus, tea-ceremony branding, and travel posters with Hokusai-inspired flat color planes",
    "vaporwave-arcade-dusk": "synthwave playlists, retro-gaming tournaments, and ironic 80s/90s nostalgia campaigns with chrome and palm-tree sunsets",
    "y2k-chrome-gloss": "Gen-Z fashion drops, pop-star merch, and early-2000s nostalgia branding with metallic gloss and bubblegum gradients",
    "art-deco-metropolis": "luxury gala invitations, hotel branding, and Great Gatsby-era glamour with gold geometric ornament",
    "formal-ceremonial-turkish": "formal invitations, awards-ceremony collateral, and diplomatic-event branding with ornate symmetry and deep crimson/gold refinement",
    "streamer-energetic-glitch": "Twitch/YouTube overlay packs, gaming-tournament promos, and esports branding with chromatic-aberration energy",
    "utility-planner-ornamental": "bullet-journal spreads, printable planner templates, and functional stationery with delicate ornamental border details",
    "warm-editorial-minimalist": "calm travel carousels, lifestyle-blog branding, and personal-brand Instagram posts with an editorial, understated feel",
}


def main() -> None:
    styles_dir = Path(__file__).resolve().parent.parent / "config" / "styles"
    updated = 0
    for path in sorted(styles_dir.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            preset = json.load(f)

        slug = path.stem
        if slug in BEST_FOR:
            preset["best_for"] = BEST_FOR[slug]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(preset, f, ensure_ascii=False, indent=2)
                f.write("\n")
            print(f"  ✅ {slug}")
            updated += 1
        else:
            print(f"  ⚠️  {slug} — no best_for mapping (SKIPPED)")

    print(f"\nUpdated {updated}/{updated} presets.")


if __name__ == "__main__":
    main()
