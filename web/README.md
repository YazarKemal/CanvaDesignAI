# CaVDesign — web

The Next.js chat UI for the Canva Prompt Workbench. Pure terminal aesthetic:
black background, monospace everywhere, grayscale only.

- `app/page.tsx` — the CAVDESIGN screen: header, centered input, and the
  top-to-bottom terminal log of generated prompt cards.
- `components/ChatInput.tsx` — the single-line bordered input with the
  `Describe a design` label, `>` cursor, and `generate` button.
- `components/ChatPromptCard.tsx` — one left-bordered terminal log entry:
  parameters, a monochrome ASCII wireframe of `text_zone`, the prompt with a
  one-click copy button, a plain-text contrast readout, and a "copy for
  Claude / ChatGPT chat" button.
- `app/api/chat/route.ts` — proxies to the Python FastAPI engine (`api.py`).

## Run

```bash
# 1. Start the Python engine (from the repo root):
uvicorn api:app --port 8000

# 2. Start the web app:
cd web
cp .env.example .env.local   # BACKEND_URL points at the engine
npm install
npm run dev                  # http://localhost:3000
```

Keyboard: `↵` generate · `↑` history · `^c` clear.
