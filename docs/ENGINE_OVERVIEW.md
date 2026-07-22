# CanvaDesignAI — Full Engine Technical Overview

> **Version:** 3.2.0 (design_rules.json) | **Date:** 2026-07-22 | **Tests:** 195 backend + 7 frontend

---

## 1. PIPELINE FLOW

The system is a 3-stage single-engine pipeline. All stages run on `deepseek-chat` via the OpenAI-compatible API at `api.deepseek.com` (pure-httpx fallback via `src/http_client.py` when the `openai` SDK isn't available, e.g. Android/Termux).

```
User request (+ optional brand/style slug)
    │
    ▼
Architect (DeepSeek, temp=0.2)  ──►  technical design brief JSON
    │
    ▼
Generator (DeepSeek, temp=0.3)  ──►  Canva automation card JSON
    │
    ▼
Reviewer (DeepSeek, temp=0.0)   ──►  score + pass/fail + feedback
    │
    ├── score ≥ 8.5  ──►  RETURN approved
    └── score < 8.5   ──►  feedback → retry Generator (up to 3 attempts)
```

### 1.1 Architect (`src/architect.py:150`)

**Task:** Analyze user request → produce technical design brief.

- **Model:** `deepseek-chat`, **temperature:** 0.2
- **Input:** user concept string + optional brand profile + optional style preset + keyword category hint from `detect_category()`
- **Output:** JSON brief with fields:

| Field | Description |
|---|---|
| `detected_category` | e.g. `instagram_post`, `flyer_a4` |
| `aspect_ratio` | e.g. `"1:1 (1080x1080)"` |
| `target_tool` | e.g. `"Canva Magic Media"` |
| `magic_media_style` | e.g. `"Minimalist"` from knowledge base |
| `text_zone` | `top` / `bottom` / `left` / `right` / `center` |
| `art_direction` | `{color_palette, lighting, mood}` |
| `canva_keywords` | 2–4 from `canva_element_keywords` |
| `negative_constraints` | negative-space reserving language |
| `selected_style_id` | style slug (auto-selected or user-chosen) |

- **Auto-style selection:** When no manual style is chosen, the Architect's system prompt includes `best_for_summaries()` — a bullet list of all 22 presets with their `best_for` descriptions. The Architect picks the best-fit slug via `selected_style_id` in the brief. `_style_selection_rule()` (`architect.py:47`) determines whether to show the full menu (auto) or just confirm the existing slug (manual).
- **Keyword hint:** `detect_category()` (`canva_rules.py:90`) matches 25 keywords (including Turkish) against the user request for a cheap design-category hint — saves the LLM from having to guess the format entirely from scratch.

### 1.2 Generator (`src/generator.py:198`)

**Task:** Turn brief → full Canva automation card.

- **Model:** `deepseek-chat`, **temperature:** 0.3
- **Input:** concept + architect brief JSON + feedback from prior rejection (if any)
- **Output:** Canva card JSON with 3 mandatory components + validated by `validate_prompt()`
- **System prompt** (`_system_prompt()`, line 72):
  - Constitution via `as_prompt_block(load_constitution())`
  - Canva knowledge base
  - **Composition rules** from `composition_rules.py` (format-specific for 9:16 / 1:1 / 16:9 / 4:5)
  - **Style section** (if active) — includes golden reference card via `as_few_shot_block()`
  - **Brand section** (if active) — with visual_identity suppression when style also active
  - `OUTPUT_FORMAT_EXAMPLE` as shape reference

**Code-level validation cascade** (`schema.py:246`, runs inside `generate_prompt()` before returning):

| # | Check | Error |
|---|---|---|
| 1 | JSON Schema shape (8 required fields) | `jsonschema.ValidationError` |
| 2 | Forbidden chat phrases (24 substrings, case-insensitive) | `PromptValidationError` |
| 3 | Headline ≤6 words, subtext ≤14 words | `PromptValidationError` |
| 4 | WCAG contrast ≥4.5:1 within palette | `PromptValidationError` |
| 5 | `text_zone` mentioned in both `magic_media_prompt` AND `background_layers` | `PromptValidationError` |
| 6 | Brand active: exact font match + palette ⊆ approved colors | `PromptValidationError` |
| 7 | Style active: `required_keywords` all appear in `magic_media_prompt` | `PromptValidationError` |

### 1.3 Reviewer (`src/reviewer.py:86`)

**Task:** Score card against 7-criterion rubric → pass/fail + actionable feedback.

- **Model:** `deepseek-chat`, **temperature:** 0.0 (deterministic)
- **Input:** card JSON + constitution + optional brand profile
- **Output:** `ReviewResult` dataclass (`score`, `passed`, `criteria_scores` dict, `feedback` string)
- **Pass threshold:** 8.5 (weighted average of 7 criteria at weights totaling 1.0)

### 1.4 Retry Logic (`src/orchestrator.py:63`)

`run_pipeline()` — 3 default attempts (`DEFAULT_MAX_ATTEMPTS = 3`):

```
for attempt in 1..3:
    card = generate_prompt(brief, ..., feedback=feedback)
    │
    ├── PromptValidationError? → feedback = str(exc); continue
    │
    └── review = review_prompt(card, ...)
        ├── review.passed? → RETURN PipelineResult(approved=True)
        └── !passed? → feedback = review.feedback; continue

After loop: RETURN best-scoring card (approved=False)
             OR raise PipelineError (if no valid card ever produced)
```

Two feedback sources feed the same `feedback` variable:
- **Code-level:** `PromptValidationError` text (structural/schema failure)
- **LLM-level:** Reviewer's `feedback` field (qualitative failure)

---

## 2. REVIEW RUBRIC

From `design_rules.json:128-141`, 7 criteria with weighted-average scoring, 0–10 per criterion:

| # | Criterion | Weight | What It Measures |
|---|---|---|---|
| 1 | `concept_fidelity` | 0.12 | Faithfully captures user's original concept |
| 2 | `magic_media_prompt_quality` | 0.18 | Concrete, renderable, correctly ordered, uses aesthetic_taxonomy |
| 3 | `layer_typography_architecture_quality` | 0.18 | Short headline/subtext, valid HEX with contrast anchor, font pairing |
| 4 | `direct_action_tip_quality` | 0.13 | Actionable, concrete steps (not generic advice) |
| 5 | `canva_fit` | 0.14 | Canva keywords, negative space at text_zone, visual-weight balance |
| 6 | `format_discipline` | 0.15 | Zero chat/question language — pure automation data |
| 7 | `brand_fit` | 0.10 | On-brand feel; scores 10 if no brand active (never penalizes brand-less) |

**Pass threshold: 8.5** — rationale from design: the weighted average ensures a card can't pass if any single criterion bottoms out. The two highest-weighted criteria (prompt_quality and typography_quality at 0.18 each) plus format_discipline (0.15) account for 51% of the total — a card that's chatty, has a weak prompt, or poor typography architecture mathematically cannot reach 8.5 even with perfect scores elsewhere.

**Special rule:** Any detected `forbidden_chat_phrase` caps `format_discipline` at 0 regardless of LLM scoring. This is enforced at both the code level (`schema.py:24` phrases, checked deterministically) AND via the Reviewer's system prompt instruction.

---

## 3. STYLE PRESET SYSTEM

22 presets in `config/styles/*.json`, each carrying:

| Field | Purpose |
|---|---|
| `slug` | Canonical ID (e.g. `warm-editorial-minimalist`) |
| `name` | Display name |
| `description` | One-paragraph summary |
| `magic_media_keywords` | The full keyword block injected into the Generator's system prompt |
| `required_keywords` | 3–5 substrings code-enforced in `magic_media_prompt` by `validate_style_compliance()` |
| `palette_hint` | Color direction guidance (with sample HEX) |
| `recommended_magic_media_style` | e.g. `"Minimalist"`, `"Photographic"` |
| `best_for` | One-sentence use-case for auto-selection |
| `negative_prompt_boost` | (Optional) Preset-specific exclusions |

### 3.1 Full Preset Catalog

| Slug | Required Keywords | Best For |
|---|---|---|
| `art-deco-metropolis` | art deco, sunburst, stepped chevron, brushed brass | luxury gala invitations, hotel branding, Gatsby-era glamour |
| `art-nouveau-botanical` | art nouveau lithograph, whiplash curve, botanical ornament, stained-glass leadline | organic skincare, floral boutique branding, garden-event promos |
| `bauhaus-modernist-poster` | bauhaus geometric layout, primary-color, diagonal bars, modernist print aesthetic | art-school exhibitions, architecture firm branding |
| `brutalist-concrete` | brutalist architecture, polished concrete, hard directional midday sun, architectural wide-angle | architecture portfolios, industrial-design showcases |
| `constructivist-agitprop` | constructivist agitprop, diagonal composition, photomontage, wedge | political campaign graphics, protest-art posters |
| `corporate-dynamic-vector` | modern corporate aesthetic, 3D vector wave elements, softbox lighting, highly isolated subject | tech launches, SaaS products, professional presentations |
| `dutch-golden-age-still-life` | dutch golden age still life, chiaroscuro, raw linen weave, hand-thrown ceramic | premium food photography, luxury tabletop product shots |
| `formal-ceremonial-turkish` | formal ceremonial, fabric banners rippling, golden-hour rim light, low-angle heroic | formal invitations, awards ceremonies, diplomatic events |
| `holographic-glassmorphism` | holographic fluid background, iridescent, glassmorphism, layered depth | futurist app UIs, Web3/crypto branding |
| `kodachrome-americana` | Kodachrome color documentary, analog film grain, golden-hour rim light, long shadows | travel editorials, nostalgic brand campaigns |
| `memphis-design-pop` | memphis design, squiggle, terrazzo speckle, black-and-white stripe | 1980s-retro parties, kids-brand launches |
| `mid-century-modern-print` | mid-century modern, atomic starburst, screenprint grain, boomerang | furniture showroom promos, retro cocktail-bar posters |
| `neo-grunge-streetwear` | distressed grunge texture, high contrast monochromatic, neon, negative space | streetwear drops, underground music gigs |
| `psychedelic-fillmore` | psychedelic concert poster, swirling liquid, vibrating orange and violet, optical ripple | music-festival lineups, vinyl-album art |
| `riso-print-editorial` | risograph print texture, ink misregistration, halftone dot, soy ink | zine covers, indie magazine spreads |
| `streamer-energetic-glitch` | streamer glitch, rgb channel-split, cutout isolated portrait, glitch echo | Twitch/YouTube overlays, gaming/esports |
| `swiss-international-grid` | swiss international typographic style, mathematical grid, flat solid color fields, structured white space | corporate annual reports, editorial layouts |
| `ukiyo-e-woodblock` | ukiyo-e woodblock, keyblock outlines, bokashi gradient, washi paper grain | Japanese cuisine menus, tea-ceremony branding |
| `utility-planner-ornamental` | utility planner layout, planner grid itself is the isolated hero subject, geometric arabesque ornamental border, empty ruled cells | bullet-journal spreads, printable planners |
| `vaporwave-arcade-dusk` | vaporwave, neon wireframe grid, vhs scanline, dusk gradient | synthwave playlists, retro-gaming events |
| `warm-editorial-minimalist` | warm editorial minimalist, thin-line ornamental border, aged terracotta, cream paper texture | calm travel carousels, lifestyle-blog branding |
| `y2k-chrome-gloss` | y2k, liquid chrome, frosted glass, gradient mesh | Gen-Z fashion drops, early-2000s nostalgia |

### 3.2 Brand ↔ Style Override Hierarchy

When **both** brand and style are active (`generator.py:84-120`, `style_presets.py:78-129`, `brand_profiles.py:82-108`):

```
STYLE WINS ON:
  ✓ Image aesthetic direction
  ✓ Mood, lighting warmth
  ✓ Material/texture cues
  ✓ Photographic/illustrative register
  → magic_media_prompt MUST open with style's keywords verbatim

BRAND WINS ON:
  ✓ Fonts (headline_font, body_font) — exact match enforced
  ✓ Color palette — must be subset of approved_colors
  ✓ Logo placement zone — text_zone avoids it

Brand's visual_identity block is STRIPPED from the system prompt entirely
when style is active (brand_profiles.py:96-97 pops the key).
```

Code-level enforcement (`schema.py:206-243`):
- `validate_brand_compliance()`: exact font name match + approved color membership
- `validate_style_compliance()`: `required_keywords` substring match in `magic_media_prompt`

### 3.3 Auto-Style Selection

1. No manual style → Architect's system prompt includes `best_for_summaries()` output (22-line bullet list, `architect.py:84-92`)
2. Architect picks ONE slug → writes into `selected_style_id` in brief
3. Orchestrator loads that slug (`orchestrator.py:100-107`) — silently continues without style if slug is invalid
4. Manual style → Architect confirms the given slug, no menu shown (`_style_selection_rule()`, `architect.py:47-66`)

---

## 4. AESTHETIC TAXONOMY

From `design_rules.json:95-106`. The constitution mandates upgrading every generic adjective to precise professional design taxonomy.

### 4.1 Lexicons (verbatim)

**Material/Texture Lexicon:**
```
matte porcelain, warm oak wood grain, brushed brass, hand-thrown ceramic,
raw linen weave, polished concrete, aged terracotta, frosted glass,
soft velvet nap, brushed aluminium
```

**Light Quality Lexicon:**
```
soft natural morning window light, golden-hour rim light, diffused overcast light,
hard directional midday sun, warm practical tungsten glow, cool blue-hour ambient,
studio softbox key with gentle fill
```

**Register Lexicon:**
```
high-end editorial photography, product hero shot, architectural wide-angle,
macro detail study, flat-lay overhead, cinematic still,
clean flat-vector illustration, isometric 3d render
```

### 4.2 Upgrade Examples

| Generic | Upgraded |
|---|---|
| "cozy coffee shop" | "minimalist Scandinavian aesthetic, warm oak wood textures, soft natural morning window light, high-end editorial photography, matte porcelain details" |
| "modern office" | "clean corporate interior, brushed matte-aluminium and warm walnut surfaces, floor-to-ceiling diffused daylight, wide-angle architectural photography, muted desaturated palette" |
| "beautiful flowers" | "editorial floral still life, dewy garden roses and eucalyptus, soft diffused overcast light, macro 100mm shallow depth of field, painterly muted tones" |

### 4.3 Enforcement

The Reviewer judges this under `magic_media_prompt_quality` (weight 0.18). A prompt still leaning on bare generic adjectives is scored down. There is no code-level taxonomy-usage check (it's a qualitative LLM judgment, not a deterministic string match like `required_keywords`).

---

## 5. GOLDEN DATASET / FEW-SHOT MEMORY

**File:** `data/golden_cards.jsonl` → loaded at import time by `src/golden_cards.py`

### 5.1 Structure

- **44 records** total (2 per style preset × 22 styles)
- Each record is one JSON line: `{style_id, brief, card_json, score, rubric_breakdown}`
- **2 brief archetypes per style:**
  - A **launch/post archetype** (e.g. "Route-launch carousel cover for Sander & Fog")
  - A **story/carousel archetype** (e.g. "Day-one carousel for Sander & Fog: '72 hours in Lisbon'")
- All 44 briefs are distinct (no reuse across styles)
- All scores ≥ 9.0

### 5.2 Loading & Indexing (`golden_cards.py:30-50`)

```python
_index: dict[str, list[dict[str, Any]]]  # style_id → [card1, card2, ...]
```
- Parsed once at module import, kept in memory
- Missing/empty file → empty dict (no crash)
- Corrupt JSON line → silently skipped
- Multiple cards per style → stored as list (no silent shadowing)

### 5.3 Few-Shot Injection (`golden_cards.py:78-103`)

`as_few_shot_block(style_id)`:
1. Calls `get_golden_card(style_id)` → returns the single **highest-scored** card via `_best()`
2. On tie, earliest line in file wins (Python `max()` stability)
3. **Silently returns `""`** if no golden card exists for the style (new/unscored preset)
4. Renders a compact block: score + brief + full `card_json` (pretty-printed)

**Injection point:** `generator.py:91` — after the style prompt block, only when a style is active:

```python
golden_block = as_few_shot_block(style["slug"])
if golden_block:
    style_section += golden_block
```

### 5.4 Token/Quality Trade-off

Only ONE golden card per style is injected (the best-scored one via `get_golden_card()`) rather than all two. Rationale from `golden_cards.py:67-71`: "roughly half the token cost for no measured quality loss."

---

## 6. UNIFIED DESIGN BRIEF / DIRECT ACTION TIP

**Version:** 3.2.0 (design_rules.json) | **Implemented in:** `src/generator.py`, `src/paste_render.py`

### 6.1 Two-Tier Format

`direct_action_tip` is a 3–5 element array:

| Entry | Label | Content |
|---|---|---|
| **Step 1** | `PRIMARY (AI-Assistant Holistic Generation):` | Unified block listing ALL design parameters inline: `magic_media_prompt`, `headline`, `subtext`, `color_palette`, `fonts`, `aspect_ratio`, `background_layers` → meant to be fed to a Canva-connected AI assistant for single-pass holistic generation |
| **Steps 2–5** | `ALTERNATIVE (Manual Magic Media):` | Classic step-by-step Canva UI instructions: open Magic Media, paste prompt, generate, add text boxes, apply fonts, recolor |

### 6.2 Paste Renderer (`paste_render.py:30`)

`render_for_assistant_paste(card)` outputs a copy-paste-ready text block:

```
Using your connected Canva tool, generate this design now at {aspect_ratio}...

UNIFIED DESIGN BRIEF:
  Visual direction: {magic_media_prompt}
  Negative prompt: {negative_prompt}
  Headline (this is the visible title text on the design): {headline}
  Subtext (this is the visible supporting text on the design): {subtext}
  Color palette (typography styling only — apply these HEX codes as fill/stroke
    colors; do NOT render the codes as visible text): {palette}
  Fonts (typography styling only — apply these as the font family for the
    headline/subtext layers; do NOT render the font names as visible text on
    the design): {headline_font} / {body_font}
  Format: {aspect_ratio}
  Target tool: {target_tool}
  Composition: {background_layers}
  Text zone: {text_zone}
  Magic Media style: {magic_media_style}

Alternative — manual Canva steps:
  1. {direct_action_tip[0]}  ← PRIMARY
  2. {direct_action_tip[1]}  ← ALTERNATIVE
  ...
```

Styling-only disclaimers on Fonts/Color Palette lines prevent AI tools from rendering font names and HEX codes as visible text (a confirmed bug fix from real-world testing, commit `d3ce429`).

---

## 7. TEST COVERAGE MAP

**Total:** 195 backend tests (pytest) + 7 frontend tests (vitest) across 16 files.

### 7.1 Backend Test Files

| File | Tests | Focus |
|---|---|---|
| `test_api.py` | 13 | FastAPI endpoints: `/health`, `/api/chat`, `/api/adapt`, error handling, paste_text format |
| `test_architect.py` | 9 | Brief structure, category detection, auto-style selection, brand constraints |
| `test_brand_profiles.py` | 14 | Loader, approved colors, visual_identity rendering, exclude_visual_identity, custom directory |
| `test_canva_rules.py` | 4 | CATEGORY_HINTS (including Turkish keywords), dimensions lookup |
| `test_color_science.py` | 13 | WCAG contrast math, hue distance, clashing pair detection, HEX parsing edge cases |
| `test_composition_rules.py` | 20 | 4 format families × 5 text_zones, aspect_family normalization |
| `test_generator.py` | 25 | Card parsing, markdown-fence stripping, brand/style injection, feedback injection, golden card injection, **no Anthropic import** invariant, DEFAULT_CLIENT uses DeepSeek |
| `test_golden_cards.py` | 11 | 2 cards per style, score ≥9.0, best-of tie-breaking, as_few_shot_block injection, silent skip for unknown style, field validation |
| `test_http_client.py` | 4 | Pure-httpx DeepSeekClient fallback |
| `test_omni_channel.py` | 12 | Story/carousel adaptation, format mapping, chat-phrase scanning |
| `test_orchestrator.py` | 10 | Pipeline success/failure, auto-style resolution, max_attempts exhaustion, brand+style together |
| `test_paste_render.py` | 6 | Unified brief format, anti-injection guard (no SYSTEM/OVERRIDE), font/palette styling disclaimers, numbered steps |
| `test_reviewer.py` | 6 | Score extraction, pass threshold, criteria breakdown, feedback on failure |
| `test_schema.py` | 25 | All 7 validation gates: JSON schema shape, forbidden phrases, headline/subtext word count, WCAG contrast, text_zone consistency, brand compliance, style compliance |
| `test_style_presets.py` | 21 | 22 expected slugs, required_keywords present in magic_media_keywords, wave segmentation (wave2: 12, wave3: 4), aesthetic_taxonomy lexicon usage, palette_hint contrast ≥4.5, override_brand directive, best_for existence for every preset |

### 7.2 Frontend Test File

| File | Tests | Focus |
|---|---|---|
| `components/ChatInput.test.tsx` | 7 | Ghost text rendering, right-arrow suggestion acceptance, input-filled guard, hide-when-no-suggestion, Enter/ArrowUp regression, aria-hidden accessibility |

### 7.3 Key Invariants Protected

| Invariant | Where Enforced |
|---|---|
| No Anthropic import anywhere in the pipeline | `test_generator.py:127` — `test_generator_module_has_no_anthropic_import()` |
| DeepSeek is the ONLY LLM engine | `test_generator.py:105` — `test_default_client_uses_deepseek...()` |
| All 22 presets have ≥2 required_keywords | `test_style_presets.py:83` |
| All presets reference aesthetic_taxonomy lexicon | `test_style_presets.py:161` |
| All presets have best_for ≥10 chars | `test_style_presets.py:317` |
| All presets have contrastable palette_hint | `test_style_presets.py:270` |
| Every style has exactly 2 golden cards | `test_golden_cards.py:59` |
| Golden cards all score ≥9.0 | `test_golden_cards.py:66` |
| Paste render never impersonates system/override | `test_paste_render.py:13` |
| Font/palette lines warn "do NOT render as visible text" | `test_paste_render.py:55` |
| Ghost text has `aria-hidden="true"` | `ChatInput.test.tsx:37` |
| Hydration: SSR uses deterministic suggestion | `page.tsx:22` — `useState(SUGGESTIONS[0])` |

---

## 8. KNOWN WEAKNESSES / LIMITATIONS

### 8.1 `utility-planner-ornamental` — Decoration Bleed Risk

This preset's defining feature (ornamental borders, ruled grids, arabesque geometry) naturally fills the canvas. It is the ONLY preset with a `negative_prompt_boost` field (`"pseudo-text, fake letters, fake numerals, gibberish glyphs, handwriting marks, filled-in cells"`) and explicit zone-protection language in its `magic_media_keywords`: `"no pseudo-text, no numerals and no handwriting marks must encroach into the reserved text zone"`. Despite these guards, it consistently scored lowest among all presets during the golden-card batch generation — the decorative density is in fundamental tension with the "clean negative space for typography" requirement.

### 8.2 Golden Dataset — Self-Review Bias

All 44 golden cards were produced by the SAME pipeline that the Generator is part of — they are self-scored (same DeepSeek model as Generator and Reviewer). There is no independent human evaluation or external Canva-tool verification. The few-shot injection may therefore reinforce any systematic blind spots the pipeline has rather than correcting them. Mitigation: scores ≥9.0 were used as the inclusion threshold (high bar), and the rubric's deterministic gates (contrast, typos, forbidden phrases) provide a hard floor.

### 8.3 Real-World Validation Coverage

As of 2026-07-22, only `warm-editorial-minimalist` has been tested end-to-end by pasting the UNIFIED DESIGN BRIEF into a Canva-connected AI assistant (Claude). The paste-to-chat renderer changed the game — results were significantly stronger than the previous Magic Media step-by-step flow — but only ONE preset has been verified this way. The other 21 presets' real-world Canva output quality is inferred from the rubric scores, not from actual Canva generation.

### 8.4 Single-Engine Architecture Risk

All three stages run on `deepseek-chat`. If DeepSeek has a systemic weakness (e.g., tends to produce similar color palettes regardless of style palette_hint, or overuses certain composition patterns), there is no cross-model check to catch it. The pipeline was designed this way intentionally (cost/simplicity/offline capability on Termux), but it means reviews are inherently limited by what the reviewing model can notice.

### 8.5 No Visual Regression Testing

The system validates cards at the text/JSON level only. There is no image output, no screenshot comparison, and no Canva API integration to verify that a generated card actually produces a good-looking design in Canva's renderer. The contrast math (`color_science.py`) catches objective color failures, but subjective visual quality is entirely a matter of LLM judgment.

### 8.6 Category Detection Limitations

`detect_category()` (`canva_rules.py:90`) uses simple substring matching against 25 keyword→category pairs. It covers Turkish and English variants for common formats, but misses many real-world requests. An Architect may override the hint, but if the hint is wrong AND the Architect follows it, the wrong aspect ratio is baked into the brief.

### 8.7 Golden Card Token Cost (Per-Call)

Every Generator call for a styled request includes the full golden card JSON in its system prompt (the highest-scored one). At roughly 1,500–2,000 tokens per golden card, this adds ~3,000–4,000 prompt tokens to every styled generation. For the 22-preset coverage, this is acceptable. If the preset library grows to 50+, the few-shot strategy should be revisited (currently one card = manageable).

---

## Appendix A: File Map

```
CanvaDesignAI/
├── design_rules.json              # Constitution v3.2.0 — single source of truth
├── api.py                         # FastAPI backend (port 8000)
├── main.py                        # CLI entrypoint
│
├── src/
│   ├── orchestrator.py            # 3-stage flow + retry logic
│   ├── architect.py               # Stage 1: user → design brief
│   ├── generator.py               # Stage 2: brief → Canva card
│   ├── reviewer.py                # Stage 3: card → score + feedback
│   ├── schema.py                  # JSON schema + 7 code-level validations
│   ├── constitution.py            # Loads design_rules.json (LRU-cached)
│   ├── canva_rules.py             # Knowledge base (dimensions, styles, keywords)
│   ├── composition_rules.py       # Format-specific composition (4 families × 5 zones)
│   ├── style_presets.py           # Style preset loader + as_prompt_block
│   ├── brand_profiles.py          # Brand profile loader
│   ├── golden_cards.py            # Few-shot golden card store (import-time load)
│   ├── color_science.py           # WCAG contrast + hue-clash math
│   ├── llm_json.py                # JSON extraction (markdown fence stripping)
│   ├── http_client.py             # Pure-httpx DeepSeek fallback
│   └── paste_render.py            # Unified design brief renderer
│
├── config/
│   ├── styles/ (*.json × 22)      # Style presets
│   └── brands/ (*.json)           # Brand profiles
│
├── data/
│   └── golden_cards.jsonl         # 44 scored reference cards (import-time load)
│
├── tests/ (15 files, 195 tests)   # pytest test suite
│
└── web/                           # Next.js 16 frontend
    ├── app/page.tsx               # Main page + state management
    ├── components/
    │   ├── ChatInput.tsx          # Ghost-text autosuggestion input
    │   ├── ChatInput.test.tsx     # 7 vitest tests
    │   ├── ChatPromptCard.tsx     # Card rendering + copy + wireframe
    │   ├── BrandSelect.tsx        # Brand slug pill selector
    │   └── StyleSelect.tsx        # Style slug pill selector
    ├── lib/
    │   ├── types.ts               # All TypeScript types
    │   └── suggestions.ts         # 10 curated ghost-text prompts
    ├── vitest.config.ts
    └── test-setup.ts
```

## Appendix B: Technology Stack

| Layer | Technology |
|---|---|
| LLM Engine | `deepseek-chat` (single model for all 3 stages) |
| API Protocol | OpenAI-compatible completions |
| HTTP Client | `openai` SDK (primary) / `src/http_client.py` (pure-httpx fallback) |
| Backend | FastAPI + Uvicorn (Python 3.14) |
| Frontend | Next.js 16 + React 19 + Tailwind CSS 3 |
| Backend Tests | pytest (195 tests) |
| Frontend Tests | vitest + @testing-library/react (7 tests) |
| Schema Validation | jsonschema (draft 2020-12) |
| Color Math | WCAG 2.1 relative luminance + contrast |
| Runtime | Android/Termux (primary dev environment) |
