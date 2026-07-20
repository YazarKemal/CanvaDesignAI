# CaVDesign — Canva Automation Engine

A chat-driven **Canva automation engine**, not a chat assistant. You type a
plain idea — `"Kafe açılışı için Instagram gönderisi"` — and a single-engine
DeepSeek pipeline hands back one machine-consumable **Canva card**: no chat,
no clarifying questions, no prose — just the data needed to build the design
in Canva as fast as possible.

It's for people who already have Canva Pro or ChatGPT Pro but can't reliably
get consistent, designer-grade results out of them. **Cards only** — this
project never generates images or logs into Canva on your behalf.

## Single-engine architecture (DeepSeek)

```
[ Chat UI (CaVDesign, Next.js) ]
        │  "Kafe açılışı için Instagram gönderisi"
        ▼
[ DeepSeek — Architect / Canva expert ]   src/architect.py
        │  detects category + dimensions, locks art direction & negative space
        ▼
[ DeepSeek — Generator / Prompt Engineer ] src/generator.py
        │  writes the Canva card's 3 mandatory components
        ▼
[ DeepSeek — Reviewer ]                    src/reviewer.py
        │  scores it; if < 8.5 OR any chat language is found, retries the
        │  Generator with feedback (up to max_attempts)
        ▼
[ Chat UI — Canva Card ]  (one-click copy + parameters, terminal log)
```

Every stage runs on DeepSeek (`DEEPSEEK_API_KEY` only — no other LLM key is
required by the pipeline).

- **`src/canva_rules.py`** — the Canva knowledge base: canvas dimensions,
  Magic Media styles, and the element/library keywords Canva's algorithms
  understand best. All three stages share it as one source of truth.
- **`design_rules.json`** — the Canva Automation Constitution: the
  `output_contract` (mandatory 3 components, forbidden chat phrases),
  prompt-engineering rules (medium/composition/lighting/color/typography),
  and the review rubric (8.5 pass threshold).
- **`src/schema.py`** — validates the card's shape AND runs a **code-level**
  ban on conversational filler ("I can generate...", "would you like...",
  etc.) — enforced independent of whether the LLM follows its system prompt.
- **`src/orchestrator.py`** — runs Architect → Generator → Reviewer, retrying
  the Generator on either a low Reviewer score or a schema/forbidden-phrase
  validation failure, up to `max_attempts`. Raises `PipelineError` if no
  attempt ever produces a valid card.
- **`api.py`** — FastAPI `POST /api/chat` that runs the pipeline.
- **`web/`** — the CaVDesign Next.js chat UI (terminal aesthetic).

## Canva card (output shape)

Exactly three mandatory components — `magic_media_prompt`,
`layer_typography_architecture`, `direct_action_tip` — plus routing fields:

```json
{
  "concept": "Grand Opening Cafe",
  "magic_media_prompt": "A minimalist 3d flat vector illustration for a specialty coffee shop grand opening, earthy terracotta and warm cream color palette, top-down view of an espresso cup next to an open notebook, ample negative space at the top for overlaying text in Canva, vintage aesthetic, clean lines, isolated on a plain background.",
  "negative_prompt": "embedded text, watermark, logo, cluttered composition, ...",
  "aspect_ratio": "1:1 (1080x1080)",
  "target_tool": "Canva Magic Media",
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

Field names map 1:1 onto the `ChatPromptCard` UI component. See
[`examples/grand_opening_cafe.json`](examples/grand_opening_cafe.json).

## Run

```bash
# Backend engine
pip install -r requirements.txt
cp .env.example .env          # DEEPSEEK_API_KEY (only key needed)
uvicorn api:app --port 8000

# CLI (no server needed)
python main.py "Grand Opening Cafe"
python main.py "Grand Opening Cafe" --raw   # just the magic_media_prompt string

# Frontend (separate terminal)
cd web && cp .env.example .env.local && npm install && npm run dev
```

## Development

```bash
pip install -r requirements.txt pytest
pytest                        # 40 tests, fully offline (mocked DeepSeek/HTTP)

cd web && npm run typecheck && npm run build
```

All API calls sit behind injectable clients, so the Python suite runs fully
offline against mocked DeepSeek responses and a mocked pipeline for the
FastAPI endpoint.
