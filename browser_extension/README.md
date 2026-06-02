# CapCapOCR Test Extension

Chrome/Edge MV3 extension for testing:
- `POST /api/ocr/base64`
- `POST /api/phase2`
- selected DOM image capture plus translated bubble overlays
- injected in-page quick action widget

## Load

1. Start the local API:
   `.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload`
2. Open `chrome://extensions` or `edge://extensions`
3. Enable `Developer mode`
4. Click `Load unpacked`
5. Select this folder:
   `browser_extension`
6. Reload the extension after code changes.
7. Refresh the page after reloading the extension so the updated content script is injected.

## Popup layout

The popup is split into three sections:

### Actions

Always visible:
- `Page Image`
- `Translator` toggle
- `Overlay Bubble` toggle
- `Injected Widget` toggle
- `Run`
- `Refresh Images`
- `Clear Overlay`
- status text and status badge

### Settings

Collapsible, saved in storage:
- `OCR Endpoint`
- `Phase 2 Endpoint`
- `Source`
- `OCR Engine`
- `Detection`
- `Target`
- `Translator`

### Details

Collapsible, saved in storage:
- `Joined Text`
- `Overlay Text`
- `Raw JSON`

## Popup behavior

- `Translator` off: OCR only, no Phase 2 request
- `Translator` on and `Overlay Bubble` off: OCR + translation, but no overlay is drawn on the page
- `Translator` on and `Overlay Bubble` on: OCR + translation + page overlay
- `Injected Widget` on: show the in-page `Execute` / `Remove Overlay` widget
- `Injected Widget` off: hide the in-page widget and remove the current overlay
- changing `Page Image` clears the current overlay
- `Refresh Images` clears the current overlay if the selected candidate changed or disappeared
- settings and collapsed section state are saved automatically

## In-page widget

When enabled, the extension injects a small floating widget into the current page with:
- `Execute`
- `Remove Overlay`

The widget uses the saved popup settings and automatically picks the best visible page image candidate.

## Use

1. Open any page you want to test.
2. Open the extension popup once and confirm:
   - OCR endpoint: `http://127.0.0.1:8000/api/ocr/base64`
   - Phase 2 endpoint: `http://127.0.0.1:8000/api/phase2`
3. Choose OCR, detection, target language, and translator settings.
4. Pick a `Page Image` in the popup, or use the injected page widget.
5. Run the pipeline.
6. Inspect `Joined Text`, `Overlay Text`, and `Raw JSON` if needed.

The extension tries to fetch the selected image directly from the page source.
If that is blocked, it falls back to cropping the visible tab around that element.
The page overlay is positioned from `groups[].x/y/width/height` on top of the selected image element.

## Notes

- `Google Translate` is available as a translator engine.
- The Google path translates text but does not perform OCR correction like the LLM-based translators.
- Use `Clear Overlay` or `Remove Overlay` to remove the current page overlay manually.
