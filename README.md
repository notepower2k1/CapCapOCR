# CapCapOCR

Manga OCR review tool with local OCR, local translation, bubble-aware detection, overlay preview, and JSON export.

Current best default stack:
- `OCR: GGUF Manga`
- `Detect: YOLO Bubble`
- `Translate: Local Gemma`

## What it does

- Upload a manga page in the browser
- Detect text regions or speech bubbles
- Run Japanese OCR locally
- Group blocks into readable manga text units
- Translate locally with a GGUF Gemma model or via Gemini API
- Preview translated overlays that hide the original text
- Export blocks and groups as JSON

## Implemented

- FastAPI backend
- Plain HTML/CSS/JavaScript frontend
- Browser extension test client
- OCR engines:
  - `gguf`: `PaddleOCR-VL-For-Manga` GGUF via `llama-cpp-python`
  - `hybrid`: Paddle detection + `manga-ocr`
  - `paddle`: Paddle-only OCR
- Detection engines:
  - `text`: Paddle text detection
  - `bubble`: YOLO speech-bubble detection + Paddle text detection inside bubbles
- Translation engines:
  - `local`: Gemma GGUF via `llama-cpp-python`
  - `api`: Gemini API
  - `auto`: prefer local, fall back to API if configured
- Canvas review UI with zoom, pan, block selection, grouped text editing, and overlay preview

## Project structure

```text
backend/
  api/
  modules/
  schemas/
  main.py
  requirements.txt
  requirements.ja.txt
browser_extension/
frontend/
  index.html
  styles.css
  app.js
ocr_ai_model/
run_backend.bat
```

## Runtime

Recommended:
- Python `3.11`
- Windows is supported and currently used in this repo setup

Pinned dependency notes:
- `paddlepaddle==3.0.0`
- `llama-cpp-python==0.3.23` in the repo venv

## Model files

Expected local model files in `ocr_ai_model/`:

- `PaddleOCR-VL-For-Manga-BF16.gguf`
- `PaddleOCR-VL-For-Manga-mmproj-BF16.gguf`
- `gemma-4-E4B-it-Q4_K_M.gguf`
- `yolov8m_seg-speech-bubble.pt`

## Setup

### Windows

Create the venv and install:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.ja.txt
```

Start the backend:

```powershell
.\run_backend.bat
```

Or directly:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

Open:
- App: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

## Environment variables

Optional:

- `GEMINI_API_KEY`
  - only needed for `translator_engine=api`
- `GGUF_OCR_MODEL_PATH`
- `GGUF_OCR_MMPROJ_PATH`
- `GGUF_TRANSLATOR_MODEL_PATH`
- `GGUF_OCR_N_GPU_LAYERS`
- `BUBBLE_DETECT_MODEL_PATH`
- `BUBBLE_DETECT_CONF`
- `BUBBLE_DETECT_IOU`

Default behavior:
- local GGUF OCR works if the OCR model files exist
- local Gemma translation works if the Gemma GGUF file exists
- Gemini API translation is disabled unless `GEMINI_API_KEY` is set

## Frontend workflow

1. Upload a manga page.
2. Choose:
   - OCR engine
   - detection engine
   - target language
   - translator engine
3. Click `Detect OCR`.
4. Review or edit OCR blocks.
5. Click `Run Phase 2`.
6. Review grouped text, corrected JP, and translation.
7. Toggle `Show Overlay` to preview translated replacement text.
8. Export JSON if needed.

Recommended settings for manga bubbles:

- `Source: Japanese`
- `OCR: GGUF Manga`
- `Detect: YOLO Bubble`
- `Translate: Local Gemma`

## API

### `POST /api/ocr`

Multipart form fields:

- `image`: image file
- `source_lang`: `ja` or `auto`
- `ocr_engine`: `gguf`, `hybrid`, `paddle`, or `auto`
- `detection_engine`: `text` or `bubble`

Notes:
- `detection_engine=bubble` is intended for Japanese manga workflows
- `ocr_engine=paddle` only supports `detection_engine=text`

Response:

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
      "confidence": 0.0,
      "direction": "vertical"
    }
  ]
}
```

### `POST /api/ocr/base64`

JSON body:

```json
{
  "image_base64": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
  "source_lang": "ja",
  "ocr_engine": "gguf",
  "detection_engine": "bubble"
}
```

Notes:
- accepts either a full data URL or raw base64 bytes
- returns the same shape as `POST /api/ocr`

### `POST /api/phase2`

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
      "confidence": 0.0,
      "direction": "vertical"
    }
  ],
  "source_lang": "ja",
  "ocr_engine": "gguf",
  "detection_engine": "bubble",
  "translator_engine": "local",
  "target_lang": "en",
  "translate": true
}
```

Response:

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
      "confidence": 0.0,
      "direction": "vertical"
    }
  ],
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

Frontend export includes:

- `image`
- `settings`
  - `source_lang`
  - `ocr_engine`
  - `detection_engine`
  - `translator_engine`
  - `target_lang`
  - `overlay_font_size`
- `blocks`
- `groups`

## Browser extension

The extension lives in [browser_extension](./browser_extension).

It can:
- scan the current page for visible image candidates
- capture one selected image
- call `/api/ocr/base64`
- call `/api/phase2`
- overlay translated text back onto the page

Current extension controls include:
- OCR engine
- detection engine
- translator engine
- target language

Load it as an unpacked extension in Chrome or Edge after starting the backend.

## Notes

- `gguf` OCR now uses detection first, then GGUF recognition on detected groups. It no longer returns a forced single whole-page block unless detection fails.
- `YOLO Bubble` detection helps recover missed speech bubbles, but it is still a speech-bubble detector, not a full non-bubble text detector.
- `Paddle Text` remains useful for SFX or text outside bubbles.
- `manga-ocr` remains available as a fallback path, but the current preferred manga setup is `GGUF + YOLO Bubble`.
- Overlay preview is for review and testing, not polished production typesetting.
- If required dependencies or model files are missing, the API returns clear `503` setup errors instead of crashing at startup.
