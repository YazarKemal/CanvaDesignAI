# CaVDesign — Canva Prompt Workbench

A chat-driven **prompt engine** that knows Canva's visual language cold. You
type a plain idea — `"Kafe açılışı için Instagram gönderisi"` — and a
three-agent pipeline hands back a copy-paste-ready image prompt tuned for
**Canva Magic Media / Canva GPT / DALL·E 3**, with the right canvas size,
art direction, and deliberate negative space for your text.

It's for people who already have Canva Pro or ChatGPT Pro but can't reliably
get consistent, designer-grade results out of them. **Prompts only** — this
project never generates images or logs into Canva.

## Architecture

```
[ Chat UI (CaVDesign, Next.js) ]
        │  "Kafe açılışı için Instagram gönderisi"
        ▼
[ DeepSeek — Architect / Canva expert ]   src/architect.py
        │  detects category + dimensions, locks art direction & negative space
        ▼
[ Claude — Prompt Engineer ]              src/generator.py
        │  writes the copy-paste-ready prompt card
        ▼
[ DeepSeek — Reviewer ]                    src/reviewer.py
        │  scores it; if < 8.5, feedback goes back to the Generator to revise
        ▼
[ Chat UI — Prompt Card ]  (one-click copy + parameters)
```

- **`src/canva_rules.py`** — the Canva knowledge base: canvas dimensions,
  Magic Media styles, and the element/library keywords Canva's algorithms
  understand best. Both agents share it as one source of truth.
- **`design_rules.json`** — the Art Director Constitution (prompt structure,
  photography/composition/lighting/color rules, and the review rubric with an
  **8.5** pass threshold).
- **`src/orchestrator.py`** — runs Architect → Generator → Reviewer, looping
  on feedback up to `max_attempts` and returning the best-scoring card.
- **`api.py`** — FastAPI `POST /api/chat` that runs the pipeline.
- **`web/`** — the CaVDesign Next.js chat UI (terminal aesthetic).

## Prompt card (output shape)

```json
{
  "concept": "Grand Opening Cafe",
  "prompt_text": "A minimalist 3d flat vector illustration for a specialty coffee shop grand opening, earthy terracotta and warm cream color palette, top-down view of an espresso cup next to an open notebook, ample negative space at the top for overlaying text in Canva, vintage aesthetic, clean lines, isolated on a plain background.",
  "negative_prompt": "embedded text, watermark, logo, cluttered composition, ...",
  "aspect_ratio": "1:1 (1080x1080)",
  "target_tool": "Canva Magic Media",
  "canva_tip": "Paste into Magic Media, then drop your headline into the empty top third.",
  "art_direction": {
    "color_palette": ["terracotta", "warm cream", "espresso brown"],
    "lighting": "soft natural daylight",
    "mood": "minimalist, vintage, artisanal",
    "magic_media_style": "Flat Vector"
  },
  "canva_keywords": ["flat vector illustration", "isolated element on transparent background"]
}
```

The field names map 1:1 onto the `ChatPromptCard` UI component. See
[`examples/grand_opening_cafe.json`](examples/grand_opening_cafe.json).

## Run

```bash
# Backend engine
pip install -r requirements.txt
cp .env.example .env          # ANTHROPIC_API_KEY + DEEPSEEK_API_KEY
uvicorn api:app --port 8000

# CLI (no server needed)
python main.py "Grand Opening Cafe"
python main.py "Grand Opening Cafe" --raw   # just the prompt string

# Frontend (separate terminal)
cd web && cp .env.example .env.local && npm install && npm run dev
```

## Development

```bash
pip install -r requirements.txt pytest
pytest                        # 25 tests, fully offline (mocked LLM/HTTP)

cd web && npm run typecheck && npm run build
```

All API calls sit behind injectable clients, so the Python suite runs fully
offline against mocked Anthropic/DeepSeek responses and a mocked pipeline for
the FastAPI endpoint.
