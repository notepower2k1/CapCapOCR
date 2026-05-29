# CapCapOCR Test Extension

Minimal Chrome/Edge MV3 extension for testing:
- `POST /api/ocr/base64`
- `POST /api/phase2`
- selected DOM image capture plus translated bubble overlays

## Load

1. Start the local API:
   `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload`
2. Open `chrome://extensions` or `edge://extensions`
3. Enable `Developer mode`
4. Click `Load unpacked`
5. Select this folder:
   `D:\CodingTime\CapCapOCR\browser_extension`
6. Reload the extension after code changes.

## Use

1. Open any page you want to test.
2. Click the extension icon.
3. Leave the default OCR endpoint as:
   `http://127.0.0.1:8000/api/ocr/base64`
4. Leave the default Phase 2 endpoint as:
   `http://127.0.0.1:8000/api/phase2`
5. Click `Refresh Images` to scan visible page images.
6. Pick the manga/comic image you want from `Page Image`.
7. Choose OCR and translation settings.
8. Click `Capture, Translate, Overlay`.

The popup will show:
- joined OCR text
- translated overlay text
- raw `Phase 2` JSON response

The extension tries to fetch the selected image directly from the page source.
If that is blocked, it falls back to cropping the visible tab around that element.
The page then gets overlay boxes positioned from `groups[].x/y/width/height` on top of the selected image element.

Use `Clear Overlay` to remove the current page overlay before the next test.
