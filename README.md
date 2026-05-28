# CapCapOCR

Phase 2 manga OCR workflow. The app uploads a page, runs OCR, lets the user review and correct raw text blocks, groups blocks into manga text units, orders them for reading flow, translates Japanese to English with Gemma, previews overlay bubbles, and exports the result as JSON.

## What is implemented

- FastAPI backend with `POST /api/ocr`
- FastAPI backend with `POST /api/ocr/base64`
- FastAPI backend with `POST /api/phase2`
- Plain HTML/CSS/JavaScript frontend served by the backend
- Canvas preview with zoom, pan, bbox overlay, and block selection
- Editable OCR block list with confidence and direction
- Editable grouped text units with corrected Japanese and English translation
- Manual reading-order editing for grouped text units
- Target-language selection for Phase 2 translation
- Overlay preview for translated bubble text with adjustable font size
- JSON export of OCR blocks plus grouped Phase 2 output
- Hybrid OCR: PaddleOCR detection plus `manga-ocr` recognition for Japanese
- Phase 2 grouping, reading order, and Gemma-powered translation
- Lazy model loading with explicit dependency errors

## Project structure

```text
backend/
  api/
  modules/
  schemas/
  main.py
  requirements.txt
frontend/
  index.html
  styles.css
  app.js
phase1.md
```

## Recommended runtime

Use Python 3.11 for the PaddleOCR stack. The code is written to be compatible with 3.11+, but Paddle dependencies are usually more reliable on 3.11 than 3.12.

## Setup

```bash
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r backend/requirements.ja.txt
export GEMINI_API_KEY=your_google_ai_studio_key
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Environment variables

- `GEMINI_API_KEY`
  - required only for Phase 2 translation
  - if unset, Phase 2 still performs grouping and reading order, but translation is disabled

Example local `.env`:

```env
GEMINI_API_KEY=your_google_ai_studio_key
```

This repo does not auto-load `.env`, so export it before starting the server:

```bash
export $(grep -v '^#' .env | xargs)
uvicorn backend.main:app --reload
```

## Frontend workflow

1. Upload one manga page image.
2. Run `Detect OCR`.
3. Review or edit raw OCR blocks.
4. Run `Phase 2` to group text, assign reading order, and translate.
5. Review grouped source text, corrected Japanese, and translated output.
6. Adjust reading order manually if needed.
7. Preview translated overlay bubbles on the canvas.
8. Export JSON.

## API

`POST /api/ocr`

Multipart form fields:

- `image`: image upload
- `source_lang`: `ja` or `auto`

Response shape:

```json
{
  "image": {
    "width": 1200,
    "height": 1800
  },
  "blocks": [
    {
      "id": 1,
      "bbox": [[100, 120], [220, 120], [220, 180], [100, 180]],
      "text": "ありがとう",
      "confidence": 0.96,
      "direction": "horizontal"
    }
  ]
}
```

`POST /api/phase2`

JSON body:

```json
{
  "image": {
    "width": 1200,
    "height": 1800
  },
  "blocks": [
    {
      "id": 1,
      "bbox": [[100, 120], [220, 120], [220, 180], [100, 180]],
      "text": "ありがとう",
      "confidence": 0.96,
      "direction": "vertical"
    }
  ],
  "source_lang": "ja",
  "target_lang": "en",
  "translate": true
}
```

`POST /api/ocr/base64`

JSON body:

```json
{
  "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "source_lang": "ja"
}
```

Notes:

- accepts either a full data URL like `data:image/png;base64,...` or raw base64 bytes
- intended for browser extensions or other clients that already capture images as data URLs
- returns the same response shape as `POST /api/ocr`

Response shape:

```json
{
  "image": {
    "width": 1200,
    "height": 1800
  },
  "blocks": [],
  "groups": [
    {
      "id": 1,
      "block_ids": [1],
      "bbox": [[100, 120], [220, 120], [220, 180], [100, 180]],
      "x": 100,
      "y": 120,
      "width": 120,
      "height": 60,
      "reading_order": 1,
      "source_text": "ありがとう",
      "corrected_text": "ありがとう",
      "translated_text": "Thank you."
    }
  ],
  "translation_enabled": true
}
```

## Export format

The frontend JSON export includes:

- `image`
- `image_base64` can be used instead of multipart upload for extension-driven OCR
- `settings`
  - `source_lang`
  - `target_lang`
  - `overlay_font_size`
- `blocks`
- `groups`

For browser overlays, each Phase 2 group now includes both:

- `bbox`
- explicit `x`, `y`, `width`, `height`

## Notes

- `source_lang=ja` uses PaddleOCR for region detection and `manga-ocr` for recognition on each detected crop.
- `confidence` remains `0.0` on the Japanese hybrid path because `manga-ocr` does not expose a confidence score.
- `source_lang=auto` currently uses the existing PaddleOCR detect+recognize path.
- `manga-ocr` requires the CPU-only Torch install in `backend/requirements.ja.txt` and downloads model weights on first use.
- `POST /api/phase2` works without translation if `GEMINI_API_KEY` is not set. In that case it still returns grouped text units and reading order with `translation_enabled=false`.
- The translation step uses Google AI Studio via the Generative Language API and expects the `gemma-4-26b-a4b-it` model to be available on the configured key.
- Phase 2 translation is conservative by design. It tries to preserve names, punctuation, and ambiguous OCR text rather than aggressively rewriting it.
- Overlay rendering is a review preview, not final manga typesetting.
- If PaddleOCR, PaddlePaddle, or `manga-ocr` is missing or fails to initialize, the API returns a clear `503` with setup guidance instead of crashing at startup.
