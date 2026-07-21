# CaVDesign — Canva Design Agency Engine

A chat-driven **Canva design agency engine**, not a chat assistant. You type
a plain idea — `"Kafe açılışı için Instagram gönderisi"` — and a
single-engine DeepSeek pipeline hands back one machine-consumable **Canva
card**: no chat, no clarifying questions, no prose — just the data needed to
build the design in Canva as fast as possible.

It's for people who already have Canva Pro or ChatGPT Pro but can't reliably
get consistent, designer-grade results out of them. **Cards only** — this
project never generates images or logs into Canva on your behalf. The
engine reasons like an Art Director, not just a prompt writer: real WCAG
color contrast, a real typographic hierarchy, and a single canonical
placement decision (`text_zone`) that the image and the text layer are both
held to — all enforced at the code level, not just described in a prompt.

## Single-engine architecture (DeepSeek)

```
[ Chat UI (CaVDesign, Next.js) ]
        │  "Kafe açılışı için Instagram gönderisi"
        ▼
[ DeepSeek — Architect / Canva expert ]   src/architect.py
        │  detects category + dimensions, picks ONE text_zone, locks
        │  art direction & negative space around it
        ▼
[ DeepSeek — Generator / Prompt Engineer ] src/generator.py
        │  writes the Canva card's 3 mandatory components, honoring
        │  the brief's text_zone in both the image prompt and the
        │  typography layer
        ▼
[ DeepSeek — Reviewer ]                    src/reviewer.py
        │  scores it; if < 8.5, OR any chat language / contrast /
        │  hierarchy / zone-consistency check fails, retries the
        │  Generator with feedback (up to max_attempts)
        ▼
[ Chat UI — Canva Card ]  (wireframe + contrast readout + one-click copy)
```

Every stage runs on DeepSeek (`DEEPSEEK_API_KEY` only — no other LLM key is
required by the pipeline; `src/http_client.py` provides a pure-httpx
fallback for platforms — e.g. Android/Termux — where the `openai` SDK's
`jiter` C-extension dependency won't compile).

- **`src/canva_rules.py`** — the Canva knowledge base: canvas dimensions,
  Magic Media styles, and the element/library keywords Canva's algorithms
  understand best. All three stages share it as one source of truth.
- **`design_rules.json`** — the Canva Automation Constitution: the
  `output_contract` (mandatory 3 components, forbidden chat phrases),
  Art Director rules (medium/composition/lighting/color/typography, the
  numeric `min_contrast_ratio`, the `text_zone` placement rule), and the
  review rubric (8.5 pass threshold).
- **`src/color_science.py`** — real WCAG contrast-ratio and hue-distance
  math (pure Python, no dependency) backing the color theory rules.
- **`src/composition_rules.py`** — format-specific composition, lighting and
  depth recipes plus precise per-`text_zone` negative-space language, keyed
  by aspect-ratio family (9:16 vertical / 1:1 square / 16:9 horizontal / 4:5
  portrait). Injected deterministically into the Generator and Omni-Channel
  system prompts so each design is composed *for* its exact canvas (e.g. a
  9:16 story gets vertical leading lines + "reserve the upper 40% as a clean
  minimalist band for the overlay"; a 16:9 banner gets rule-of-thirds offset
  + panoramic depth) rather than relying on the LLM to reinvent it per call.
- **`src/schema.py`** — validates the card's shape AND runs several
  **code-level** Art Director checks, independent of whether the LLM
  follows its system prompt: a ban on conversational filler ("I can
  generate...", "would you like...", etc.), a WCAG contrast-ratio floor
  (≥ 4.5:1 within `color_palette`), headline/subtext length limits, and
  `text_zone` consistency between the image prompt and the typography layer.
- **`src/orchestrator.py`** — runs Architect → Generator → Reviewer, retrying
  the Generator on either a low Reviewer score or any of the schema/Art
  Director validation failures, up to `max_attempts`. Raises `PipelineError`
  if no attempt ever produces a valid card.
- **`api.py`** — FastAPI `POST /api/chat` that runs the pipeline.
- **`web/`** — the CaVDesign Next.js chat UI (terminal aesthetic).

## Canva card (output shape)

Exactly three mandatory components — `magic_media_prompt`,
`layer_typography_architecture`, `direct_action_tip` — anchored to one
canonical `text_zone`, plus routing fields:

```json
{
  "concept": "Grand Opening Cafe",
  "magic_media_prompt": "A minimalist 3d flat vector illustration for a specialty coffee shop grand opening, earthy terracotta and warm cream color palette, top-down view of an espresso cup next to an open notebook, ample negative space at the top for overlaying text in Canva, vintage aesthetic, clean lines, isolated on a plain background.",
  "negative_prompt": "embedded text, watermark, logo, cluttered composition, ...",
  "aspect_ratio": "1:1 (1080x1080)",
  "target_tool": "Canva Magic Media",
  "text_zone": "top",
  "layer_typography_architecture": {
    "headline": "Grand Opening",
    "subtext": "Freshly roasted, every morning.",
    "color_palette": ["#4A2E1B", "#D4A373", "#F5EFE6"],
    "fonts": { "headline_font": "Montserrat Bold", "body_font": "Playfair Display" },
    "background_layers": "generated image fills the bottom 60%; solid cream rectangle layer behind the top 40% carries the headline/subtext",
    "magic_media_style": "Flat Vector"
  },
  "direct_action_tip": [
    "Open Canva > Apps > Magic Media, paste magic_media_prompt, generate at 1:1 (1080x1080).",
    "Add a Heading text box in the empty top space and type the headline.",
    "Set Text > Font to the headline_font/body_font pairing.",
    "Recolor accents using the color_palette HEX codes via the color picker."
  ],
  "canva_keywords": ["flat vector illustration", "isolated element on transparent background"]
}
```

`text_zone` (`top`/`bottom`/`left`/`right`/`center`) is decided once by the
Architect and must be referenced by both `magic_media_prompt`'s negative
space and `background_layers` — `src/schema.py` rejects a card where they
disagree. `color_palette` must contain a pair with a WCAG contrast ratio
≥ 4.5:1 (simulating headline text over its background). Field names map
1:1 onto the `ChatPromptCard` UI component, which also renders a monochrome
ASCII wireframe of `text_zone` and a plain-text contrast readout. See
[`examples/grand_opening_cafe.json`](examples/grand_opening_cafe.json).

## Design Agency: Brand Profiles, Critic, Omni-Channel

**Brand Profiles** (`config/brands/<slug>.json`, loaded by
`src/brand_profiles.py`) lock a design to one brand's exact signature fonts
and approved colors instead of the generic Art Director defaults. Pass
`--brand <slug>` (CLI) or `brand` (API/UI); every stage — Architect,
Generator, Reviewer — is constrained to that profile, and `src/schema.py`
**hard-rejects** (retried, same as contrast/text_zone) a card using the
wrong font or an unapproved color. A profile's optional `visual_identity`
block (mood, `lighting_warmth`, `texture_cues`, `photographic_style`) goes
one level deeper: it's rendered as explicit steering that must be embedded
into `magic_media_prompt` itself, so the **generated image** reads on-brand
(warm oak textures, morning window light, editorial register) — not just
the typography overlay. See
[`config/brands/example-cafe.json`](config/brands/example-cafe.json).

**Critic = the existing Reviewer, extended — not a new stage.** Rather than
add a separate fourth LLM call, `design_rules.json`'s rubric gained a
`brand_fit` criterion that the same Reviewer call already scores (zero
extra latency/cost); the factual parts of brand compliance (exact font/color
match) are enforced deterministically in code, so the LLM only judges what's
genuinely subjective — does it *feel* on-brand.

**Omni-Channel** (`src/omni_channel.py`) adapts an *already-approved* card to
other formats (`instagram_post`, `instagram_story`, `banner`) on demand — not
automatically, and not by re-running the full pipeline. One small "Adapter"
DeepSeek call holds the concept/headline/subtext/palette/fonts fixed and
only re-derives `text_zone`, `magic_media_prompt`'s composition,
`background_layers`, and `direct_action_tip` for the new aspect ratio; the
result passes through the same `validate_prompt` as everything else. In the
UI, each card gets `[ story ] [ post ] [ banner ]` buttons that append the
adapted variant as a new terminal-log entry.

```bash
python main.py "Grand Opening Cafe" --brand example-cafe
python main.py "Grand Opening Cafe" --adapt-to instagram_story,banner
```

## Pasting into a Claude/ChatGPT chat with Canva connected

`src/paste_render.py` renders the card as a plain-text block — a direct,
first-person instruction ("use your connected Canva tool now, don't ask me
clarifying questions") followed by the full card — so pasting it into a
Claude/ChatGPT conversation that has a Canva tool connected maximizes the
odds that assistant proceeds immediately instead of asking for details.

**What this is not:** there's no way to make pasted text carry system-level
authority or force a tool call — that's always ordinary user content to the
receiving assistant, and wording tricks like fake `SYSTEM:`/`OVERRIDE:` tags
don't change that (and are the classic prompt-injection pattern, which
production assistants are hardened against). This only writes a clear,
honest, direct request — the same thing that makes any instruction more
likely to be followed.

```bash
python main.py "Grand Opening Cafe" --paste   # prints the paste-ready block
```

The FastAPI response and the chat UI's card also carry this as `paste_text`,
with its own "copy for Claude / ChatGPT chat" button.

## Run

```bash
# Backend engine
pip install -r requirements.txt
cp .env.example .env          # DEEPSEEK_API_KEY (only key needed)
uvicorn api:app --port 8000

# CLI (no server needed)
python main.py "Grand Opening Cafe"
python main.py "Grand Opening Cafe" --raw    # just the magic_media_prompt string
python main.py "Grand Opening Cafe" --paste  # paste-ready block for a Canva-connected chat

# Frontend (separate terminal)
cd web && cp .env.example .env.local && npm install && npm run dev
```

## Development

```bash
pip install -r requirements.txt pytest
pytest                        # 132 tests, fully offline (mocked DeepSeek/HTTP)

cd web && npm run typecheck && npm run build
```

All API calls sit behind injectable clients, so the Python suite runs fully
offline against mocked DeepSeek responses and a mocked pipeline for the
FastAPI endpoint.
